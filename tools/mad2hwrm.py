"""Convert a Cataclysm/HW1 mesh animation (.mad, "Mellonn" 0.91, MeshAnim.c) to an HWRM .mad for our model.

The model must have been built with the same objects as joints (geo2dae.py --anim-joints): every animated object
is a joint named after it (brackets dropped: Blade(1) -> Blade1), its local transform relative to the nearest
animated ancestor, in HWRM axes.

HW1 (MeshAnim.c madAnimationUpdate): per object six Kochanek-Bartels splines over shared key times (seconds);
the object's local matrix is translation (c1, c2, -c0) and rotation nisObjectEulerToMatrix(c3, c4, c5) (radians),
replacing the object's .geo matrix. Each clip is [startTime, endTime].

HWRM .mad (IFF, chunk sizes big-endian, payload little-endian), as Cataclysm Remastered's and stock files:
  FORM "MAD " { NAME "Homeworld2 MAD File", VERS 04 01 00 00, INFO <5I: fps, clips, curves, joint refs, curve refs>,
                STRI null-terminated strings, MARK clips, CURV curves }
  MARK per clip: name, start, end, loop start, loop end (f32 seconds; stock clips run e.g. 0.0667-1.8), joint count, per joint: name, curve count,
       curve indices (6: translateX/Y/Z, rotateX/Y/Z; radians, composed Z * Y * X)
  CURV per curve: name (<joint>_translateX ...), key count, keys <dd4f: time (s), value, in tangent dx/dy,
       out tangent dx/dy (unit vectors, value per second)>, 8 zero bytes
Times stay HW1's (seconds); every clip gets its own curves, sampled every 1/30 s.

Usage: mad2hwrm.py <hw1.mad> <hw1.geo> <out.mad> --joints A,B,... [--scale 0.35] [--clips X,Y] [--trim OBJECT=DEG]
"""
import argparse
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geo2dae import geo2obj, hwrm_local, joint_frames, joint_name, rigid_inverse  # noqa: E402
from nis2hwrm import continuous_euler, matrix_to_euler_xyz, mm, rot_about, spline_eval  # noqa: E402

FPS = 30
# a joint within this of its bind pose for a whole clip is left out of it (HW1 keys drift ~0.1 unit / 0.01 rad
# between clips; including it would make the clip override other clips playing on that joint)
REST_MOVE, REST_TURN = 0.15, 0.03


def read_mellonn(path):
    d = open(path, "rb").read()
    if len(d) < 40:
        raise ValueError("too short")
    ident, ver, sbl, sbo, length, fps, nobj, objo, nanim = struct.unpack_from("<8sfiIffiIi", d)
    if not ident.startswith(b"Mellonn") or not (0 <= sbl <= len(d)) or not (0 <= nobj < 256) or not (0 <= nanim <= 32):
        raise ValueError(f"not a Mellonn .mad: {ident!r} objs {nobj} anims {nanim}")
    sb = len(d) - sbl

    def s(o):
        return d[sb + o:d.index(b"\0", sb + o)].decode("latin-1")
    clips = []
    for i in range(nanim):
        n, st, en, fl = struct.unpack_from("<IffI", d, 40 + i * 16)
        clips.append({"name": s(n), "start": st, "end": en, "flags": fl})
    objs = {}
    for i in range(nobj):
        f = struct.unpack_from("<IHHIiII6I", d, objo + i * 48)
        n, _, _, bits, nk, to, po = f[:7]
        if not 0 < nk <= (len(d) - to) // 4:
            raise ValueError(f"object {i}: bad key count {nk}")
        objs[s(n)] = {"bits": bits, "times": list(struct.unpack_from(f"<{nk}f", d, to)),
                      "tcb": [struct.unpack_from("<3f", d, po + 12 * k) for k in range(nk)],
                      "curves": [list(struct.unpack_from(f"<{nk}f", d, p)) for p in f[7:]]}
    return fps, clips, objs


def euler_to_matrix(h, p, b):
    """NIS.c nisObjectEulerToMatrix (row-major 3x3)."""
    m = [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]
    m = mm(rot_about((1, 0, 0), -h), m)
    m = mm(rot_about([m[0][2], m[1][2], m[2][2]], p), m)
    m = mm(rot_about([m[0][1], m[1][1], m[2][1]], -b), m)
    return m


def angles(path, t):
    return [spline_eval(path["times"], cv, path["tcb"], t) for cv in path["curves"]]


def local_matrix(path, t, trim=None):
    """Object's HW1 local matrix at time t, column-major 4x4. trim = (rest hpb, k): the angles' swing away from
    rest scaled by k (--trim)."""
    c0, c1, c2, h, p, b = angles(path, t)
    if trim:
        rest, k = trim
        h, p, b = (rest[j] + ([h, p, b][j] - rest[j]) * k for j in range(3))
    r = euler_to_matrix(h, p, b)
    m = [0.0] * 16
    for row in range(3):
        for col in range(3):
            m[col * 4 + row] = r[row][col]
    m[12:15] = [c1, c2, -c0]
    m[15] = 1.0
    return m


def chunk(tag, data):
    return tag + struct.pack(">I", len(data)) + data


def keys_blob(samples):
    """samples: [(time, value)]; constant curves get their two end keys. One-sided unit tangents."""
    if max(v for _, v in samples) - min(v for _, v in samples) < 1e-6:
        samples = [samples[0], samples[-1]]

    def tangent(a, b):
        dt = b[0] - a[0]
        slope = (b[1] - a[1]) / dt if dt > 0 else 0.0
        n = math.hypot(1.0, slope)
        return 1.0 / n, slope / n
    out = []
    for i, (t, v) in enumerate(samples):
        tin = tangent(samples[i - 1], samples[i]) if i > 0 else tangent(samples[i], samples[min(i + 1, len(samples) - 1)])
        tout = tangent(samples[i], samples[i + 1]) if i + 1 < len(samples) else tin
        out.append(struct.pack("<dd4f", t, v, tin[0], tin[1], tout[0], tout[1]))
    return len(samples), b"".join(out) + bytes(8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mad")
    ap.add_argument("geo")
    ap.add_argument("out")
    ap.add_argument("--joints", required=True)
    ap.add_argument("--scale", type=float, default=0.35)
    ap.add_argument("--clips", default="", help="only these clips (default: all)")
    ap.add_argument("--trim", action="append", default=[],
                    help="OBJECT=DEGREES: the object turns that much less at its furthest from rest (over the clips "
                         "converted), every angle's swing scaled by the same factor")
    ap.add_argument("--shift", action="append", default=[],
                    help="CLIP:OBJECT=X,Y,Z: added to the object's translation (HW1 units, its parent's axes) during "
                         "that clip; the game script places the ship that much the other way (the Acolyte's Link: "
                         "two ships on one spot collide, so each sits where its body starts)")
    ap.add_argument("--rolled", action="append", default=[],
                    help="NEW=CLIP:OBJECT[:SECONDS]: a copy of CLIP named NEW with OBJECT turned 180 degrees about the "
                         "forward axis (the model shown upside down while the ship flies upright: the engine fought a "
                         "rolled ship, jiggling it), then turning upright over SECONDS after the clip's end")
    a = ap.parse_args()
    names = [n for n in a.joints.split(",") if n]
    _, clips, paths = read_mellonn(a.mad)
    _, _, _, objs = geo2obj.parse(a.geo)
    frames = joint_frames(objs, set(names))
    by_name = {objs[i]["name"]: i for i in frames}
    missing = [n for n in names if n not in paths or n not in by_name]
    if missing:
        sys.exit(f"not in the .mad or .geo: {missing}")
    cache = {}

    def static_prefix(i):
        """Matrix from the joint parent's frame to the geo parent's frame (static objects in between)."""
        jp, _ = frames[i]
        gp = objs[i]["parent"]
        if gp is None:
            return None
        W = geo2obj.world(objs, gp, cache)
        return W if jp is None else geo2obj.matmul(rigid_inverse(geo2obj.world(objs, jp, cache)), W)

    prefix = {i: static_prefix(i) for i in frames}

    # check the convention: each object's .mad pose at time 0 against its .geo matrix
    worst = 0.0
    for n in names:
        i = by_name[n]
        m0 = local_matrix(paths[n], 0.0)
        worst = max(worst, max(abs(x - y) for x, y in zip(m0[:15], objs[i]["matrix"][:15])))
    print(f"pose at t=0 vs .geo matrices: max difference {worst:.4f}")

    wanted = [c for c in clips if not a.clips or c["name"] in a.clips.split(",")]
    trims = {}
    for spec in a.trim:
        n, deg = spec.split("=")
        rest = angles(paths[n], 0.0)[3:]
        swing = max(abs(angles(paths[n], c["start"] + (c["end"] - c["start"]) * k / 60)[3 + j] - rest[j])
                    for c in wanted for k in range(61) for j in range(3))
        trims[n] = (rest, (swing - math.radians(float(deg))) / swing)
        print(f"  {n}: swing {math.degrees(swing):.1f} deg -> {math.degrees(swing) - float(deg):.1f}")

    for spec in a.rolled:
        new, rest = spec.split("=")
        parts = rest.split(":")
        base = next(c for c in clips if c["name"] == parts[0])
        right = float(parts[2]) if len(parts) > 2 else 0.0
        wanted.append({"name": new, "start": base["start"], "end": base["end"] + right, "base": base["name"],
                       "base_end": base["end"], "roll": parts[1], "right": right})

    shifts = {}
    for spec in a.shift:
        key, xyz = spec.split("=")
        clip, obj = key.split(":")
        shifts[(clip, obj)] = [float(v) for v in xyz.split(",")]

    def hwrm_pose(i, t, c):
        name = objs[i]["name"]
        m = local_matrix(paths[name], min(t, c.get("base_end", t)), trims.get(name))
        d = shifts.get((c.get("base", c["name"]), name))
        if d:
            m = m[:12] + [m[12] + d[0], m[13] + d[1], m[14] + d[2]] + m[15:]
        if c.get("roll") == name:
            # about the model's forward axis (HW1 +Z), through the ship's origin; easing upright after the clip
            k = 0.0 if t <= c["base_end"] else min(1.0, (t - c["base_end"]) / c["right"])
            th = math.pi * (1.0 - k * k * (3 - 2 * k))
            cs, sn = math.cos(th), math.sin(th)
            m = geo2obj.matmul([cs, sn, 0, 0, -sn, cs, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], m)
        if prefix[i] is not None:
            m = geo2obj.matmul(prefix[i], m)
        return hwrm_local(m, a.scale)

    bind = {i: hwrm_local(frames[i][1], a.scale) for i in frames}
    strings, stri = {}, bytearray()

    def sid(s):
        if s not in strings:
            strings[s] = len(stri)
            stri.extend(s.encode("latin-1") + b"\0")
        return strings[s]

    curves, marks, njref, ncref = [], [], 0, 0
    for c in wanted:
        t0, t1 = c["start"], c["end"]
        steps = max(1, int(math.ceil((t1 - t0) * FPS - 1e-6)))
        fr = [min(t1, t0 + k / FPS) for k in range(steps + 1)]
        joints = []
        for n in names:
            i = by_name[n]
            poses = [hwrm_pose(i, t, c) for t in fr]
            eul = continuous_euler([r for _, r in poses])
            # anchor the angles to the bind pose's (2 pi turns kept: a full spin stays a spin)
            b_eul = matrix_to_euler_xyz(bind[i][1])
            shift = [2 * math.pi * round((b_eul[k] - eul[0][k]) / (2 * math.pi)) for k in range(3)]
            eul = [tuple(e[k] + shift[k] for k in range(3)) for e in eul]
            chans = [[p[0][k] for p in poses] for k in range(3)] + [[e[k] for e in eul] for k in range(3)]
            bvals = list(bind[i][0]) + list(b_eul)
            if all(max(abs(v - bvals[k]) for v in chans[k]) < (REST_MOVE if k < 3 else REST_TURN) for k in range(6)):
                continue        # at its bind pose throughout (within the HW1 keys' jitter): not part of this clip
            jn = joint_name(n)
            idx = []
            for k, ch in enumerate(("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ")):
                nk, blob = keys_blob(list(zip(fr, chans[k])))
                curves.append(struct.pack("<II", sid(f"{jn}_{ch}"), nk) + blob)
                idx.append(len(curves) - 1)
            joints.append((jn, idx))
        if not joints:
            print(f"  {c['name']}: no joint moves, skipped")
            continue
        m = struct.pack("<I4fI", sid(c["name"]), t0, t1, t0, t1, len(joints))
        for jn, idx in joints:
            m += struct.pack("<II", sid(jn), len(idx)) + struct.pack(f"<{len(idx)}I", *idx)
        marks.append(m)
        njref += len(joints)
        ncref += 6 * len(joints)
        print(f"  {c['name']}: {t0:.3f}-{t1:.3f} s, joints {', '.join(j for j, _ in joints)}")
    body = (b"MAD " + chunk(b"NAME", b"Homeworld2 MAD File") + chunk(b"VERS", bytes([4, 1, 0, 0]))
            + chunk(b"INFO", struct.pack("<5I", FPS, len(marks), len(curves), njref, ncref))
            + chunk(b"STRI", bytes(stri)) + chunk(b"MARK", b"".join(marks)) + chunk(b"CURV", b"".join(curves)))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "wb") as f:
        f.write(chunk(b"FORM", body))
    print(f"{a.out}: {len(marks)} clips, {len(curves)} curves")


if __name__ == "__main__":
    main()
