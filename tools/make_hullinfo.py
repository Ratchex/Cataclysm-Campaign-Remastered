"""Hull sizes and salvage points per ship type, for the Ramming Frigate (shiprules.lua CatRam_*: where its nose meets a
target's hull, and the box other ships are shoved out of while it pushes; user: hold distance per hull).

From each type's .hod (ours in data/ship, else stock HWRM's in the reference copy):
  BBOX  6 floats (min xyz, max xyz), HWRM model space, outside the compressed POOL; our HODOR models have none: their meshes' box
  HIER  joints: SalvagePoint* (the latch points, parented to Root): stock HWRM's layout (name, parent, 9 floats:
        position, rotation, joint orient) or an older one (name, parent, 12 floats, 3 bytes)
-> data/scripts/cataclysm/hullinfo_gen.lua: CatHull[type] = { box = {x0, y0, z0, x1, y1, z1}, sp = { {x, y, z}, ... } }

Usage: python tools/make_hullinfo.py  (then install_base.py is not needed: the file is ours, under data/)
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = r"C:\Modding\Cataclysm-decomp\reference"
STOCK = [os.path.join(REF, "hwrm", "HW1Ships", "ship"), os.path.join(REF, "hwrm", "Homeworld2", "ship")]
OUT = os.path.join(MOD, "data", "scripts", "cataclysm", "hullinfo_gen.lua")


def bbox(d):
    i = d.find(b"BBOX")
    if i < 0 or struct.unpack_from(">I", d, i + 4)[0] != 24:
        return None
    return struct.unpack_from("<6f", d, i + 8)


def joints(d):
    """{name: (parent, position)} from HIER, whichever layout reads as joint names"""
    i = d.find(b"HIER")
    if i < 0:
        return {}
    for start, nfloat, extra in ((i + 8, 9, 0), (i + 12, 12, 3)):
        out, p, ok = {}, start, True
        for _ in range(4096):
            if p + 8 > len(d):
                break
            n = struct.unpack_from("<I", d, p)[0]
            if not 0 < n < 80:
                break
            name = d[p + 4:p + 4 + n]
            if not re.fullmatch(rb"[ -~]+", name):
                ok = False
                break
            p += 4 + n
            m = struct.unpack_from("<I", d, p)[0]
            if m > 80:
                ok = False
                break
            par = d[p + 4:p + 4 + m].decode("latin-1")
            p += 4 + m
            v = struct.unpack_from(f"<{nfloat}f", d, p)
            p += 4 * nfloat + extra
            out[name.decode("latin-1")] = (par, v[:3])
        if ok and "Root" in out and len(out) > 1:
            return out
    return {}


def mesh_bbox(path):
    """the bounding box of a model's LOD 0 meshes in model space (tools/hodread.py, joints as tools/hod2dae.py): our
    HODOR-built models carry no BBOX (the Processor, Acolyte... were missing, so meteor hits never measured them)"""
    import numpy as np
    import hodread
    import hod2dae
    model = hodread.read(path)
    world = hod2dae.world_frames(model)
    lo, hi = None, None
    for mesh in model.meshes:
        R, T = world(mesh["parent"])
        for part in mesh["lods"].get(0, []):
            if not part["pos"]:
                continue
            P = np.array(part["pos"]) @ R.T + T
            lo = P.min(0) if lo is None else np.minimum(lo, P.min(0))
            hi = P.max(0) if hi is None else np.maximum(hi, P.max(0))
    return None if lo is None else tuple(float(c) for c in list(lo) + list(hi))


def find_hod(t):
    """the type's .hod and its bounding box: ours (data/ship), else stock's"""
    for folder in [os.path.join(MOD, "data", "ship")] + STOCK:
        f = os.path.join(folder, t, t + ".hod")
        if os.path.exists(f):
            box = bbox(open(f, "rb").read())
            if box is None and folder == os.path.join(MOD, "data", "ship"):
                box = mesh_bbox(f)
            if box:
                return f, box
    return None, None


def ship_regen(t):
    """the type's regentime (seconds to regenerate from nothing to full; cataclysmkas.lua KAS_NoRegen cancels it
    where Cataclysm sets a ship's repair factor to 0)"""
    for folder in [os.path.join(MOD, "data", "ship")] + STOCK:
        f = os.path.join(folder, t, t + ".ship")
        if os.path.exists(f):
            m = re.search(r"regentime\s*=\s*(?:getShipNum\([^,]*,[^,]*,\s*)?([\d.]+)", open(f, encoding="latin-1").read())
            return float(m.group(1)) if m else 0
    return 0


def main():
    types = sorted(d for d in os.listdir(os.path.join(MOD, "data", "ship"))
                   if os.path.isdir(os.path.join(MOD, "data", "ship", d)))
    for folder in STOCK:
        if os.path.isdir(folder):
            types += [d for d in os.listdir(folder) if os.path.isdir(os.path.join(folder, d))]
    lines, n_sp = [], 0
    for t in sorted(set(types)):
        f, box = find_hod(t)
        if not f:
            continue
        d = open(f, "rb").read()
        js = joints(d)
        sp = [pos for name, (par, pos) in sorted(js.items()) if re.fullmatch(r"SalvagePoint\d+", name) and par == "Root"]
        n_sp += bool(sp)
        b = ", ".join(f"{c:.1f}" for c in box)
        s = ", ".join("{" + ", ".join(f"{c:.1f}" for c in p) + "}" for p in sp)
        regen = ship_regen(t)
        r = f", regen = {regen:g}" if regen else ""
        lines.append(f'CatHull["{t}"] = {{ box = {{ {b} }}, sp = {{ {s} }}{r} }}')
    with open(OUT, "w", newline="\n") as fh:
        fh.write("-- Generated by tools/make_hullinfo.py: per ship type its HOD bounding box (min xyz, max xyz) and salvage\n"
                 "-- points (HWRM model space), for the Ramming Frigate (shiprules.lua CatRam_*); regen: its .ship regentime\n"
                 "CatHull = {}\n" + "\n".join(lines) + "\n")
    print(f"{os.path.relpath(OUT, MOD)}: {len(lines)} ship types, {n_sp} with salvage points")


if __name__ == "__main__":
    main()
