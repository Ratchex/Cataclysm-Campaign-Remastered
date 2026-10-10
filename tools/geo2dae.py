"""Convert a Cataclysm ship model (.geo, LOD0) to a HODOR-ready Collada file and build the .hod with HODOR.

Input:  Cataclysm-decomp/extracted/big/<race>/<ship>/rl0/lod0/<ship>.geo  (parsed with geo2obj.parse)
        Cataclysm-decomp/extracted/textures/<same dir>/<texture>.png (+ _team0/_team1 masks from lif2png.py)
Output: <out_dir>/<name>.dae, <name>_<tex>_DIFF.tga / _TEAM.tga next to it, and <out_dir>/<name>.hod

Coordinates: HW1 models are X up, Y right, Z forward; HODOR wants Y up, Z forward. HWRM = 0.35 * (-y, x, z)
(0.35 = the same factor Gearbox used for HW1 levels and ship sizes, see NOTES.md); a proper rotation, so winding
is kept. Objects are baked into JNT[Root], except animated parts (--anim-joints: each under its own joint, driven
by tools/mad2hwrm.py's converted .mad).
Materials: MAT[<tex>]_SHD[ship] with image IMG[<name>_<tex>_DIFF] (id ...-image); the Somtaaw colours are baked into
the DIFF (write_textures), no team mask files.

Usage: geo2dae.py <geo> <out_dir> <name> [--scale 0.35]   (tools/build_ship.sh runs it, then HODOR)
HODOR quirks: it must be started from Git Bash (from Python or PowerShell it spins forever), with forward-slash
paths; textures must be square powers of two >= 64; image ids must be IMG[x]-image.
"""
import argparse
import itertools
import math
import re
import os
import struct
import sys

import numpy as np
from PIL import Image

DECOMP = r"C:\Modding\Cataclysm-decomp"
sys.path.insert(0, os.path.join(DECOMP, "tools"))
import geo2obj  # noqa: E402

HODOR = r"C:\Program Files (x86)\Steam\steamapps\common\Homeworld 347380\GBXTools\HODOR"


def pow2(n):
    p = 1
    while p < n:
        p *= 2
    return p


# Somtaaw colour scheme 0 (Cataclysm teamcolors.script: BaseColor 66 108 202, StripeColor 255 255 255)
BAKE_BASE, BAKE_STRIPE = (66, 108, 202), (255, 255, 255)


def write_textures(png_dir, tex, out_dir, base, colour, bake=None):
    """Write <base>_DIFF.tga with the team / stripe colours baked in (bake: (base, stripe) RGB 0-255, default
    Somtaaw's; the Mimic's disguises take their faction's); return the DIFF file name.

    Cataclysm (HW1 texreg.c trBufferColorRGB, Somtaaw scalar 1: colpick.script has curves for the Taiidan only)
    paints texel = texel x (1 - team mask) + base x team mask, then the same with the stripe mask and colour: grey
    hull, blue panels, white bands. Baked here (Somtaaw's own colours: only the Somtaaw player uses these models)
    because HWRM team masks through HODOR (<x>_TEAM / _STRP.tga -> $team) went wrong three ways in game (whole hulls
    blue or white, no stripes) and HODOR's POOL can't be read back to check (RODOH reads HW2 Classic HODs only).
    """
    src = os.path.join(png_dir, tex.lower() + ".png") if tex else None
    if src and os.path.exists(src):
        im = Image.open(src).convert("RGB")
    else:
        im = Image.new("RGB", (4, 4), colour)
    # HODOR loops forever building mips for small or non-square textures: square, power of two, at least 64.
    n = max(64, pow2(im.width), pow2(im.height))
    size = (n, n)
    im = im.resize(size) if size != im.size else im
    if src:
        for k, c in enumerate(bake or (BAKE_BASE, BAKE_STRIPE)):
            m = os.path.join(png_dir, f"{tex.lower()}_team{k}.png")
            if os.path.exists(m):
                im = Image.composite(Image.new("RGB", size, c), im, Image.open(m).convert("L").resize(size))
    for old in ("_TEAM.tga", "_STRP.tga", "_GLOW.tga"):   # HODOR picks up any such file next to the DIFF
        if os.path.exists(os.path.join(out_dir, base + old)):
            os.remove(os.path.join(out_dir, base + old))
    glow = GLOW_MAPS.get(tex.lower()) if tex else None
    if glow is not None:
        # sob_ship.frag: $glow G = self-illumination mask (R spec sharpness, B spec mask). The mask goes in all three
        # channels: with G alone the glow barely showed in game (HODOR may fill $glow G from another source channel)
        g = Image.fromarray(glow).resize(size)
        Image.merge("RGB", (g, g, g)).save(os.path.join(out_dir, base + "_GLOW.tga"))
        # glowing texels emit the diffuse x a global strength: brighten it under the mask, keeping its colour (user:
        # the hangars needed more glow; lifting toward white was too white; then 1.35 a little bright, 1.25 still: user). Not the engines' (user: keep those).
        if not GLOW_KEEP.match(tex.lower()):
            m = np.asarray(g, np.float32)[..., None] / 255
            im = Image.fromarray(np.clip(np.asarray(im, np.float32) * (1 + (GLOW_BOOST - 1) * m), 0, 255)
                                 .astype(np.uint8))
    im.save(os.path.join(out_dir, base + "_DIFF.tga"))
    return base + "_DIFF.tga"


FX_TILE = 128                                  # --fx-mesh: atlas cell size per texture page
GLOW_BOOST = 1.05                             # diffuse multiplier under a full glow mask
GLOW_KEEP = re.compile(r"smo_eng(up|lwr)_")    # engine module textures: their glow is right as is


GLOW_MAPS = {}   # Cataclysm texture name (lower case) -> glow mask (uint8 array), from --glow-from


def load_glow_maps(hod, cache_dir):
    """CR's GLOW textures (G channel) by Cataclysm texture name: "SMO_com_antenna_EXPORT[1]_GLOW" / "SWKcap_1_GLOW"
    -> smo_com_antenna / swkcap. Decoded once into cache_dir (the hod is 20 MB of DXT)."""
    import hodtex
    os.makedirs(cache_dir, exist_ok=True)
    stamp = os.path.join(cache_dir, "_done")
    if not os.path.exists(stamp):
        for name, img in hodtex.textures(hod, r"_GLOW$").items():
            key = re.sub(r"(_EXPORT\[\d+\]|_\d+)?_GLOW$", "", name, flags=re.I).lower()
            Image.fromarray(img[..., 1].clip(0, 255).astype("uint8")).save(os.path.join(cache_dir, key + ".png"))
        open(stamp, "w").close()
    for f in os.listdir(cache_dir):
        if f.endswith(".png"):
            GLOW_MAPS[f[:-4]] = np.asarray(Image.open(os.path.join(cache_dir, f)).convert("L"))


def fl(vals):
    return " ".join("%.6g" % v for v in vals)



# ----------------------------------------------------------------------------------------------- .mex extras
def read_mex(path):
    """HW1 Game/MEX.h: header ident[8], version u16, nChunks u16; chunks: type[4], name[8], size (body bytes),
    body. Gun/Eng/Dok bodies start with position, normal (HW1 model space); Dok bodies end with a 20-byte name."""
    out = []
    if not os.path.exists(path):
        return out
    b = open(path, "rb").read()
    n = struct.unpack_from("<H", b, 10)[0]
    p = 12
    for _ in range(n):
        typ, name, size = struct.unpack_from("<4s8sI", b, p)
        body = b[p + 16:p + 16 + size]
        typ = typ.split(b"\0")[0].decode("latin-1")
        if typ in ("Gun", "Eng", "Dok") and len(body) >= 24:
            pos = struct.unpack_from("<3f", body, 0)
            nrm = struct.unpack_from("<3f", body, 12)
            label = name.split(b"\0")[0].decode("latin-1")
            if typ == "Dok" and len(body) >= 52:
                label = body[32:52].split(b"\0")[0].decode("latin-1")
            parent = ""
            if typ == "Eng" and len(body) >= 48:   # Cataclysm: optional object the nozzle is attached to
                raw = body[32:48].split(b"\0")[0]
                if raw and all(32 <= c < 127 for c in raw):
                    parent = raw.decode("latin-1")
            out.append((typ, label, pos, nrm, parent))
        elif typ == "Nav" and len(body) >= 36:
            # MEX.h MEXNAVLightChunk: position, red, BLUE, green, pad, name[20] (the .shp NavLight's name, any case)
            pos = struct.unpack_from("<3f", body, 0)
            r, b_, g = body[12], body[13], body[14]
            label = body[16:36].split(b"\0")[0].decode("latin-1")
            out.append((typ, label, pos, (r / 255, g / 255, b_ / 255), path))
        p += 16 + size
    return out


def jnode(name, xyz, children="", rot=None):
    """Joint node; rot = (rx, ry, rz) degrees, composed Z * Y * X (HODOR's order, as the .mad rotate channels)."""
    r = "" if rot is None else (f'<rotate sid="rotateZ">0 0 1 {rot[2]:.5f}</rotate><rotate sid="rotateY">0 1 0 '
                                f'{rot[1]:.5f}</rotate><rotate sid="rotateX">1 0 0 {rot[0]:.5f}</rotate>')
    return (f'<node name="{name}" id="{name}" sid="{name}E"><translate sid="translate">{fl(xyz)}</translate>{r}'
            f'{children}</node>')


# Animated parts (Cataclysm .mad objects) become joints so tools/mad2hwrm.py can drive them: their meshes hang
# under JNT[<object name without brackets>] in the object's own frame. HW1 -> HWRM axes: v' = C v (conv without
# the scale), so a local matrix becomes C R C^T with translation C t * scale.
C3 = ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))


def joint_name(obj):
    return re.sub(r"[^A-Za-z0-9_]", "", obj)


def rigid_inverse(m):
    """Inverse of a column-major 4x4 rotation + translation."""
    r = [[m[c * 4 + k] for c in range(3)] for k in range(3)]          # r[row][col]
    t = m[12:15]
    out = [0.0] * 16
    for row in range(3):
        for col in range(3):
            out[col * 4 + row] = r[col][row]
        out[12 + row] = -sum(r[k][row] * t[k] for k in range(3))
    out[15] = 1.0
    return out


def hwrm_local(m, scale):
    """Column-major HW1 local matrix -> (HWRM translation, row-major HWRM rotation)."""
    r = [[m[c * 4 + k] for c in range(3)] for k in range(3)]
    cr = [[sum(C3[i][k] * r[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    rot = [[sum(cr[i][k] * C3[j][k] for k in range(3)) for j in range(3)] for i in range(3)]   # C R C^T
    t = [sum(C3[i][k] * m[12 + k] for k in range(3)) * scale for i in range(3)]
    return t, rot


def euler_deg(rot):
    from nis2hwrm import matrix_to_euler_xyz
    return tuple(math.degrees(a) for a in matrix_to_euler_xyz(rot))


def joint_frames(objs, names):
    """For the objects named (animated parts): {object index: (joint parent index or None, local matrix)}, the local
    matrix relative to the nearest animated ancestor (None: the model root, i.e. the object's world matrix)."""
    cache = {}
    idx = {i for i, o in enumerate(objs) if o["name"] in names}
    out = {}
    for i in idx:
        p = objs[i]["parent"]
        while p is not None and p not in idx:
            p = objs[p]["parent"]
        W = geo2obj.world(objs, i, cache)
        out[i] = (p, W if p is None else geo2obj.matmul(rigid_inverse(geo2obj.world(objs, p, cache)), W))
    return out


# Dock paths built from Cataclysm dock points (distances in HW1 units, scaled with the model):
# entry = approach along the point's normal, then onto the point; exit = the reverse.
DOCK_KINDS = [  # (dock point name prefix, HWRM dock family, path flags, approach distances)
    ("RES", "Utility", "Latch", (1200, 350)),
    ("DBSMALLIN", "Fighter", "", (900, 250)),
    ("DBMEDIN", "Corvette", "", (1200, 350)),
]
# Hangar paths also line up from well outside the Kuun-Lan's docking bay (the module is a ~480-unit box under the
# core with the dock points inside it): with only the near approach (~315 HWRM units out, at the box's corner) ships
# flew straight through the box to reach it, and launched ships turned back through it. Cataclysm Remastered's
# fighter / corvette paths start ~1100 units out.
OUTER_APPROACH = {"Fighter": 2400, "Corvette": 2800}
EXIT_OF = {"DBSMALLIN": "DBSMALLOUT", "DBMEDIN": "DBMEDOUT"}
LATCH_OFFSET = 45   # collector latch waypoint off the dock point along its normal (HW1 units; ~16 HWRM)


def dock_nodes(points, conv, extra="", skip=()):
    """HOLD_DOCK with DOCK[...] paths (HODOR naming: DOCK[name]_Fam[]_Link[]_Flags[]_MAD[];
    SEG[i]_Tol[]_Spd[]_Flags[])."""
    def seg(i, xyz, tol, spd, flags, rot=None):
        if rot is None:
            return jnode(f"SEG[{i}]_Tol[{tol}]_Spd[{spd}]_Flags[{flags}]", xyz)
        name = f"SEG[{i}]_Tol[{tol}]_Spd[{spd}]_Flags[{('UseRot ' + flags).strip()}]"
        return (f'<node name="{name}" id="{name}" sid="{name}E"><translate sid="translate">{fl(xyz)}</translate>'
                f'<rotate sid="rotateZ">0 0 1 {rot[2]:.4f}</rotate><rotate sid="rotateY">0 1 0 {rot[1]:.4f}</rotate>'
                f'<rotate sid="rotateX">1 0 0 {rot[0]:.4f}</rotate></node>')

    def latch_rotation(pos, nrm):
        """Collector orientation at a dock point (degrees, Z*Y*X): its top along the point's outward normal, so the
        clamps underneath face the hull, nose towards the ship's top (or front when the normal is vertical) - the
        orientation of Cataclysm Remastered's Kuun-Lan collector paths, which need it (UseRot) to latch."""
        a, b = conv(*pos), conv(*(pos[k] + nrm[k] for k in range(3)))
        up = [b[k] - a[k] for k in range(3)]
        ln = math.sqrt(sum(c * c for c in up)) or 1.0
        up = [c / ln for c in up]
        ref = (0.0, 1.0, 0.0) if abs(up[1]) < 0.9 else (0.0, 0.0, 1.0)
        dot = sum(ref[k] * up[k] for k in range(3))
        fwd = [ref[k] - dot * up[k] for k in range(3)]
        ln = math.sqrt(sum(c * c for c in fwd))
        fwd = [c / ln for c in fwd]
        side = [up[1] * fwd[2] - up[2] * fwd[1], up[2] * fwd[0] - up[0] * fwd[2], up[0] * fwd[1] - up[1] * fwd[0]]
        m = [[side[r], up[r], fwd[r]] for r in range(3)]       # columns: the collector's x, y, z in ship space
        ry = math.asin(max(-1.0, min(1.0, -m[2][0])))
        if abs(m[2][0]) < 0.9999:
            rx = math.atan2(m[2][1], m[2][2])
            rz = math.atan2(m[1][0], m[0][0])
        else:   # gimbal lock (sideways normals, ry = +-90): the roll goes into X, Z = 0
            rz = 0.0
            rx = math.atan2(m[0][1] if ry > 0 else -m[0][1], m[1][1])
        return tuple(math.degrees(v) for v in (rx, ry, rz))

    def along(pos, nrm, d):
        return conv(*(pos[k] + nrm[k] * d for k in range(3)))

    docks = {lbl: (pos, nrm) for typ, lbl, pos, nrm, _ in points if typ == "Dok"}
    paths = []
    for prefix, fam, flags, (far, near) in DOCK_KINDS:
        if prefix in skip:
            continue
        for lbl in sorted(l for l in docks if l.startswith(prefix)):
            if prefix == "RES" and not re.match(r"RES\d+$", lbl):
                continue                                   # RESLEECH*: Beast attachment points
            pos, nrm = docks[lbl]
            exit_lbl = None
            if prefix in EXIT_OF:   # DBSMALLINP0 leaves by DBSMALLOUTP0, else the first exit on that side
                side = lbl[len(prefix):]
                cands = sorted(l for l in docks if l.startswith(EXIT_OF[prefix]))
                exit_lbl = next((l for l in cands if l[len(EXIT_OF[prefix]):] == side), None) or \
                    next((l for l in cands if l[len(EXIT_OF[prefix]):].rstrip("0123456789") == side.rstrip("0123456789")), None)
            name = lbl.title()
            ex_name = name + "Ex"
            # Waypoint flags as in kus_mothership.hod (decoded with a HODOR flag test): queue/player control on the
            # approach, ClearRes at the dock point (collectors latch there, fighters are clipped into the hold).
            # Collectors (Utility) instead follow Cataclysm Remastered's Kuun-Lan, which their Workers unload at:
            # Check+Queue on the approach, Close leaving, no Player/ClearRes, tolerance 50, oriented waypoints (UseRot,
            # latch_rotation): with the stock flags they never unloaded, without rotations they stopped short.
            rot = latch_rotation(pos, nrm) if fam == "Utility" else None
            if fam == "Utility":
                # the waypoint is the collector's centre: off the hull by about its half-height (Worker clamps 14.4
                # below centre; CR's nose latch is ~28 off the hull), not on the Cataclysm dock point itself
                entry = (seg(0, along(pos, nrm, far), 50, 0, "Check Queue", rot) + seg(1, along(pos, nrm, near), 50, 0, "", rot)
                         + seg(2, along(pos, nrm, LATCH_OFFSET), 50, 0, "", rot))
            else:
                outer = OUTER_APPROACH.get(fam)
                pre = [(along(pos, nrm, outer), 60, 250)] if outer else []
                way = pre + [(along(pos, nrm, far), 25, 200), (along(pos, nrm, near), 25, 120)]
                entry = "".join(seg(i, p, tol, spd, "Player Queue" if i == 0 else "Player")
                                for i, (p, tol, spd) in enumerate(way))
                entry += seg(len(way), conv(*pos), 25, 50, "Clip ClearRes")
            # Stock HW1 Kushan paths (kus_mothership.hod): MAD 0 (an invalid -1 crashed the level load), empty links,
            # Exit on the way out, Latch on both ways for collectors.
            paths.append(jnode(f"DOCK[{name}]_Fam[{fam}]_Link[]_Flags[{flags}]_MAD[0]", (0, 0, 0), entry))
            epos, enrm = docks[exit_lbl] if exit_lbl else (pos, nrm)
            if fam == "Utility":
                exitp = (seg(0, along(epos, enrm, LATCH_OFFSET), 50, 0, "", rot) + seg(1, along(epos, enrm, near), 50, 0, "Close", rot)
                         + seg(2, along(epos, enrm, far), 50, 0, "", rot))
            else:
                exitp = (seg(0, conv(*epos), 25, 50, "") + seg(1, along(epos, enrm, near), 25, 150, "")
                         + seg(2, along(epos, enrm, far), 50, 200, ""))
                if OUTER_APPROACH.get(fam):    # leave all the way out before turning (see OUTER_APPROACH)
                    exitp += seg(3, along(epos, enrm, OUTER_APPROACH[fam]), 60, 250, "")
            paths.append(jnode(f"DOCK[{ex_name}]_Fam[{fam}]_Link[]_Flags[{(flags + ' Exit').strip()}]_MAD[0]",
                               (0, 0, 0), exitp))
    if not paths and not extra:
        return "", 0
    return jnode("HOLD_DOCK", (0, 0, 0), "".join(paths) + extra), len(paths) // 2


SEG_FLAGS = ("Check", "Close", "Player", "Queue", "Clip", "ClearRes")


def read_hod_docks(path):
    """DOCK chunk of a HOD: [(name, exit, latch, families, [(pos, rot, useRot, tol, unfocus, spd, flags...)])].
    Path: name, parent, u32 6, u32 10, u32 exit, u32 latch, u32 0, families, links, i32 MAD, u32 segments;
    segment (64 B): pos 3f, rot 3f (radians), u32 useRot, f tol, u32 unfocus, f speed, u32 x6 SEG_FLAGS."""
    d = open(path, "rb").read()
    o = d.index(b"DOCK") + 8
    n, = struct.unpack_from("<I", d, o)
    o += 4

    def s():
        nonlocal o
        k, = struct.unpack_from("<I", d, o)
        o += 4 + k
        return d[o - k:o].decode("latin-1")
    out = []
    for _ in range(n):
        name, _parent = s(), s()
        _, _, ex, latch, _ = struct.unpack_from("<5I", d, o)
        o += 20
        fam, _links = s(), s()
        _mad, nseg = struct.unpack_from("<iI", d, o)
        o += 8
        segs = []
        for _ in range(nseg):
            segs.append(struct.unpack_from("<3f3fIfIfIIIIII", d, o))
            o += 64
        out.append((name, ex, latch, fam, segs))
    return out


def borrowed_dock_nodes(path, scale, family, anchors=()):
    """Dock paths copied from another model (positions scaled), those whose families include `family`:
    SEG[i]_Tol[]_Spd[]_Flags[] joints rotated as the source waypoints (Z*Y*X, as HODOR stores them).
    With anchors (latch points on this model), each latching path moves whole so its latch point lands on an
    anchor (in and out paths share the point, so a pair moves together; anchors assigned for the least travel)."""
    docks = [d for d in read_hod_docks(path) if family.lower() in d[3].lower()]
    shift = {}
    if anchors:
        keys = sorted({tuple(round(c * scale, 3) for c in (segs[-1] if not ex else segs[0])[0:3])
                       for _, ex, latch, _, segs in docks if latch and segs})
        dist = lambda a, b: math.sqrt(sum((a[k] - b[k]) ** 2 for k in range(3)))
        best = min(itertools.permutations(range(len(anchors)), len(keys)),
                   key=lambda perm: sum(dist(keys[i], anchors[j]) for i, j in enumerate(perm)))
        shift = {k: tuple(anchors[j][c] - k[c] for c in range(3)) for k, j in zip(keys, best)}
    nodes = []
    for name, ex, latch, fam, segs in docks:
        key = tuple(round(c * scale, 3) for c in (segs[-1] if not ex else segs[0])[0:3]) if segs else None
        dx = shift.get(key, (0, 0, 0)) if latch else (0, 0, 0)
        kids = ""
        for i, v in enumerate(segs):
            pos, rot, use_rot, tol, unfocus, spd = v[0:3], v[3:6], v[6], v[7], v[8], v[9]
            pos = tuple(pos[c] + dx[c] / scale for c in range(3))
            flags = (["UseRot"] if use_rot else []) + (["Unfocus"] if unfocus else []) + \
                [f for f, on in zip(SEG_FLAGS, v[10:]) if on]
            sname = f"SEG[{i}]_Tol[{tol:g}]_Spd[{spd:g}]_Flags[{' '.join(flags)}]"
            kids += (f'<node name="{sname}" id="{name}_{sname}" sid="{name}_{i}E">'
                     f'<translate sid="translate">{fl([c * scale for c in pos])}</translate>'
                     f'<rotate sid="rotateZ">0 0 1 {math.degrees(rot[2]):.4f}</rotate>'
                     f'<rotate sid="rotateY">0 1 0 {math.degrees(rot[1]):.4f}</rotate>'
                     f'<rotate sid="rotateX">1 0 0 {math.degrees(rot[0]):.4f}</rotate></node>')
        pflags = " ".join(f for f, on in (("Exit", ex), ("Latch", latch)) if on)
        nodes.append(jnode(f"DOCK[{name}]_Fam[{fam}]_Link[]_Flags[{pflags}]_MAD[0]", (0, 0, 0), kids))
    return "".join(nodes), len(nodes)


def shp_navlights(mex_path):
    """The .shp NavLight lines of the ship a .mex belongs to (<race>/<ship>/rl0/lod0/<ship>.mex -> <race>/<ship>.shp):
    name (lower case) -> (blink on s, off s, start delay s, size HW1 units)."""
    d = os.path.dirname(os.path.dirname(os.path.dirname(mex_path)))
    shp = os.path.join(os.path.dirname(d), os.path.basename(d) + ".shp")
    out = {}
    if os.path.exists(shp):
        for line in open(shp, encoding="latin-1"):
            m = re.match(r"\s*NavLight\s+(.*)", line.split(";")[0])
            if m:
                f = [x.strip() for x in m.group(1).split(",")]
                if len(f) >= 6:
                    try:
                        out[f[0].lower()] = (float(f[2]), float(f[3]), float(f[4]), float(f[5]))
                    except ValueError:
                        pass
    return out


def navlight_nodes(points, conv, scale):
    """Cataclysm nav lights (.mex Nav chunks: position, colour; .shp NavLight: blink on/off, delay, size) as HODOR
    NAVL joints: NAVL[name]_Type[default]_Sect[0]_Sz[]_Ph[]_Fr[]_Dist[0]_Col[r,g,b]_Flags[Sprite] (the keys
    HODOR.exe parses, in its order; Cataclysm Remastered's Kuun-Lan NAVL chunk: size 16, freq 0.75, phase 0, dist 0,
    sprite on). Size x the model scale; frequency = 1 / (on + off); phase = start delay / period."""
    out, used, shps = [], set(), {}
    for typ, lbl, pos, col, mex in points:
        if typ != "Nav":
            continue
        if mex not in shps:
            shps[mex] = shp_navlights(mex)
        on, off, delay, size = shps[mex].get(lbl.lower(), (1.0, 1.0, 0.0, 30.0))
        period = max(on + off, 0.01)
        stem = re.sub(r"\W", "", lbl) or "Nav"
        name, k = stem, 1
        while name in used:
            k += 1
            name = f"{stem}_{k}"
        used.add(name)
        tag = (f"NAVL[{name}]_Type[default]_Sect[0]_Sz[{size * scale:.4g}]_Ph[{(delay / period) % 1:.4g}]"
               f"_Fr[{1 / period:.4g}]_Dist[0]_Col[{col[0]:.3g},{col[1]:.3g},{col[2]:.3g}]_Flags[Sprite]")
        out.append(jnode(tag, conv(*pos)))
    return "".join(out), len(out)


def hod_engines(path):
    """Engine nozzles and shapes of an old-format HWRM .hod (Cataclysm Remastered's smt_ms_sp): [(nozzle joint name,
    world position, [(shape name, [vertex, ...])])]. HIER: u32 count, per joint name, parent (u32-length strings),
    position 3f, rotation 3f, scale 3f, axis 3f, 3 flag bytes; ETSH: name, parent joint, u32 count, vertices 3f
    (local to the parent). Joint rotations on the way are zero in CR's Kuun-Lan (only translations are summed)."""
    d = open(path, "rb").read()

    def lstr(p):
        n = struct.unpack_from("<I", d, p)[0]
        return d[p + 4:p + 4 + n].decode("latin-1"), p + 4 + n
    joints = {}
    i = d.find(b"HIER")
    if i >= 0:
        n, p = struct.unpack_from("<I", d, i + 8)[0], i + 12
        for _ in range(min(n, 4096)):
            name, p = lstr(p)
            parent, p = lstr(p)
            v = struct.unpack_from("<12f", d, p)
            p += 51
            joints[name] = (parent, v[:3], v[3:6])

    def world(name):
        x, seen = [0.0, 0.0, 0.0], set()
        while name in joints and name not in seen:
            seen.add(name)
            parent, t, r = joints[name]
            if any(abs(c) > 1e-6 for c in r):
                sys.exit(f"--engines-from: joint {name} is rotated; only translations are handled")
            x = [x[k] + t[k] for k in range(3)]
            name = parent
        return tuple(x)
    shapes = {}
    for m in re.finditer(rb"ETSH", d):
        p = m.start() + 8
        name, p = lstr(p)
        parent, p = lstr(p)
        n = struct.unpack_from("<I", d, p)[0]
        if not 0 < n < 64:
            continue
        shapes.setdefault(parent, []).append((name, [struct.unpack_from("<3f", d, p + 4 + 12 * k) for k in range(n)]))
    return [(nz, world(nz), shapes.get(nz, [])) for nz in sorted(n for n in joints if n.startswith("EngineNozzle"))]


def weapon_nodes(points, conv, convn):
    """JNT[Weapon_<GUNn>_Position] with _Direction (up), _Rest (firing direction), _Muzzle children (the layout of
    the HWRM Blender toolkit's hardpoint tool); the position joint itself is not rotated."""
    out = []
    for typ, lbl, pos, nrm, _ in points:
        if typ != "Gun":
            continue
        n = convn(*nrm)
        ln = math.sqrt(sum(c * c for c in n)) or 1.0
        n = tuple(c / ln for c in n)
        up = (0.0, 1.0, 0.0) if abs(n[1]) < 0.9 else (1.0, 0.0, 0.0)
        base = f"Weapon_{lbl}"
        kids = (jnode(f"JNT[{base}_Direction]", tuple(10 * c for c in up))
                + jnode(f"JNT[{base}_Rest]", tuple(10 * c for c in n))
                + jnode(f"JNT[{base}_Muzzle]", tuple(0.1 * c for c in n)))
        out.append(jnode(f"JNT[{base}_Position]", conv(*pos), kids))
    return "".join(out), len(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("geo")
    ap.add_argument("out_dir")
    ap.add_argument("name")
    ap.add_argument("--scale", type=float, default=0.35)
    ap.add_argument("--no-hodor", action="store_true")
    ap.add_argument("--dock-from", help="take the collector (Utility) dock paths from this HOD instead of RES*")
    ap.add_argument("--dock-scale", type=float, default=1.0, help="position scale for --dock-from paths")
    ap.add_argument("--hardpoint", action="append", default=[],
                    help="extra subsystem hardpoint joint set: NAME at the origin, NAME@x,y,z (HWRM units), "
                         "NAME@dok:LABEL (at that .mex dock point) or NAME@gun:LABEL (at that gun point, facing its "
                         "firing direction: weapon subsystems); a trailing @flip turns it 180 degrees about Y")
    ap.add_argument("--points-from", action="append", default=[],
                    help="another .geo whose .mex guns/engines are added (Kuun-Lan engine modules' nozzles)")
    ap.add_argument("--no-docks", action="store_true", help="no dock paths (module subsystems)")
    ap.add_argument("--merge", nargs="*", default=[],
                    help="more .geo files baked into the same mesh (Kuun-Lan modules share the core's frame)")
    ap.add_argument("--anim-joints", default="",
                    help="comma-separated objects that get their own joint (parts animated by tools/mad2hwrm.py)")
    ap.add_argument("--marker", action="append", default=[],
                    help="effect marker joint NAME@OBJECT@x,y,z[@rx,ry,rz] (HW1 units in that animated object's "
                         "frame; pointing along its +Z, or turned by those HWRM degrees, Z*Y*X) or NAME@gun:LABEL "
                         "(at that .mex gun point, pointing forward) or NAME@x,y,z (fixed, HWRM units, pointing "
                         "forward)")
    ap.add_argument("--weapon", action="append", default=[],
                    help="extra weapon hardpoint Weapon_NAME (_Position / _Direction / _Rest / _Muzzle): "
                         "NAME@x,y,z@dx,dy,dz (HWRM units, firing along d) or NAME@dok:LABEL@dx,dy,dz (at that "
                         ".mex dock point): the Worker's and Processor's repair beams")
    ap.add_argument("--latch", help="LatchOrientation joint at x,y,z (HWRM units): the point a collector puts on "
                                    "the asteroid's surface while harvesting")
    ap.add_argument("--glow-from", help="old-format HOD whose GLOW textures (Cataclysm texture names) become our "
                                        "_GLOW maps (Cataclysm Remastered's smt_ms_sp.hod for the Kuun-Lan)")
    ap.add_argument("--no-navlights", action="store_true", help="no NAVL joints from the .mex Nav chunks")
    ap.add_argument("--anim-geo", help="the .geo (the main one or a --merge one) whose objects --anim-joints names "
                                       "(the Kuun-Lan core's spinning grav_generator is in the merged command module)")
    ap.add_argument("--no-engines", action="store_true", help="no engine nozzles from the .mex Eng chunks")
    ap.add_argument("--engines-from", help="engine look from this old-format HOD (Cataclysm Remastered's smt_ms_sp.hod): "
                                           "its ETSH shape on our .mex nozzles")
    ap.add_argument("--engines-scale", type=float, default=1.0, help="size scale for --engines-from shapes")
    ap.add_argument("--retexture", action="append", default=[],
                    help="OLD=MODEL:NEW@u0,u1,v0,v1: faces textured OLD take MODEL's (race dir/model, e.g. "
                         "race_sect/smothershipenginesupper) texture NEW, their UV box u0-u1 x v0-v1 (HW1 UVs) "
                         "stretched over it (the Kuun-Lan's lower engine exhaust: the upper's glowing thruster, user)")
    ap.add_argument("--body", help="this ship's own meshes under a joint of this name (shown / hidden by the "
                                   ".madstate: the Mimic's body)")
    ap.add_argument("--part", action="append", default=[],
                    help="NAME@x.geo: another model's meshes under joint NAME at the origin (the Mimic's disguises)")
    ap.add_argument("--fx-mesh", action="store_true",
                    help="an effect mesh (STYLE_RING UseMesh): every triangle in one mesh with one plain white "
                         "material, no joints (the Mimic's shell, tools/make_mimicfx.py)")
    ap.add_argument("--origin", help="recentre the model on x,y,z (HWRM units) or 'auto' (its bounding box centre), "
                                     "written to <out_dir>/origin.txt: a Kuun-Lan module on a hardpoint there "
                                     "(HWRM draws a subsystem's health bar at its hardpoint)")
    a = ap.parse_args()
    retex = {}   # old texture (lower case) -> (png dir, new texture, (u0, u1, v0, v1))
    for spec in a.retexture:
        old, rest = spec.split("=", 1)
        model_tex, box = rest.split("@")
        model, new = model_tex.split(":")
        retex[old.lower()] = (os.path.join(DECOMP, "extracted", "textures", model.replace("/", os.sep), "rl0", "lod0"),
                              new, tuple(float(c) for c in box.split(",")))
    if a.glow_from:
        load_glow_maps(a.glow_from, os.path.join(os.path.dirname(os.path.abspath(a.out_dir)), "_glow_cache",
                                                 os.path.splitext(os.path.basename(a.glow_from))[0]))
    anim_names = {n for n in a.anim_joints.split(",") if n}
    os.makedirs(a.out_dir, exist_ok=True)
    rel = os.path.relpath(os.path.dirname(a.geo), os.path.join(DECOMP, "extracted", "big"))
    s = a.scale
    conv = lambda x, y, z: (-y * s, x * s, z * s)
    convn = lambda x, y, z: (-y, x, z)

    # Group triangles by texture (materials sharing a texture share one HWRM material).
    groups = {}   # key -> {"mat", "png_dir", "tris": [(positions[3], normals[3], uvs[3])]}
    flipped = total = 0
    extent = 0.0   # largest |coordinate| of the hull (HW1 units), sizes the engine glow quads
    frames = {}   # animated object index (in the --anim-geo .geo) -> (joint parent, local matrix)
    # [(joint name, .geo, (base, stripe) colours baked into its textures or None: Somtaaw's)]
    parts = []
    for p in a.part:
        f = p.split("@")
        parts.append((f[0], f[1], tuple(tuple(int(c) for c in x.split(",")) for x in f[2:4]) if len(f) > 3 else None))
    npre = 1 + len(a.merge)
    geos = [a.geo] + a.merge + [g for _, g, _ in parts]
    norm = lambda g: os.path.normcase(os.path.abspath(g))
    anim_gn = [norm(g) for g in geos].index(norm(a.anim_geo)) if a.anim_geo else 0
    for gn, geo in enumerate(geos):
        b, ver, mats, objs = geo2obj.parse(geo)
        png_dir = os.path.join(DECOMP, "extracted", "textures",
                               os.path.relpath(os.path.dirname(geo), os.path.join(DECOMP, "extracted", "big")))
        cache = {}
        if gn == anim_gn and anim_names:
            frames = joint_frames(objs, anim_names)
            missing = anim_names - {objs[i]["name"] for i in frames}
            if missing:
                sys.exit(f"--anim-joints: no such objects {sorted(missing)}")
            main_objs = objs
        for i, o in enumerate(objs):
            W = geo2obj.world(objs, i, cache)
            owner = None
            if gn == anim_gn and frames:
                owner = i
                while owner is not None and owner not in frames:
                    owner = objs[owner]["parent"]
            Wworld = W
            if owner is not None:     # vertices in the owning joint's frame
                W = geo2obj.matmul(rigid_inverse(geo2obj.world(objs, owner, cache)), W)
            f = struct.unpack_from(geo2obj.OBJ.format, b, 68 + i * geo2obj.OBJ.size)
            p_norm = f[10]
            verts = [struct.unpack_from("<fffi", b, o["pV"] + v * 16) for v in range(o["nV"])]
            for p in range(o["nP"]):
                ifn, i0, i1, i2, m, s0, t0, s1, t1, s2, t2, _ = geo2obj.POLY.unpack_from(b, o["pP"] + p * geo2obj.POLY.size)
                pos, nrm = [], []
                for vi in (i0, i1, i2):
                    x, y, z, ivn = verts[vi]
                    pos.append(geo2obj.xform(W, x, y, z))
                    extent = max(extent, *map(abs, geo2obj.xform(Wworld, x, y, z)))
                    nx, ny, nz = struct.unpack_from("<fff", b, p_norm + ivn * 16)
                    wx, wy, wz = (W[0] * nx + W[4] * ny + W[8] * nz, W[1] * nx + W[5] * ny + W[9] * nz,
                                  W[2] * nx + W[6] * ny + W[10] * nz)
                    nrm.append((wx, wy, wz))
                uv = [(s0, 1 - t0), (s1, 1 - t1), (s2, 1 - t2)]
                # Make the winding counter-clockwise around the stored face normal (Collada front faces).
                fx, fy, fz = struct.unpack_from("<fff", b, p_norm + ifn * 16)
                fw = (W[0] * fx + W[4] * fy + W[8] * fz, W[1] * fx + W[5] * fy + W[9] * fz, W[2] * fx + W[6] * fy + W[10] * fz)
                e1 = [pos[1][k] - pos[0][k] for k in range(3)]
                e2 = [pos[2][k] - pos[0][k] for k in range(3)]
                cr = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
                total += 1
                if sum(cr[k] * fw[k] for k in range(3)) < 0:
                    flipped += 1
                    pos, nrm, uv = pos[::-1], nrm[::-1], uv[::-1]
                mat = mats[m] if m < len(mats) else {"texture": None, "diffuse": 0x808080}
                face_png = png_dir
                rt = retex.get((mat["texture"] or "").lower())
                if rt:   # --retexture: another model's texture, these faces' UV box stretched over all of it
                    new_dir, new_tex, (u0, u1, v0, v1) = rt
                    mat, face_png = dict(mat, texture=new_tex), new_dir
                    uv = [((u_ - u0) / (u1 - u0), 1 - ((1 - v_) - v0) / (v1 - v0)) for u_, v_ in uv]
                key = (mat["texture"] or "").lower() or "col%06x" % (mat["diffuse"] & 0xFFFFFF)
                bake = None
                if gn >= npre:   # a --part: its own materials (models share texture names), its own colours
                    key += f"_p{gn - npre}"
                    bake = parts[gn - npre][2]
                # owner: an --anim-joints object, -1 the root (or --body), -2 - k --part k
                groups.setdefault((-2 - (gn - npre) if gn >= npre else owner if owner is not None else -1, key),
                                  {"mat": mat, "png_dir": face_png, "tris": [], "bake": bake})["tris"].append(
                    ([conv(*q) for q in pos], [convn(*q) for q in nrm], uv))

    if a.fx_mesh:
        # one mesh, one material (an effect mesh: HWRM drew nothing of a ship's many meshes), its texture an atlas of
        # the model's texture pages (as written for a ship, colours baked), UVs moved into each page's cell (clamped
        # to the page: these models don't wrap)
        keys = sorted(groups)
        side = math.ceil(math.sqrt(len(keys)))
        size = pow2(side * FX_TILE)
        cell = size // side
        atlas = Image.new("RGB", (size, size))
        tris, clamped = [], 0
        for i, k in enumerate(keys):
            g = groups[k]
            d = g["mat"]["diffuse"]
            tga = write_textures(g["png_dir"], g["mat"]["texture"], a.out_dir, f"fxtile{i}",
                                 (d & 0xFF, d >> 8 & 0xFF, d >> 16 & 0xFF))
            atlas.paste(Image.open(os.path.join(a.out_dir, tga)).convert("RGB").resize((cell, cell)),
                        ((i % side) * cell, (i // side) * cell))
            os.remove(os.path.join(a.out_dir, tga))
            x0, y0 = (i % side) * cell / size, (i // side) * cell / size
            for p, n, uv in g["tris"]:
                out = []
                for u, v in uv:
                    cu, cv = min(max(u, 0.0), 1.0), min(max(v, 0.0), 1.0)
                    clamped += (cu, cv) != (u, v)
                    out.append((x0 + cu * cell / size, 1 - (y0 + (1 - cv) * cell / size)))
                tris.append((p, n, out))
        atlas.save(os.path.join(a.out_dir, "fxatlas.png"))
        groups = {(-1, "fxatlas"): {"mat": {"texture": "fxatlas", "diffuse": 0xFFFFFF}, "png_dir": a.out_dir,
                                    "tris": tris}}
        frames = {}
        print(f"--fx-mesh: {len(keys)} texture pages in a {size} atlas, {clamped} UVs clamped")
    if a.origin:   # recentred: the model's point o is its origin (o: HWRM units, written to origin.txt)
        if a.origin == "auto":
            vs = [v for g in groups.values() for t in g["tris"] for v in t[0]]
            o = tuple((min(v[k] for v in vs) + max(v[k] for v in vs)) / 2 for k in range(3))
        else:
            o = tuple(float(c) for c in a.origin.split(","))
        for g in groups.values():
            g["tris"] = [([tuple(v[k] - o[k] for k in range(3)) for v in p], n, uv) for p, n, uv in g["tris"]]
        conv0 = conv
        conv = lambda x, y, z: tuple(c - o[k] for k, c in enumerate(conv0(x, y, z)))
        with open(os.path.join(a.out_dir, "origin.txt"), "w") as f:
            f.write(",".join(f"{c:.4f}" for c in o) + "\n")
    images, materials, effects, geoms, nodes = [], [], [], [], []
    joint_kids = {i: [] for i in frames}   # animated object -> its mesh / marker / child joint nodes
    part_kids = [[] for _ in parts]        # --part k -> its mesh nodes
    done_mats = set()
    for gi, ((owner, key), g) in enumerate(sorted(groups.items())):
        d = g["mat"]["diffuse"]
        colour = (d & 0xFF, d >> 8 & 0xFF, d >> 16 & 0xFF)
        base = f"{a.name}_{key}"
        img = f"IMG[{base}_DIFF]"   # RODOH's layout: id IMG[x]-image, name IMG[x]_FMT[..]; HODOR crashes otherwise
        # an effect mesh: HODOR's effect shader (the ship shader ignored the effect's colour: no fade; hw2Shader, the
        # Keeper meshes', lost the texture through HODOR)
        mname = f"MAT[{key}]_SHD[{'fx' if a.fx_mesh else 'ship'}]"
        if key not in done_mats:   # one material per texture, shared by the root and the animated parts
            done_mats.add(key)
            tga = write_textures(g["png_dir"], g["mat"]["texture"], a.out_dir, base, colour, g.get("bake"))
            images.append(f'<image id="{img}-image" name="{img}_FMT[DXT1]"><init_from>{tga}</init_from></image>')
            materials.append(f'<material id="{mname}" name="{mname}"><instance_effect url="#{mname}-fx"/></material>')
            effects.append(f'<effect id="{mname}-fx" name="{mname}"><profile_COMMON>'
                           f'<technique sid="standard"><phong><diffuse><texture texture="{img}-image" '
                           f'texcoord="CHANNEL0"/></diffuse></phong></technique></profile_COMMON></effect>')
        tris = g["tris"]
        n = len(tris) * 3
        P = [c for t in tris for q in t[0] for c in q]
        N = [c for t in tris for q in t[1] for c in q]
        T = [c for t in tris for q in t[2] for c in q]
        gid = f"MULT[{a.name}_{gi}]"
        geoms.append(
            f'<geometry id="{gid}" name="{gid}"><mesh>'
            f'<source id="{gid}-pos"><float_array id="{gid}-pos-a" count="{len(P)}">{fl(P)}</float_array>'
            f'<technique_common><accessor source="#{gid}-pos-a" count="{n}" stride="3"><param name="X" type="float"/>'
            f'<param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>'
            f'<source id="{gid}-nrm"><float_array id="{gid}-nrm-a" count="{len(N)}">{fl(N)}</float_array>'
            f'<technique_common><accessor source="#{gid}-nrm-a" count="{n}" stride="3"><param name="X" type="float"/>'
            f'<param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>'
            f'<source id="{gid}-uv0"><float_array id="{gid}-uv0-a" count="{len(T)}">{fl(T)}</float_array>'
            f'<technique_common><accessor source="#{gid}-uv0-a" count="{n}" stride="2"><param name="S" type="float"/>'
            f'<param name="T" type="float"/></accessor></technique_common></source>'
            f'<vertices id="{gid}-v"><input semantic="POSITION" source="#{gid}-pos"/></vertices>'
            f'<triangles count="{len(tris)}" material="{mname}">'
            f'<input semantic="VERTEX" offset="0" source="#{gid}-v"/><input semantic="NORMAL" offset="0" source="#{gid}-nrm"/>'
            f'<input semantic="TEXCOORD" offset="0" set="0" source="#{gid}-uv0"/>'
            f'<p>{" ".join(map(str, range(n)))}</p></triangles></mesh></geometry>')
        (nodes if owner == -1 else part_kids[-2 - owner] if owner < -1 else joint_kids[owner]).append(
                     f'<node name="{gid}" id="{gid}" sid="{gid}E"><translate sid="translate">0 0 0</translate>'
                     f'<instance_geometry url="#{gid}"><bind_material><technique_common>'
                     f'<instance_material symbol="{mname}" target="#{mname}"><bind_vertex_input semantic="CHANNEL0" '
                     f'input_semantic="TEXCOORD" input_set="0"/></instance_material>'
                     f'</technique_common></bind_material></instance_geometry></node>')

    points = [] if a.fx_mesh else read_mex(os.path.splitext(a.geo)[0] + ".mex")
    for g in a.merge:
        points += read_mex(os.path.splitext(g)[0] + ".mex")
    engine_geo = {}   # engine point -> the .geo its parent object is in
    for g in a.points_from:
        extra_pts = [pt for pt in read_mex(os.path.splitext(g)[0] + ".mex") if pt[0] in ("Gun", "Eng")]
        engine_geo.update({id(pt): g for pt in extra_pts})
        points += extra_pts
    dok_points = {pt[1]: pt for pt in points if pt[0] == "Dok"}
    if a.no_docks:
        points = [pt for pt in points if pt[0] != "Dok"]
    weapons, nweap = weapon_nodes(points, conv, convn)
    # collector paths borrowed from another model, moved onto our Cataclysm RES points (LATCH_OFFSET off the hull)
    anchors = [conv(*(pos[k] + nrm[k] * LATCH_OFFSET for k in range(3)))
               for typ, lbl, pos, nrm, _ in points if typ == "Dok" and re.match(r"RES\d+$", lbl)]
    extra, nextra = borrowed_dock_nodes(a.dock_from, a.dock_scale, "Utility", anchors) if a.dock_from else ("", 0)
    hold_dock, ndock = dock_nodes(points, conv, extra, ("RES",) if a.dock_from else ())
    ndock += nextra
    # Engine nozzles from the .mex Eng chunks: JNT[EngineNozzle<n>] (setEngineTrail index n-1 / setEngineBurn).
    # Each nozzle as in HODOR's engine layout (toolkit demo ship): BURN[EngineBurn<n>] with five flame divisions
    # trailing backwards and an ETSH[EngineShape<n>] quad; trails/burns need these, not just the joint.
    engines = [] if a.no_engines else [pt for pt in points if pt[0] == "Eng"]
    cr_shapes = [sh for _, _, shp in hod_engines(a.engines_from) for sh in shp] if a.engines_from else []
    parsed = {}
    for i, pt in enumerate(engines):
        _, _, pos, _, parent = pt
        n = i + 1
        g = engine_geo.get(id(pt), a.geo)
        if g not in parsed:
            b0, _, _, objs0 = geo2obj.parse(g)
            parsed[g] = (b0, objs0, {o["name"]: k for k, o in enumerate(objs0)}, {})
        b0, objs0, by_name, cache0 = parsed[g]
        if parent in by_name:                       # position is local to that object (Worker: Thruster(1)/(2))
            k = by_name[parent]
            W = geo2obj.world(objs0, k, cache0)
            pos = geo2obj.xform(W, *pos)
            o = objs0[k]
            vs = [geo2obj.xform(W, *struct.unpack_from("<fff", b0, o["pV"] + v * 16)) for v in range(o["nV"])]
            if vs:   # on the engine object's rear face, centred on it (the .mex point sat ~0.6 inboard)
                pos = tuple((min(v[c] for v in vs) + max(v[c] for v in vs)) / 2 for c in (0, 1)) + \
                    (min(v[2] for v in vs),)
        flames = "".join(jnode(f"Flame[0]_Div[{d}]", (0, 0, -2.0 * d)) for d in range(5))
        gid = f"ETSH[EngineShape{n}]"
        # glow quad half-size ~6% of the ship's half-length (Cataclysm Remastered's Recon: 0.45 on ~7)
        if cr_shapes:
            # Cataclysm Remastered's engine shape (its Kuun-Lan: one triangle 54 behind its nozzle), scaled to ours,
            # on our nozzle (user: "a direct port of CR's engines")
            vs = cr_shapes[i % len(cr_shapes)][1]
            P = [c * a.engines_scale for v in vs for c in v]
            idx = [k for t in range(1, len(vs) - 1) for k in (0, t, t + 1)]
        else:
            h = min(30.0, max(0.3, 0.06 * extent * a.scale))
            P = [-h, -h, 0, -h, h, 0, h, h, 0, h, -h, 0]
            idx = [0, 1, 2, 0, 2, 3]
        nv = len(P) // 3
        geoms.append(f'<geometry id="{gid}" name="{gid}"><mesh>'
                     f'<source id="{gid}-pos"><float_array id="{gid}-pos-a" count="{len(P)}">{fl(P)}</float_array>'
                     f'<technique_common><accessor source="#{gid}-pos-a" count="{nv}" stride="3"><param name="X" type="float"/>'
                     f'<param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>'
                     f'<source id="{gid}-nrm"><float_array id="{gid}-nrm-a" count="{len(P)}">{fl([0, 0, -1] * nv)}</float_array>'
                     f'<technique_common><accessor source="#{gid}-nrm-a" count="{nv}" stride="3"><param name="X" type="float"/>'
                     f'<param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>'
                     f'<vertices id="{gid}-v"><input semantic="POSITION" source="#{gid}-pos"/></vertices>'
                     f'<triangles count="{len(idx) // 3}"><input semantic="VERTEX" offset="0" source="#{gid}-v"/>'
                     f'<input semantic="NORMAL" offset="0" source="#{gid}-nrm"/><p>{" ".join(map(str, idx))}</p></triangles>'
                     f'</mesh></geometry>')
        shape = (f'<node name="{gid}" id="{gid}" sid="{gid}E"><translate sid="translate">0 0 0</translate>'
                 f'<instance_geometry url="#{gid}"></instance_geometry></node>')
        # BURN flames kept with CR's shape: CR's .ship setEngineBurn (ours too) drives them, but its own model has no
        # BURN, so CR shows no flames; without them the engines barely glowed in game (user: "add CR's stuff")
        burn = jnode(f"BURN[EngineBurn{n}]", (0, 0, 0), flames)
        weapons += jnode(f"JNT[EngineNozzle{n}]", conv(*pos), burn + shape)
    nav, nnav = ("", 0) if a.no_navlights else navlight_nodes(points, conv, a.scale)
    weapons += nav
    # resource drop-off at the collector docks (Cataclysm Remastered's sits at its Kuun-Lan's front dock)
    res = [conv(*pt[2]) for pt in points if pt[0] == "Dok" and re.match(r"RES\d+$", pt[1])]
    res_at = tuple(sum(p[k] for p in res) / len(res) for k in range(3)) if res else (0, 0, 0)
    for spec in a.hardpoint:   # subsystem hardpoint: <name>_Position with _Direction / _Rest (HWRM toolkit layout)
        hp, *opts = spec.split("@")
        at, rest = (res_at if hp == "Hardpoint_Resource" else (0, 0, 0)), (0, 0, 10)
        for o in opts:
            if o == "flip":
                rest = (0, 0, -10)
            elif o.startswith("dok:"):
                at = conv(*dok_points[o[4:]][2])
            elif o.startswith("gun:"):   # at a .mex gun point, facing its firing direction (weapon subsystems)
                gun = [pt for pt in points if pt[0] == "Gun" and pt[1] == o[4:]]
                if not gun:
                    sys.exit(f"--hardpoint {spec}: no gun point {o[4:]}")
                at = conv(*gun[0][2])
                n = convn(*gun[0][3])
                ln = math.sqrt(sum(c * c for c in n)) or 1.0
                rest = tuple(10 * c / ln for c in n)
            else:
                at = tuple(float(c) for c in o.split(","))
        weapons += jnode(f"JNT[{hp}_Position]", at, jnode(f"JNT[{hp}_Direction]", (0, 10, 0))
                         + jnode(f"JNT[{hp}_Rest]", rest))
    for spec in a.weapon:   # extra weapon hardpoints (weapon_nodes' layout)
        name, where, d = spec.split("@")
        if where.startswith("dok:"):
            if where[4:] not in dok_points:
                sys.exit(f"--weapon {spec}: no dock point {where[4:]}")
            at = conv(*dok_points[where[4:]][2])
        else:
            at = tuple(float(c) for c in where.split(","))
        n = tuple(float(c) for c in d.split(","))
        ln = math.sqrt(sum(c * c for c in n)) or 1.0
        n = tuple(c / ln for c in n)
        up = (0.0, 1.0, 0.0) if abs(n[1]) < 0.9 else (1.0, 0.0, 0.0)
        base = f"Weapon_{name}"
        weapons += jnode(f"JNT[{base}_Position]", at, jnode(f"JNT[{base}_Direction]", tuple(10 * c for c in up))
                         + jnode(f"JNT[{base}_Rest]", tuple(10 * c for c in n))
                         + jnode(f"JNT[{base}_Muzzle]", tuple(0.1 * c for c in n)))
    # effect markers (.events "marker"): plain joints, the effect pointing along the joint's +Z
    by_obj = {main_objs[i]["name"]: i for i in frames} if frames else {}
    for spec in a.marker:
        name, where, *at = spec.split("@")
        if re.match(r"^-?[\d.]+,-?[\d.]+,-?[\d.]+$", where):
            weapons += jnode(f"JNT[{name}]", tuple(float(c) for c in where.split(",")))
        elif where.startswith("gun:"):
            gun = [pt for pt in points if pt[0] == "Gun" and pt[1] == where[4:]]
            if not gun:
                sys.exit(f"--marker {spec}: no gun point {where[4:]}")
            weapons += jnode(f"JNT[{name}]", conv(*gun[0][2]))
        else:
            if where not in by_obj or not at:
                sys.exit(f"--marker {spec}: {where} is not an --anim-joints object (or no position)")
            rot = tuple(float(c) for c in at[1].split(",")) if len(at) > 1 else None
            joint_kids[by_obj[where]].append(jnode(f"JNT[{name}]", conv(*(float(c) for c in at[0].split(","))),
                                                   rot=rot))

    def joint_tree(parent):
        out = ""
        for i, (p, m) in sorted(frames.items()):
            if p == parent:
                t, rot = hwrm_local(m, s)
                out += jnode(f"JNT[{joint_name(main_objs[i]['name'])}]", t,
                             "".join(joint_kids[i]) + joint_tree(i), euler_deg(rot))
        return out
    if frames:
        weapons += joint_tree(None)
    # whole models as joints the .madstate can show / hide (setJointVisible): --body (this ship's own meshes) and
    # each --part (another model, at the origin): the Mimic's disguises
    if a.body:
        weapons += jnode(f"JNT[{a.body}]", (0, 0, 0), "".join(nodes))
        nodes = []
    for k, (name, _, _) in enumerate(parts):
        weapons += jnode(f"JNT[{name}]", (0, 0, 0), "".join(part_kids[k]))
    if a.latch:
        # harvesting: HWRM puts LatchOrientation on the asteroid's surface, so it sets how far off a collector holds
        # (none = the ship's origin: it sits on the rock). Layout of stock tai_resourcecollector's: Up along the
        # beam (+Z), Heading up, with _Heading / _Left / _Up joints 10 units out.
        at = tuple(float(c) for c in a.latch.split(","))
        weapons += jnode("JNT[LatchOrientation]", at, jnode("JNT[LatchOrientationHeading]", (0, 0, 10))
                         + jnode("JNT[LatchOrientationLeft]", (10, 0, 0)) + jnode("JNT[LatchOrientationUp]", (0, 10, 0)),
                         rot=(90.0, 0.0, 180.0))

    if not a.fx_mesh:
        # repair points (stock HW1 layout: RepairPointN with _Heading / _Left / _Up, 10 out): HWRM repairs a ship only
        # at its RepCap latch points ("marked as repairable ... but has no repair points!"; user: the repair order
        # targeted nothing), one repairer per point (user: several craft must repair one target). Four, just off
        # the hull's top, bottom and sides (bounding box); install_cr.py declares them.
        rp_vs = [v for g in groups.values() for t in g["tris"] for v in t[0]] or [(0.0, 0.0, 0.0)]
        rp_lo = [min(v[k] for v in rp_vs) for k in range(3)]
        rp_hi = [max(v[k] for v in rp_vs) for k in range(3)]
        rp_c = [(rp_lo[k] + rp_hi[k]) / 2 for k in range(3)]
        rp_out = [(rp_hi[k] - rp_lo[k]) * 0.05 for k in range(3)]
        spots = [(rp_c[0], rp_hi[1] + rp_out[1], rp_c[2]), (rp_c[0], rp_lo[1] - rp_out[1], rp_c[2]),
                 (rp_lo[0] - rp_out[0], rp_c[1], rp_c[2]), (rp_hi[0] + rp_out[0], rp_c[1], rp_c[2])]
        for k, at in enumerate(spots):
            rp = f"RepairPoint{k}"
            weapons += jnode(f"JNT[{rp}]", at, jnode(f"JNT[{rp}Heading]", (0, 0, 10))
                             + jnode(f"JNT[{rp}Left]", (10, 0, 0)) + jnode(f"JNT[{rp}Up]", (0, 10, 0)))

    dae = os.path.join(a.out_dir, a.name + ".dae")
    with open(dae, "w", encoding="utf-8", newline="\n") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n'
                '<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">\n'
                f'<asset><contributor><authoring_tool>Cataclysm-HWRM geo2dae.py ({rel})</authoring_tool></contributor>'
                '<unit meter="1.0" name="meter"/><up_axis>Y_UP</up_axis></asset>\n'
                '<library_images>\n' + "\n".join(images) + '\n</library_images>\n'
                '<library_materials>\n' + "\n".join(materials) + '\n</library_materials>\n'
                '<library_effects>\n' + "\n".join(effects) + '\n</library_effects>\n'
                '<library_geometries>\n' + "\n".join(geoms) + '\n</library_geometries>\n'
                '<library_visual_scenes><visual_scene id="scene" name="scene">\n'
                '<node name="ROOT_LOD[0]" id="ROOT_LOD[0]" sid="ROOT_LOD[0]E"><translate sid="translate">0 0 0</translate>\n'
                '<node name="JNT[Root]" id="JNT[Root]" sid="JNT[Root]E"><translate sid="translate">0 0 0</translate>\n'
                # weapon/engine/hardpoint joints inside JNT[Root], with the meshes (HODOR adds its own Root above it)
                + "\n".join(nodes) + '\n' + weapons + '\n</node>\n' + hold_dock + '\n</node>\n'
                '<node name="ROOT_INFO" id="ROOT_INFO" sid="ROOT_INFOE"><translate sid="translate">0 0 0</translate>'
                '<node name="Class[MultiMesh]_Version[512]" id="Class[MultiMesh]_Version[512]" sid="ClassE"/>'
                '<node name="UVSets[1]" id="UVSets[1]" sid="UVSetsE"/></node>\n'
                '</visual_scene></library_visual_scenes>\n'
                '<scene><instance_visual_scene url="#scene"/></scene>\n</COLLADA>\n')
    print(f"{dae}: {total} triangles ({flipped} rewound), {len(groups)} materials, {nweap} weapon joints, "
          f"{ndock} dock paths, {len(engines)} engine nozzles, {nnav} nav lights, "
          f"{sum(1 for f in os.listdir(a.out_dir) if f.endswith('_GLOW.tga'))} glow maps")
    if not a.no_hodor:
        print("HODOR hangs when started from Python/PowerShell (not from Git Bash); use tools/build_ship.sh")



if __name__ == "__main__":
    main()
