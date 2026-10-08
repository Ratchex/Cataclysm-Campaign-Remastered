"""Convert a Cataclysm (Homeworld 1 format) NIS cutscene into Homeworld Remastered's NIS format.

Input:  Cataclysm-decomp/extracted/big/nis/<name>.nis (+ <name>.script)
Output: data/nis/cataclysm/<name>.nis + <name>.script, speech in data/sound/speech/nis/<name>/

HW1 side (Game/NIS.c, Game/B-Spline.c, read with Cataclysm-decomp/tools/nisread.py):
  every object/camera has Kochanek-Bartels splines for x, y, z, heading, pitch, bank (degrees) with one extra
  control point at each end. Position in HW1 world = (-z, x, y); orientation = nisShipEulerToMatrix(h, p, b)
  (columns up, right, heading). Cameras use the same matrix and look along column 2 with column 1 up.
HWRM side (decoded from Gearbox's HW1Campaign/nis/*.nis, an IFF "FORM NIS "):
  INFO fps, 0, last frame | ANIM channels "<obj>_translateX".."_rotateZ": u16 count, u16 type 0, keys of
  (double time, double value, float in-tangent dx,dy, float out-tangent dx,dy), then 8 zero bytes |
  LEAD root record | FOLW objects (name, team "HW1", kind, ship type, 6 channel names, 6 start values, order) |
  CMRA cameras (name, "<name>_Eye", lens parameters copied from Gearbox).
  Rotations are radians, M = Rz * Ry * Rx (Maya "xyz"), objects face +Z, cameras look down -Z.
HW1 world -> HWRM: 0.35 * (-x, z, y), as for levels (mission2level.py); model axes as in geo2dae.py.

Usage: nis2hwrm.py <name> [--fps 30]
"""
import argparse
import bisect
import csv
import math
import os
import re
import shutil
import struct
import sys

DECOMP = r"C:\Modding\Cataclysm-decomp"
MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(DECOMP, "tools"))
import nisread  # noqa: E402

SCALE = 0.35
TAIL_FRAMES = 45   # extra time after the HW1 NIS ends, for the fade back in (HW1's engine did that itself)
NIS_SPEECH_FLAG = 0x20000000
# Lens record Gearbox writes for every camera (52 bytes after the eye name; 21.8 / 31.9 / 24 / near 3 / far 50000).
CAMERA_LENS = bytes.fromhex("000000000000000000000000000000c0cccc354080b8ab5791ed3f40000000000000384000000000000008"
                            "4000000000006ae840")
LEAD = struct.pack("<II", 1, 3) + b"HW1" + bytes(76) + b" ZYX"


# ----------------------------------------------------------------------------------------------- HW1 maths
def spline_eval(times, points, tcb, t):
    """B-Spline.c bsCurveUpdate for absolute time t (index 0 and n-1 are the extra control points)."""
    n = len(points)
    if n < 4 or t <= times[1]:
        return points[1 if n > 1 else 0]
    if t >= times[n - 2]:
        return points[n - 2]
    cp = max(1, min(bisect.bisect_right(times, t) - 1, n - 3))
    kl = times[cp + 1] - times[cp]
    s = (t - times[cp]) / kl if kl > 0 else 0.0
    t2, t3 = s * s, s * s * s
    z = 3 * t2 - t3 - t3
    h = (1 - z, z, t3 - t2 - t2 + s, t3 - t2)
    k0, k1 = tcb[cp], tcb[cp + 1]
    adj0 = kl / (times[cp + 1] - times[cp - 1]) if times[cp + 1] != times[cp - 1] else 0.0
    adj1 = kl / (times[cp + 2] - times[cp]) if times[cp + 2] != times[cp] else 0.0
    dd0a = (1 - k0[0]) * (1 + k0[1]) * (1 + k0[2])
    dd0b = (1 - k0[0]) * (1 - k0[1]) * (1 - k0[2])
    ds1a = (1 - k1[0]) * (1 - k1[1]) * (1 + k1[2])
    ds1b = (1 - k1[0]) * (1 + k1[1]) * (1 - k1[2])
    p = points
    delta = p[cp + 1] - p[cp]
    return (h[0] * p[cp] + h[1] * p[cp + 1] + h[2] * (adj0 * (dd0a * (p[cp] - p[cp - 1]) + dd0b * delta))
            + h[3] * (adj1 * (ds1a * delta + ds1b * (p[cp + 2] - p[cp + 1]))))


def rot_about(axis, rad):
    """nisRotateAboutVector, as a row-major 3x3."""
    x, y, z = axis
    s, c = math.sin(rad), math.cos(rad)
    o = 1 - c
    return [[o * x * x + c, o * x * y - z * s, o * z * x + y * s],
            [o * x * y + z * s, o * y * y + c, o * y * z - x * s],
            [o * z * x - y * s, o * y * z + x * s, o * z * z + c]]


def mm(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def col(m, j):
    return [m[0][j], m[1][j], m[2][j]]


HPB_IDENTITY_SHIP = [[0, -1, 0], [0, 0, -1], [1, 0, 0]]   # NIS.c HPBIdentityShip (column-major in the source)


def ship_euler_to_matrix(h, p, b):
    """NIS.c nisShipEulerToMatrix (angles in radians); returns row-major, columns = up, right, heading."""
    m = HPB_IDENTITY_SHIP
    m = mm(rot_about((0, 0, 1), -h), m)
    m = mm(rot_about(col(m, 2), p), m)
    m = mm(rot_about(col(m, 1), -b), m)
    return m


def to_hwrm_vec(v):
    return (-v[0], v[2], v[1])


def matrix_to_euler_xyz(m):
    """Angles (rx, ry, rz) with M = Rz * Ry * Rx."""
    ry = math.asin(max(-1.0, min(1.0, -m[2][0])))
    if abs(m[2][0]) < 0.99999:
        rx = math.atan2(m[2][1], m[2][2])
        rz = math.atan2(m[1][0], m[0][0])
    else:
        rx = math.atan2(-m[1][2], m[1][1])
        rz = 0.0
    return rx, ry, rz


def pose(path, t, camera):
    cv, times, tcb = path["curves"], path["times"], path["tcb"]
    t = t - max(path.get("timeOffset", 0.0), 0.0)
    x, y, z, h, p, b = (spline_eval(times, cv[k], tcb, t) for k in range(6))
    world = (-z, x, y)                                    # NIS.c: position mode "-Z, X, Y"
    pos = tuple(SCALE * c for c in to_hwrm_vec(world))
    m = ship_euler_to_matrix(math.radians(h), math.radians(p), math.radians(b))
    up, right, heading = col(m, 0), col(m, 1), col(m, 2)
    if camera:
        yax = to_hwrm_vec(up)
        zax = tuple(-c for c in to_hwrm_vec(right))        # camera looks along column 2; HWRM camera looks down -Z
        xax = (yax[1] * zax[2] - yax[2] * zax[1], yax[2] * zax[0] - yax[0] * zax[2], yax[0] * zax[1] - yax[1] * zax[0])
    else:
        xax = to_hwrm_vec([-c for c in right])
        yax = to_hwrm_vec(up)
        zax = to_hwrm_vec(heading)
    hm = [[xax[0], yax[0], zax[0]], [xax[1], yax[1], zax[1]], [xax[2], yax[2], zax[2]]]
    return pos, matrix_to_euler_xyz(hm)


# ----------------------------------------------------------------------------------------------- HWRM writer
def chunk(tag, data):
    return tag + struct.pack(">I", len(data)) + data


def lstr(s):
    b = s.encode("latin-1")
    return struct.pack("<I", len(b)) + b


def channel(name, samples, fps):
    """samples: list of (time, value). Constant channels get two keys."""
    if max(v for _, v in samples) - min(v for _, v in samples) < 1e-6:
        samples = [samples[0], samples[-1]] if len(samples) > 1 else samples
    out = [lstr(name), struct.pack("<HH", len(samples), 0)]
    for i, (t, v) in enumerate(samples):
        a = samples[max(i - 1, 0)]
        c = samples[min(i + 1, len(samples) - 1)]
        dt = c[0] - a[0]
        slope = (c[1] - a[1]) / dt if dt > 0 else 0.0
        n = math.hypot(1.0, slope)
        tan = (1.0 / n, slope / n)
        out.append(struct.pack("<dd4f", t, v, tan[0], tan[1], tan[0], tan[1]))
    out.append(bytes(8))
    return b"".join(out)


def unwrap(vals):
    out = [vals[0]]
    for v in vals[1:]:
        p = out[-1]
        while v - p > math.pi:
            v -= 2 * math.pi
        while v - p < -math.pi:
            v += 2 * math.pi
        out.append(v)
    return out


# ----------------------------------------------------------------------------------------------- object naming
def load_shipmap():
    m = {}
    with open(os.path.join(MOD, "tools", "shipmap.tsv"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["hwrm"]:
                m[r["ship"].lower()] = r["hwrm"]
    return m


def hwrm_object(name, race, shipmap, placeholder):
    """(kind, hwrm type) for a HW1 NIS object, or None to drop it."""
    base = re.sub(r"\(\d+\)$", "", name).strip()
    low = base.lower()
    if race == 7 or low.startswith("asteroid"):            # NSR_Asteroid
        n = re.sub(r"\D", "", low) or "1"
        return "asteroid", "Asteroid" + str(min(max(int(n), 1), 3))
    if low.startswith(("nislight", "nislensflare")) or low.startswith("dfirstplanet"):
        return None                                        # lights/flares/backdrop: not ported yet
    if low in shipmap:
        return "ship", shipmap[low]
    if low.startswith("d"):                                # derelicts without an HWRM equivalent yet
        return None
    return "ship", placeholder


def object_key(name):
    """'sRecon(1)' / 'RACE_SECT\\sRecon (1)' -> 'sRecon1'."""
    name = name.split("\\")[-1]
    return re.sub(r"[^A-Za-z0-9_]", "", name)


# ----------------------------------------------------------------------------------------------- script
def speech_lookup():
    sys.path.insert(0, os.path.join(MOD, "data", "scripts", "scar"))
    events = {}
    base_id = 2200000
    with open(os.path.join(MOD, "data", "scripts", "scar", "cataclysmspeech.lua"), encoding="latin-1") as f:
        for line in f:
            m = re.match(r'KAS_SpeechEvents\["sect(\d+)"\] = \{ (\d+), (\d+), (\d+) \}', line)
            if m:
                events[int(m.group(1))] = base_id + int(m.group(4))
    return events


def translate_script(src, objects, nisname, speech, fps, end_frame):
    """HW1 NIS script -> HWRM NIS script. Returns (text, speech ids used, notes)."""
    lines = [l.split(";")[0].split("//")[0].rstrip() for l in open(src, encoding="latin-1").read().splitlines()]
    lines = [l for l in lines if l.strip() and not l.lstrip().startswith("#")]
    out_global, out_obj, used, skipped = [], {}, [], {}
    cur_obj, cur_time, cur_list = None, None, out_global
    hidden_universe = False

    def emit(cmd):
        cur_list.append("    " * (2 if cur_obj else 1) + cmd)

    for raw in lines:
        l = raw.strip()
        m = re.match(r"with\s+(.+)$", l)
        if m:
            key = object_key(m.group(1))
            cur_obj = objects.get(key, "#drop")
            cur_list = out_obj.setdefault(cur_obj, [])
            continue
        if l == "{":
            continue
        if l == "}":
            cur_obj, cur_list = None, out_global
            continue
        m = re.match(r"at\s+frame\s+(\d+)", l)
        if m:
            cur_time = int(m.group(1))
            cur_list.append(("    " if cur_obj else "") + f"at frame {cur_time}")
            continue
        m = re.match(r"(\w+)\s*(.*)$", l)
        cmd, args = m.group(1), m.group(2).strip()
        if cmd == "fadeSet":
            emit(f"fadeSet({float(args.split('%')[0]) / 100:g})")
        elif cmd == "fadeTo":
            pct, rest = args.split("%", 1)
            fr = re.search(r"(\d+)\s*frames", rest)
            emit(f"fadeTo({float(pct) / 100:g}, {int(fr.group(1)) / fps if fr else 0:g})")
        elif cmd == "wideScreenIn":
            fr = re.search(r"(\d+)", args)
            emit(f"wideScreenIn({max(int(fr.group(1)) if fr else 1, 1) / fps:g})")
        elif cmd == "wideScreenOut":
            fr = re.search(r"(\d+)", args)
            emit(f"wideScreenOut({max(int(fr.group(1)) if fr else 1, 1) / fps:g})")
        elif cmd in ("musicVolume", "speechVolume", "SFXVolume"):
            emit(f"{cmd}({float(args):g})")
        elif cmd == "hideUniverseToggle":
            hidden_universe = not hidden_universe
            emit(f"hideUniverse({1 if hidden_universe else 0})")
        elif cmd in ("hide", "show") and cur_obj:
            emit(f"{cmd}()")
        elif cmd == "fleetSpeechEvent":
            ev = eval(re.sub(r"[^0-9+ ]", "", args))      # "(343 + 2048 + 536870912)"
            sid = speech.get(ev & 0x3FF)
            if sid is None:
                skipped["fleetSpeechEvent (no line)"] = skipped.get("fleetSpeechEvent (no line)", 0) + 1
                continue
            used.append(sid)
            # HWRM actors (logged in game): 16 Fleet Command, 17 Fleet Intel. Cataclysm 0x1000 = Fleet Command.
            emit(f'speechEventActor("${sid}", {16 if ev & 0x1000 else 17}, 2)')
        else:
            skipped[cmd] = skipped.get(cmd, 0) + 1
    out = [f'speechSetDir("{nisname}")', "at frame 0", '    cameraCut("Camera0")',
           "at frame 1", '    cameraBlendOutOnSkip("Camera0", 1)'] + out_global
    # HW1 faded the game back in after an NIS; HWRM keeps the NIS fade, so end like Gearbox's scripts do.
    out += [f"at frame {end_frame}", "    wideScreenOut(1)", '    cameraBlendOut("Camera0", 1)', "    fadeTo(0, 1)"]
    for key, body in out_obj.items():
        if key == "#drop" or not any(not b.strip().startswith("at frame") for b in body):
            continue
        out += [f"with {key}", "{"] + body + ["}"]
    return "\n".join(out) + "\n", used, skipped


# ----------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--placeholder", default="Kus_Scout")
    a = ap.parse_args()
    src = os.path.join(DECOMP, "extracted", "big", "nis", a.name)
    nis = nisread.read(src + ".nis")
    shipmap = load_shipmap()
    fps = a.fps
    nframes = int(math.ceil(nis["length"] * fps))
    times = [f / fps for f in range(nframes + 1)]

    anim, folw, objects, dropped = [], [], {}, []
    kept = []
    for o in nis["objects"]:
        k = hwrm_object(o["name"], o["race"], shipmap, a.placeholder)
        if k is None:
            dropped.append(o["name"])
        else:
            kept.append((o, k))
    counts = {}
    for o, (kind, typ) in kept:
        counts[typ] = counts.get(typ, 0) + 1
    seen = {}
    for o, (kind, typ) in kept:
        # NISShipStartPosition finds the centre ship by object name = ship type (Gearbox: "Kus_Mothership",
        # "Tur_Fighter1"), so name objects after their HWRM type, numbered when the type repeats.
        seen[typ] = seen.get(typ, 0) + 1
        key = typ if counts[typ] == 1 else f"{typ}{seen[typ]}"
        objects[object_key(o["name"])] = key
        poses = [pose(o, t, False) for t in times]
        chans = {}
        for i, ax in enumerate("XYZ"):
            chans["translate" + ax] = [p[0][i] for p in poses]
            chans["rotate" + ax] = unwrap([p[1][i] for p in poses])
        names = []
        for c in ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"):
            nm = f"{key}_{c}"
            names.append(nm)
            anim.append(channel(nm, list(zip(times, chans[c])), fps))
        folw.append(lstr(key) + lstr("HW1") + lstr(kind) + lstr(typ) + b"".join(lstr(n) for n in names)
                    + struct.pack("<6d", *(chans[c][0] for c in ("translateX", "translateY", "translateZ",
                                                                  "rotateX", "rotateY", "rotateZ"))) + b" ZYX")

    cmra = []
    for i, c in enumerate(nis["cameras"]):
        cam, eye = f"Camera{i}", f"Camera{i}_Eye"
        poses = [pose(c, t, True) for t in times]
        chans = {}
        for j, ax in enumerate("XYZ"):
            chans["translate" + ax] = [p[0][j] for p in poses]
            chans["rotate" + ax] = unwrap([p[1][j] for p in poses])
        order = ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ")
        for c_ in order:
            anim.append(channel(f"{eye}_{c_}", list(zip(times, chans[c_])), fps))
        # The eye is also a FOLW object of kind "camera" (Gearbox); without it the engine has a NULL camera.
        folw.append(lstr(eye) + lstr("HW1") + lstr("camera") + lstr("") + b"".join(lstr(f"{eye}_{c_}") for c_ in order)
                    + struct.pack("<6d", *(chans[c_][0] for c_ in order)) + b" ZYX")
        cmra.append(lstr(cam) + lstr(eye) + CAMERA_LENS)

    body = (chunk(b"NAME", b"Homeworld2 NIS File") + chunk(b"VERS", struct.pack("<I", 0x100))
            + chunk(b"INFO", struct.pack("<III", fps, 0, nframes + TAIL_FRAMES))
            + chunk(b"ANIM", struct.pack("<I", len(anim)) + b"".join(anim))
            + chunk(b"LEAD", LEAD)
            + chunk(b"FOLW", struct.pack("<I", len(folw)) + b"".join(folw))
            + chunk(b"CMRA", struct.pack("<I", len(cmra)) + b"".join(cmra)))
    out_dir = os.path.join(MOD, "data", "nis", "cataclysm")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, a.name + ".nis"), "wb") as f:
        f.write(b"FORM" + struct.pack(">I", len(body) + 4) + b"NIS " + body)

    text, used, skipped = translate_script(src + ".script", objects, a.name, speech_lookup(), fps, nframes + 2)
    with open(os.path.join(out_dir, a.name + ".script"), "w", encoding="latin-1", newline="\n") as f:
        f.write(text)
    sp_dir = os.path.join(MOD, "data", "sound", "speech", "nis", a.name)
    os.makedirs(sp_dir, exist_ok=True)
    for sid in used:
        s = os.path.join(MOD, "data", "sound", "speech", "missions", "cataclysm", f"{sid}.wav")
        if os.path.exists(s):
            shutil.copyfile(s, os.path.join(sp_dir, f"{sid}.wav"))
    print(f"{a.name}: {nis['length']:.1f}s ({nframes} frames), {len(objects)} objects, {len(cmra)} cameras, "
          f"{len(anim)} channels; dropped {len(dropped)}: {', '.join(sorted(set(re.sub(r'[(][0-9]+[)]', '', d) for d in dropped)))}")
    print(f"script: {len(used)} speech lines; not translated: {skipped}")


if __name__ == "__main__":
    main()
