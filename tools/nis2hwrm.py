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
# Scene spread for models bigger than Cataclysm's at Gearbox's 0.35: 1.0 with our converted models
# (Cataclysm Remastered's own were ~1.1)
MODEL_SCALE = 1.0
TELEPORT = 20     # HWRM units moved between two keys a frame apart: an off-camera reposition, hidden while it moves
TAIL_FRAMES = 45   # extra time after the HW1 NIS ends, for the fade back in (HW1's engine did that itself)
NIS_SPEECH_FLAG = 0x20000000
# HW1 "meshAnimStart <clip>" -> numbered .madstate state (handled in tools/overrides/ship/*/*.madstate)
NIS_STATES = {"DockOpen": "NIS00", "DockClose": "NIS01"}
# Cataclysm speech actor bits (NOTES.md; 0x800 = the NIS pilots' chatter, e.g. n01's Workers / Recon)
SPEAKERS = {0x800: "pilots", 0x1000: "Fleet Command", 0x2000: "Tactical Officer", 0x8000: "other fleets"}
NIS_STATE_FIRST_FRAME = 5   # earlier state changes are moved here (frame 0 ones were ignored)

# Every HW1 NIS script command is accounted for (docs/nis/<name>.md lists each event and what became of it):
# translated into the HWRM script, cued (played by the mission runtime at its time, cataclysmkas.lua KAS_NisCues:
# what HWRM NIS scripts can't do), or listed here with the reason it is not converted. A command in none of these
# stops the conversion, so nothing is lost without a line in the report.
NOT_CONVERTED = {
    "colorScheme": "HWRM ships use their player's team colours",
    "minimumLODSet": "HWRM picks LODs itself",
    "motionCueScale": "HW1 camera motion-cue tuning; no HWRM equivalent",
    "cameraFOV": "converted into each camera's lens (fov_events), not a script command",
    "globalAmbient": "lighting comes from the level's background in HWRM",
    "lightAmbient": "lighting comes from the level's background in HWRM",
    "lightDiffuse": "lighting comes from the level's background in HWRM",
    "numberLights": "lighting comes from the level's background in HWRM",
    "remainAtEnd": "the real ships are hidden during the intro instead (KAS_RunAfterIntro)",
    "subtitle": "Cataclysm-only (subtitle <n> <ms>); shows nothing in the original (n01 at 10 s / 16 s, checked "
                "in Cataclysm by the user)",
    "fire": "Gearbox's HW1 NIS conversions drop it too (the attack() before it does the shooting)",
    "fog": "TODO: NIS fog not converted",
    "mimic": "TODO: mimic not converted",
    "ebolts": "TODO: effect not converted",
    "stretch": "TODO: effect not converted",
    "repair": "TODO: NIS repair not converted",
    "openSlipgate": "TODO: slipgate effect not converted",
    "closeslipgate": "TODO: slipgate effect not converted",
    "beastEffect": "TODO: effect not converted",
}
TRANSLATED = ["fadeSet", "fadeTo", "wideScreenIn", "wideScreenOut", "musicVolume", "speechVolume", "SFXVolume",
              "hideUniverseToggle", "hide", "show", "meshAnimStart", "startMusic", "fleetSpeechEvent", "speechEvent",
              "attack", "haltAttack", "deathDamage", "deathProjectile", "deathBeam", "health"]
# HW1 NIS death kinds (NIS.c nisDeath*Set) -> HWRM death() as Gearbox's HW1 conversions use them
DEATHS = {"deathDamage": "deathCannon", "deathProjectile": "deathPlasma", "deathBeam": "deathBeam"}
# NIS object type (substring) -> seconds its HWRM weapon charges before firing: attack() is ordered that much early.
# Ion cannons: tai/kus_ioncannon.wepn beam anticipation 2 s (+ margin).
ATTACK_LEAD = {"ioncannonfrigate": 2.2}
# ... and seconds its haltAttack() is put off (the beam stops at once in HWRM; nislet01's ion frigate beam cut off on
# screen: 0.5 s was a little long in game)
HALT_DELAY = {"ioncannonfrigate": 0.25}
# explosion for a target that "dies" under such a beam (beam_kills): stock HW1 fighter death effect
BEAM_KILL_FX, BEAM_KILL_SCALE, BEAM_KILL_SUFFIX = "death_generic_fighter", 0.75, "_explosion"
COMMANDS = {c.lower(): c for c in TRANSLATED + list(NOT_CONVERTED)}   # spelling used below, by lower case
HW1_NIS_FOV = 75.0          # NIS.h NIS_DefaultFOV: HW1 field of view is vertical (Camera.c), on a 4:3 screen
SCREEN_ASPECT = 16 / 9


def camera_lens(hw1_fov):
    """CMRA lens record after the eye name: u32 0, then doubles (0, 21.8, 31.928, 24, near 3, far 50000) in
    Gearbox's files. Experiment (Phase 0.5): fields 1/2 taken as vertical/horizontal FOV in degrees, set so the
    horizontal view matches HW1's 4:3 one on a 16:9 screen."""
    h = 2 * math.degrees(math.atan(math.tan(math.radians(hw1_fov / 2)) * 4 / 3))
    v = 2 * math.degrees(math.atan(math.tan(math.radians(h / 2)) / SCREEN_ASPECT))
    return struct.pack("<I6d", 0, 0.0, v, h, 24.0, 3.0, 50000.0)


def fov_events(script):
    """[(frame, fov)] from the HW1 script's global cameraFOV commands."""
    ev, frame, in_obj = [(0, HW1_NIS_FOV)], 0, False
    for l in open(script, encoding="latin-1").read().splitlines():
        l = l.split(";")[0].strip()
        if l.startswith("with "):
            in_obj = True
        elif l == "}":
            in_obj = False
        m = re.match(r"at\s+frame\s+(\d+)", l)
        if m:
            frame = int(m.group(1))
        m = re.match(r"cameraFOV\s+([\d.]+)", l)
        if m and not in_obj:
            ev.append((frame, float(m.group(1))))
    return ev
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
    x, y, z, h, p, b = (spline_eval(times, cv[k], tcb, t) for k in range(6))
    world = (-z, x, y)                                    # NIS.c: position mode "-Z, X, Y"
    pos = tuple(SCALE * MODEL_SCALE * c for c in to_hwrm_vec(world))
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
    return pos, hm


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
    def tangent(a, b):
        dt = b[0] - a[0]
        slope = (b[1] - a[1]) / dt if dt > 0 else 0.0
        n = math.hypot(1.0, slope)
        return 1.0 / n, slope / n
    # One-sided tangents (slope to the previous / next key): no overshoot between keys or across cuts.
    for i, (t, v) in enumerate(samples):
        tin = tangent(samples[i - 1], samples[i]) if i > 0 else tangent(samples[i], samples[min(i + 1, len(samples) - 1)])
        tout = tangent(samples[i], samples[i + 1]) if i + 1 < len(samples) else tin
        out.append(struct.pack("<dd4f", t, v, tin[0], tin[1], tout[0], tout[1]))
    out.append(bytes(8))
    return b"".join(out)


GIMBAL_LOCK = 0.99995     # |sin ry| above this (within ~0.6 deg of +-90): keep rz from the previous frame


def continuous_euler(mats):
    """Per-frame rotation matrices -> (rx, ry, rz) with M = Rz Ry Rx, each frame the equivalent triple closest
    to the previous one: (x, y, z) and (x + pi, pi - y, z + pi) are the same rotation, angles are free modulo
    2 pi. Near gimbal lock (ry = +-90, where only x -/+ z is defined; HW1 NIS cameras rest there at heading 0)
    rz is held and rx, ry solved for it, so the angles do not flip between frames."""
    def near(a, ref):
        return a + 2 * math.pi * round((ref - a) / (2 * math.pi))
    out = []
    for m in mats:
        r = matrix_to_euler_xyz(m)
        if not out:
            out.append(r)
            continue
        p = out[-1]
        if abs(m[2][0]) > GIMBAL_LOCK:
            cz, sz = math.cos(p[2]), math.sin(p[2])
            m2 = [[cz * m[0][j] + sz * m[1][j] for j in range(3)],          # Rz(-z) * M = Ry * Rx
                  [-sz * m[0][j] + cz * m[1][j] for j in range(3)],
                  list(m[2])]
            x = math.atan2(-m2[1][2], m2[1][1])
            y = math.atan2(-m2[2][0], m2[0][0])
            out.append((near(x, p[0]), near(y, p[1]), p[2]))
            continue
        best = None
        for cand in (r, (r[0] + math.pi, math.pi - r[1], r[2] + math.pi)):
            c = tuple(near(cand[i], p[i]) for i in range(3))
            d = sum((c[i] - p[i]) ** 2 for i in range(3))
            if best is None or d < best[0]:
                best = (d, c)
        out.append(best[1])
    return out


def sample_times(path, frame_times):
    """Frame times plus instant-cut keys: where two HW1 keys sit at most a frame apart (camera cuts, often in
    clusters of 2-4 keys), hold the old pose until the first and jump 1 ms later. HWRM interpolates between keys at
    the render frame rate, which turned these one-frame steps into fast swoops."""
    ts = path["times"]
    off = 0.0                                              # HW1 reads timeOffset but never uses it
    cuts = []
    for i in range(1, len(ts) - 2):
        if 0 < ts[i + 1] - ts[i] <= 0.04:                  # every 1-frame gap was a step at HW1's 30 fps
            cuts.append((ts[i] + off, ts[i + 1] + off))
    extra = [(a + 0.001, b) for a, b in cuts]           # (sample time, time to evaluate)
    out = [(t, t) for t in frame_times] + extra
    out.sort()
    return out, len(cuts)


def camera_cuts(path):
    """Times where the HW1 camera cuts. A cut is a cluster of keys at most a frame apart; the cut is the gap in
    the cluster with the biggest change of position/view (the other keys only shape the spline)."""
    ts = path["times"]
    off = 0.0                                              # HW1 reads timeOffset but never uses it

    def change(t0, t1):
        (p0, r0), (p1, r1) = pose(path, t0, True), pose(path, t1, True)
        d = math.dist(p0, p1)
        tr = sum(r0[k][i] * r1[k][i] for i in range(3) for k in range(3))   # trace(R0^T R1)
        a = math.acos(max(-1.0, min(1.0, (tr - 1) / 2)))
        return d + 500 * a

    cuts, i, n = [], 1, len(ts)
    while i < n - 2:
        if 0 < ts[i + 1] - ts[i] <= 0.04:
            j = i
            while j + 1 < n - 1 and 0 < ts[j + 1] - ts[j] <= 0.04:
                j += 1
            best = max(range(i, j), key=lambda k: change(ts[k] + off, ts[k + 1] + off))
            cuts.append(ts[best + 1] + off)
            i = j + 1
        else:
            i += 1
    return cuts


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
    return re.sub(r"[^A-Za-z0-9_]", "", name).lower()           # scripts are not consistent about case


# ----------------------------------------------------------------------------------------------- script
def speech_lookup():
    """Speech event -> (string / wav id, duration s, subtitle, speaker) of its first phrase (NIS events have one),
    from Cataclysm-decomp/out/speech_events_sect.tsv (tools/speechmap.py) as tools/build_speech.py numbers them;
    speaker = tools/speech_speakers.tsv's, else None. Unsubtitled lines have speech_tags.INVISIBLE in speech.dat."""
    import speech_tags
    speakers = speech_tags.known_speakers()
    events = {}
    base_id = 2200000
    with open(os.path.join(DECOMP, "out", "speech_events_sect.tsv"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            ev = int(r["event"])
            if ev not in events:
                sid, text = base_id + int(r["phrase"]), r["subtitle"].strip()
                events[ev] = (sid, int(r["duration_ms"]) / 1000, text, speakers.get(sid))
    return events


def beam_kills(src, objects, fps):
    """{target key: death frame} for NIS objects that die while a HALT_DELAY ship (a beam) is attacking them: an
    HWRM beam stops when its target dies (nislet01's ion frigate cut off as the interceptor blew up, though HW1's
    kept firing into space), so such a death becomes hide() + an explosion effect object on the target's path (the
    hidden ship stays the target until haltAttack)."""
    lines = [l.split(";")[0].split("//")[0].strip() for l in open(src, encoding="latin-1").read().splitlines()]
    cur, t, attacks, deaths = None, 0, [], {}
    for l in lines:
        if not l or l.startswith("#"):
            continue
        m = re.match(r"with\s+(.+)$", l)
        if m:
            cur = objects.get(object_key(m.group(1)))
            continue
        if l == "}":
            cur = None
            continue
        m = re.match(r"at\s+frame\s+(\d+)", l)
        if m:
            t = int(m.group(1))
            continue
        m = re.match(r"(\w+)\s*(.*)$", l)
        if not m:                                          # "{"
            continue
        cmd = COMMANDS.get(m.group(1).lower(), m.group(1))
        if cur and cmd == "attack" and any(k in cur.lower() for k in HALT_DELAY):
            attacks.append([cur, objects.get(object_key(m.group(2).strip())), t, None])
        elif cur and cmd == "haltAttack":
            for a_ in attacks:
                if a_[0] == cur and a_[3] is None:
                    a_[3] = t
        elif cur and cmd in DEATHS:
            deaths[cur] = t
    out = {}
    for ship, target, t0, t1 in attacks:
        d = deaths.get(target)
        if target and d is not None and t0 <= d <= (t1 if t1 is not None else 10 ** 9):
            out[target] = d
    return out


def translate_script(src, objects, nisname, speech, fps, end_frame, cam_events, teleports, hidden_deaths=None):
    """HW1 NIS script -> HWRM NIS script. Returns (text, speech ids used, runtime cues, report rows).
    Report rows: (frame, object, HW1 command, what became of it)."""
    lines = [l.split(";")[0].split("//")[0].rstrip() for l in open(src, encoding="latin-1").read().splitlines()]
    lines = [l for l in lines if l.strip() and not l.lstrip().startswith("#")]
    out_global, out_obj, used, cues, report = [], {}, [], [], []
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
        cmd = COMMANDS.get(cmd.lower(), cmd)               # HW1 matches commands without case (nislet02 "widescreenOut")
        n_before = len(cur_list)

        def note(what):
            report.append((cur_time, cur_obj or "", f"{cmd} {args}".strip(), what))
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
        elif cmd == "meshAnimStart" and cur_obj:
            # HW1 plays a .mad clip; HWRM NIS can only set a .madstate state, and only numbered ones work (NIS00..,
            # as in mods' madstates; "NIS_DockOpen" did nothing in game): NIS_STATES maps the clip to one, whose
            # <SHIP>_NISnn_OnSet (our .madstate overrides, tools/overrides) starts the converted clip (mad2hwrm.py)
            clip = args.strip()
            if clip in NIS_STATES and cur_time < NIS_STATE_FIRST_FRAME:
                # set at frame 0 it did nothing in game (n01 Worker 2): a few frames in (later commands of this
                # key follow it there)
                cur_time = NIS_STATE_FIRST_FRAME
                cur_list.append(f"    at frame {cur_time}")
                emit(f'setMADState("{NIS_STATES[clip]}")')
            elif clip in NIS_STATES:
                emit(f'setMADState("{NIS_STATES[clip]}")')
            else:
                note("NOT CONVERTED: no NIS_STATES entry for this clip")
                continue
        elif cmd == "attack" and cur_obj:
            target = objects.get(object_key(args))
            if target is None:
                note(f"NOT CONVERTED: attack target {args!r} is not an NIS object with a model")
                continue
            lead = next((s_ for k_, s_ in ATTACK_LEAD.items() if k_ in cur_obj.lower()), 0)
            if lead:
                # HWRM charges this weapon before it fires (HW1 fired at once): order the attack that much earlier
                # so the shot lands when HW1's did (nislet01: the ion frigate's beam before the interceptor dies)
                frame = max(0, cur_time - round(lead * fps))
                cur_list.extend([f"    at frame {frame}", f'        attack("{target}")', f"    at frame {cur_time}"])
                note(f'translated: attack("{target}") at frame {frame} ({lead}s early: HWRM weapon charge time)')
                continue
            emit(f'attack("{target}")')
        elif cmd == "haltAttack" and cur_obj:
            delay = next((s_ for k_, s_ in HALT_DELAY.items() if k_ in cur_obj.lower()), 0)
            if delay:
                frame = cur_time + round(delay * fps)
                cur_list.extend([f"    at frame {frame}", "        haltAttack()", f"    at frame {cur_time}"])
                note(f"translated: haltAttack() at frame {frame} ({delay}s late: the beam keeps firing off-screen)")
                continue
            emit("haltAttack()")
        elif cmd in DEATHS and cur_obj and cur_obj in (hidden_deaths or {}):
            # a beam is still on it (beam_kills): hidden, with its explosion effect object, so the beam fires on
            emit("hide()")
            out_obj.setdefault(cur_obj + BEAM_KILL_SUFFIX, []).extend(
                [f"    at frame {cur_time}", f"        triggerEffect({BEAM_KILL_SCALE})"])
            note(f"translated: hide() + {BEAM_KILL_FX} effect (a beam is still firing at it: HWRM beams stop when "
                 f"their target dies)")
            continue
        elif cmd in DEATHS and cur_obj:
            emit(f'death("{DEATHS[cmd]}")')
        elif cmd == "health" and cur_obj:
            emit(f"health({float(args):g})")
        elif cmd == "startMusic":
            # Cataclysm stream n (tools/build_music.py): the NIS script's musicStart("cataclysm/music_nn") stayed
            # silent in game; the runtime's Sound_MusicPlayType (as kasfMusicPlay) plays it
            cues.append((cur_time or 0, "music", f"data:sound/music/cataclysm/music_{int(args):02d}"))
            note("CUED Sound_MusicPlayType")
            continue
        elif cmd in ("fleetSpeechEvent", "speechEvent"):
            ev = eval(re.sub(r"[^0-9+ ]", "", args))      # "(343 + 2048 + 536870912)"
            line = speech.get(ev & 0x3FF)
            if line is None:
                note(f"NO LINE: Cataclysm's speech tables have no phrase for event {ev & 0x3FF} (silent there too)")
                continue
            sid, secs, text, known = line
            used.append(sid)
            speaker = SPEAKERS.get(ev & 0x3FFC00, f"actor bits {ev & 0x3FFC00:#x}")
            # HWRM actors (logged in game): 16 Fleet Command, 17 Fleet Intel. Cataclysm 0x1000 = Fleet Command; a
            # known speaker (tools/speech_speakers.tsv) overrides the bits (n01's Fleet Command line has 0x800)
            fc = known == "Fleet Command" if known else ev & 0x1000
            emit(f'speechEventActor("${sid}", {16 if fc else 17}, 2)')
            who = f", {known}" if known else ""
            if text:
                note(f"speech ${sid} ({speaker}{who}, {secs:.1f}s, subtitled): speechEventActor - \"{text[:60]}\"")
            else:
                note(f"speech ${sid} ({speaker}{who}, {secs:.1f}s, unsubtitled: invisible subtitle): speechEventActor")
            continue
        elif cmd in NOT_CONVERTED:
            note(("NOT CONVERTED: " if NOT_CONVERTED[cmd].startswith("TODO") else "dropped: ") + NOT_CONVERTED[cmd])
            continue
        else:
            raise SystemExit(f"{src}: unknown NIS command {cmd!r} at frame {cur_time} ({l!r}): add a translation, "
                             f"a cue or a NOT_CONVERTED reason")
        note("translated: " + "; ".join(x.strip() for x in cur_list[n_before:]))
    # HWRM interpolates keys at the render frame rate (and snaps them to whole frames), so a one-frame HW1
    # reposition shows as a slide: hide the object for that frame unless the script already hides it.
    for key, jumps in teleports.items():
        body = out_obj.setdefault(key, [])
        state, frame, vis = 1, 0, []
        for b in body:
            m = re.match(r"\s*at frame (\d+)", b)
            if m:
                frame = int(m.group(1))
            elif b.strip() in ("hide()", "show()"):
                vis.append((frame, 1 if b.strip() == "show()" else 0))
        for fa, fb in jumps:
            shown = 1
            for f, v in sorted(vis):
                if f <= fb:
                    shown = v
            if shown:
                body += [f"    at frame {fa}", "        hide()", f"    at frame {fb}", "        show()"]
    last = cam_events[-1][1]
    out = [f'speechSetDir("{nisname}")']
    for f, cam in cam_events:
        out += [f"at frame {f}", f'    cameraCut("{cam}")']
    out += ["at frame 1", f'    cameraBlendOutOnSkip("{last}", 1)'] + out_global
    # End like Gearbox's scripts: wideScreenOut (without it the NIS never completes, frozen on its last frame). HW1
    # faded the game back in after an NIS, so the end fades in - unless the script ends on black: then it stays
    # black (the NIS and Universe_Fade share the fade; a fade-in here showed space and UI between n01 and nislet01),
    # a "noui" cue just after hides the UI again, and the runtime fades the game in unless another NIS follows
    # (KAS_NisEndsBlack). The NIS runs TAIL_FRAMES past end_frame.
    fades = [re.match(r"\s*fade(?:Set|To)\(([0-9.]+)", b) for b in out_global]
    fades = [float(m.group(1)) for m in fades if m]
    ends_black = bool(fades) and fades[-1] >= 1
    out += [f"at frame {end_frame}", "    wideScreenOut(1)", f'    cameraBlendOut("{last}", 1)']
    if ends_black:
        cues.append((end_frame - 5, "hideui", ""))     # before wideScreenOut brings the HUD back
        cues.append((end_frame + 1, "noui", ""))
    else:
        out.append("    fadeTo(0, 1)")
    for key, body in out_obj.items():
        if key == "#drop" or not any(not b.strip().startswith("at frame") for b in body):
            continue
        # every NIS ship invincible (Gearbox's HW1 conversions): attack() fires real weapons, deaths are scripted
        # and death() still kills an invincible ship (their n07 Tai_AssaultFrigate3)
        if key.endswith(BEAM_KILL_SUFFIX):
            pass
        elif body and body[0].strip() == "at frame 0":
            body = body[:1] + ["        invincible()"] + body[1:]
        else:
            body = ["    at frame 0", "        invincible()"] + body
        out += [f"with {key}", "{"] + body + ["}"]
    return "\n".join(out) + "\n", used, cues, report, ends_black


# ----------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--placeholder", default="Kus_Scout")
    ap.add_argument("--modules", default="", help="Kuun-Lan modules shown on it (make_modules.py keys, comma "
                                                  "separated: the mission's starting modules)")
    ap.add_argument("--audit-only", action="store_true",
                    help="only write docs/nis/<name>.md (cutscenes not converted yet; nothing in data/)")
    a = ap.parse_args()
    src = os.path.join(DECOMP, "extracted", "big", "nis", a.name)
    nis = nisread.read(src + ".nis")
    shipmap = load_shipmap()
    fps = a.fps
    nframes = int(math.ceil(nis["length"] * fps))
    times = [f / fps for f in range(nframes + 1)]

    anim, folw, objects, dropped, teleports, object_channels = [], [], {}, [], {}, {}
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
        st, _ = sample_times(o, times)
        tlist = [t for t, _ in st]
        ts_ = o["times"]
        for i_ in range(1, len(ts_) - 2):
            if 0 < ts_[i_ + 1] - ts_[i_] <= 0.04 and math.dist(pose(o, ts_[i_], False)[0],
                                                               pose(o, ts_[i_ + 1], False)[0]) > TELEPORT:
                teleports.setdefault(key, []).append((round(ts_[i_] * fps), round(ts_[i_ + 1] * fps)))
        poses = [pose(o, te, False) for _, te in st]
        rots = continuous_euler([p_[1] for p_ in poses])
        chans = {}
        for i, ax in enumerate("XYZ"):
            chans["translate" + ax] = [p[0][i] for p in poses]
            chans["rotate" + ax] = [r[i] for r in rots]
        names = []
        for c in ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"):
            nm = f"{key}_{c}"
            names.append(nm)
            anim.append(channel(nm, list(zip(tlist, chans[c])), fps))
        start = struct.pack("<6d", *(chans[c][0] for c in ("translateX", "translateY", "translateZ",
                                                            "rotateX", "rotateY", "rotateZ")))
        folw.append(lstr(key) + lstr("HW1") + lstr(kind) + lstr(typ) + b"".join(lstr(n) for n in names)
                    + start + b" ZYX")
        object_channels[key] = (names, start)
        # Cataclysm's Kuun-Lan carries its modules; HWRM NIS objects have no subsystems, so each module is a dummy
        # ship on the Kuun-Lan's own channels (modules share its frame)
        if typ == "smt_ms_sp":
            for m in a.modules.split(",") if a.modules else []:
                mtyp = f"smt_kl_{m}_dummy"
                folw.append(lstr(f"{key}_{m}") + lstr("HW1") + lstr(kind) + lstr(mtyp)
                            + b"".join(lstr(n) for n in names) + start + b" ZYX")

    # explosion effect objects for targets that die under a beam (beam_kills), on the target's own channels
    hidden_deaths = beam_kills(src + ".script", objects, fps)
    for target in hidden_deaths:
        names, start = object_channels[target]
        folw.append(lstr(target + BEAM_KILL_SUFFIX) + lstr("HW1") + lstr("effect") + lstr(BEAM_KILL_FX)
                    + b"".join(lstr(n) for n in names) + start + b" ZYX")

    # One HWRM camera per HW1 shot, switched with cameraCut() like Gearbox's scripts: HWRM interpolates camera
    # keys at the render frame rate, so a cut inside one camera path shows in-between frames.
    cmra, cam_events = [], []
    fovs = fov_events(src + ".script")
    order = ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ")
    for c in nis["cameras"]:
        bounds = [0.0] + [t for t in camera_cuts(c) if t < nis["length"]] + [nis["length"] + TAIL_FRAMES / fps]
        for k in range(len(bounds) - 1):
            cam = f"Camera{len(cmra)}"
            eye = cam + "_Eye"
            f0, f1 = round(bounds[k] * fps), max(round(bounds[k + 1] * fps) - 1, round(bounds[k] * fps))
            tlist = [f / fps for f in range(f0, f1 + 1)]
            poses = [pose(c, t, True) for t in tlist]
            rots = continuous_euler([p_[1] for p_ in poses])
            chans = {}
            for j, ax in enumerate("XYZ"):
                chans["translate" + ax] = [p_[0][j] for p_ in poses]
                chans["rotate" + ax] = [r[j] for r in rots]
            for c_ in order:
                anim.append(channel(f"{eye}_{c_}", list(zip(tlist, chans[c_])), fps))
            # The eye is also a FOLW object of kind "camera" (Gearbox); without it the engine has a NULL camera.
            folw.append(lstr(eye) + lstr("HW1") + lstr("camera") + lstr("") + b"".join(lstr(f"{eye}_{c_}") for c_ in order)
                        + struct.pack("<6d", *(chans[c_][0] for c_ in order)) + b" ZYX")
            fov = [v for f, v in fovs if f <= f0][-1]
            cmra.append(lstr(cam) + lstr(eye) + camera_lens(fov))
            if fov != HW1_NIS_FOV:
                print(f"  {cam} (frame {f0}): HW1 FOV {fov}")
            cam_events.append((f0, cam))
        break                                              # HW1 NIS files have one camera path
    print(f"  cameras: {len(cmra)} shots")

    body = (chunk(b"NAME", b"Homeworld2 NIS File") + chunk(b"VERS", struct.pack("<I", 0x100))
            + chunk(b"INFO", struct.pack("<III", fps, 0, nframes + TAIL_FRAMES))
            + chunk(b"ANIM", struct.pack("<I", len(anim)) + b"".join(anim))
            + chunk(b"LEAD", LEAD)
            + chunk(b"FOLW", struct.pack("<I", len(folw)) + b"".join(folw))
            + chunk(b"CMRA", struct.pack("<I", len(cmra)) + b"".join(cmra)))
    text, used, cues, report, ends_black = translate_script(src + ".script", objects, a.name, speech_lookup(), fps,
                                                            nframes + 2, cam_events, teleports, hidden_deaths)
    write_report(a.name, report, dropped, fps)
    if a.audit_only:
        todo = [r for r in report if r[3].startswith(("NOT CONVERTED", "NO LINE"))]
        print(f"{a.name}: audit only, {len(used)} speech lines ({len(cues)} would be cued), {len(todo)} events not "
              f"converted: docs/nis/{a.name}.md")
        return
    out_dir = os.path.join(MOD, "data", "nis", "cataclysm")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, a.name + ".nis"), "wb") as f:
        f.write(b"FORM" + struct.pack(">I", len(body) + 4) + b"NIS " + body)
    with open(os.path.join(out_dir, a.name + ".script"), "w", encoding="latin-1", newline="\n") as f:
        f.write(text)
    # runtime cues (cataclysmkas.lua KAS_NisStart loads them): seconds after the NIS starts
    with open(os.path.join(out_dir, a.name + "_cues.lua"), "w", encoding="latin-1", newline="\n") as f:
        f.write(f"-- Generated by tools/nis2hwrm.py: what {a.name}'s HWRM script can't play, by the mission runtime\n"
                f'KAS_NisCues["{a.name}"] = {{\n')
        for frame, kind, arg in sorted(cues):
            f.write(f'    {{ {frame / fps:.3f}, "{kind}", "{arg}" }},\n')
        f.write("}\n")
        if ends_black:
            f.write(f'KAS_NisEndsBlack["{a.name}"] = 1   -- ends on black: the runtime fades the game in\n')
    sp_dir = os.path.join(MOD, "data", "sound", "speech", "nis", a.name)
    os.makedirs(sp_dir, exist_ok=True)
    for sid in used:
        s = os.path.join(MOD, "data", "sound", "speech", "missions", "cataclysm", f"{sid}.wav")
        if os.path.exists(s):
            shutil.copyfile(s, os.path.join(sp_dir, f"{sid}.wav"))
    print(f"{a.name}: {nis['length']:.1f}s ({nframes} frames), {len(objects)} objects, {len(cmra)} cameras, "
          f"{len(anim)} channels; dropped {len(dropped)}: {', '.join(sorted(set(re.sub(r'[(][0-9]+[)]', '', d) for d in dropped)))}")
    todo = [r for r in report if r[3].startswith(("NOT CONVERTED", "NO LINE"))]
    print(f"script: {len(used)} speech lines ({len(cues)} cued), {len(todo)} events not converted: "
          f"docs/nis/{a.name}.md")


def write_report(name, report, dropped, fps):
    """docs/nis/<name>.md: every HW1 script event and what became of it, audio first (the checklist to compare
    against the original cutscene)."""
    path = os.path.join(MOD, "docs", "nis", name + ".md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    audio = [r for r in report if r[2].startswith(("fleetSpeechEvent", "speechEvent", "startMusic", "musicVolume",
                                                     "speechVolume", "SFXVolume", "subtitle"))]
    todo = [r for r in report if r[3].startswith(("NOT CONVERTED", "NO LINE"))]

    def table(rows):
        out = ["| frame | time | object | HW1 | result |", "|---|---|---|---|---|"]
        for f, obj, cmd, what in sorted(rows, key=lambda r: (r[0] or 0)):
            out.append(f"| {f} | {(f or 0) / fps:.1f}s | {obj} | `{cmd}` | {what} |")
        return "\n".join(out)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# {name}: conversion audit\n\nGenerated by tools/nis2hwrm.py. Check the audio table against the "
                f"original cutscene (every line heard there must be here and play in game).\n\n"
                f"## Audio (speech, music, volumes, subtitle cards)\n\n{table(audio)}\n\n"
                f"## Not converted ({len(todo)})\n\n{table(todo) if todo else 'None.'}\n\n"
                f"## NIS objects without an HWRM model ({len(dropped)})\n\n"
                f"{', '.join(sorted(set(dropped))) or 'None.'}\n\n## Every event\n\n{table(report)}\n")


if __name__ == "__main__":
    main()
