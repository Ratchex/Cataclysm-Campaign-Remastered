"""Convert a Cataclysm ship model (.geo, LOD0) to a HODOR-ready Collada file and build the .hod with HODOR.

Input:  Cataclysm-decomp/extracted/big/<race>/<ship>/rl0/lod0/<ship>.geo  (parsed with geo2obj.parse)
        Cataclysm-decomp/extracted/textures/<same dir>/<texture>.png (+ _team0/_team1 masks from lif2png.py)
Output: <out_dir>/<name>.dae, <name>_<tex>_DIFF.tga / _TEAM.tga next to it, and <out_dir>/<name>.hod

Coordinates: HW1 models are X up, Y right, Z forward; HODOR wants Y up, Z forward. HWRM = 0.35 * (-y, x, z)
(0.35 = the same factor Gearbox used for HW1 levels and ship sizes, see NOTES.md); a proper rotation, so winding
is kept. Every object is baked into JNT[Root] for now (turret joints come later with weapons).
Materials: MAT[<tex>]_SHD[ship] with image IMG[<name>_<tex>_DIFF] (id ...-image); HODOR picks up the _TEAM file next
to the _DIFF one (SHADERS.MAP: $team R = 1 - team colour, G = 1 - stripe colour, B = 0).

Usage: geo2dae.py <geo> <out_dir> <name> [--scale 0.35]   (tools/build_ship.sh runs it, then HODOR)
HODOR quirks: it must be started from Git Bash (from Python or PowerShell it spins forever), with forward-slash
paths; textures must be square powers of two >= 64; image ids must be IMG[x]-image.
"""
import argparse
import os
import struct
import sys

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


def write_textures(png_dir, tex, out_dir, base, colour):
    """Write <base>_DIFF.tga (and _TEAM.tga when masks exist); return the DIFF file name."""
    src = os.path.join(png_dir, tex.lower() + ".png") if tex else None
    if src and os.path.exists(src):
        im = Image.open(src).convert("RGB")
    else:
        im = Image.new("RGB", (4, 4), colour)
    # HODOR loops forever building mips for small or non-square textures: square, power of two, at least 64.
    n = max(64, pow2(im.width), pow2(im.height))
    size = (n, n)
    im = im.resize(size) if size != im.size else im
    im.save(os.path.join(out_dir, base + "_DIFF.tga"))
    if src:
        masks = []
        for k in (0, 1):
            m = os.path.join(png_dir, f"{tex.lower()}_team{k}.png")
            masks.append(Image.open(m).convert("L").resize(size) if os.path.exists(m) else Image.new("L", size, 0))
        if any(m.getextrema()[1] for m in masks):
            inv = [m.point(lambda v: 255 - v) for m in masks]
            Image.merge("RGB", (inv[0], inv[1], Image.new("L", size, 0))).save(os.path.join(out_dir, base + "_TEAM.tga"))
    return base + "_DIFF.tga"


def fl(vals):
    return " ".join("%.6g" % v for v in vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("geo")
    ap.add_argument("out_dir")
    ap.add_argument("name")
    ap.add_argument("--scale", type=float, default=0.35)
    ap.add_argument("--no-hodor", action="store_true")
    ap.add_argument("--merge", nargs="*", default=[],
                    help="more .geo files baked into the same mesh (Kuun-Lan modules share the core's frame)")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    rel = os.path.relpath(os.path.dirname(a.geo), os.path.join(DECOMP, "extracted", "big"))
    s = a.scale
    conv = lambda x, y, z: (-y * s, x * s, z * s)
    convn = lambda x, y, z: (-y, x, z)

    # Group triangles by texture (materials sharing a texture share one HWRM material).
    groups = {}   # key -> {"mat", "png_dir", "tris": [(positions[3], normals[3], uvs[3])]}
    flipped = total = 0
    for geo in [a.geo] + a.merge:
        b, ver, mats, objs = geo2obj.parse(geo)
        png_dir = os.path.join(DECOMP, "extracted", "textures",
                               os.path.relpath(os.path.dirname(geo), os.path.join(DECOMP, "extracted", "big")))
        cache = {}
        for i, o in enumerate(objs):
            W = geo2obj.world(objs, i, cache)
            f = struct.unpack_from(geo2obj.OBJ.format, b, 68 + i * geo2obj.OBJ.size)
            p_norm = f[10]
            verts = [struct.unpack_from("<fffi", b, o["pV"] + v * 16) for v in range(o["nV"])]
            for p in range(o["nP"]):
                ifn, i0, i1, i2, m, s0, t0, s1, t1, s2, t2, _ = geo2obj.POLY.unpack_from(b, o["pP"] + p * geo2obj.POLY.size)
                pos, nrm = [], []
                for vi in (i0, i1, i2):
                    x, y, z, ivn = verts[vi]
                    pos.append(geo2obj.xform(W, x, y, z))
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
                key = (mat["texture"] or "").lower() or "col%06x" % (mat["diffuse"] & 0xFFFFFF)
                groups.setdefault(key, {"mat": mat, "png_dir": png_dir, "tris": []})["tris"].append(
                    ([conv(*q) for q in pos], [convn(*q) for q in nrm], uv))

    images, materials, effects, geoms, nodes = [], [], [], [], []
    for gi, (key, g) in enumerate(sorted(groups.items())):
        d = g["mat"]["diffuse"]
        colour = (d & 0xFF, d >> 8 & 0xFF, d >> 16 & 0xFF)
        base = f"{a.name}_{key}"
        tga = write_textures(g["png_dir"], g["mat"]["texture"], a.out_dir, base, colour)
        img = f"IMG[{base}_DIFF]"   # RODOH's layout: id IMG[x]-image, name IMG[x]_FMT[..]; HODOR crashes otherwise
        mname = f"MAT[{key}]_SHD[ship]"
        images.append(f'<image id="{img}-image" name="{img}_FMT[DXT1]"><init_from>{tga}</init_from></image>')
        materials.append(f'<material id="{mname}" name="{mname}"><instance_effect url="#{mname}-fx"/></material>')
        effects.append(f'<effect id="{mname}-fx" name="{mname}"><profile_COMMON>'
                       f'<technique sid="standard"><phong><diffuse><texture texture="{img}-image" texcoord="CHANNEL0"/>'
                       f'</diffuse></phong></technique></profile_COMMON></effect>')
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
        nodes.append(f'<node name="{gid}" id="{gid}" sid="{gid}E"><translate sid="translate">0 0 0</translate>'
                     f'<instance_geometry url="#{gid}"><bind_material><technique_common>'
                     f'<instance_material symbol="{mname}" target="#{mname}"><bind_vertex_input semantic="CHANNEL0" '
                     f'input_semantic="TEXCOORD" input_set="0"/></instance_material>'
                     f'</technique_common></bind_material></instance_geometry></node>')

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
                + "\n".join(nodes) + '\n</node></node>\n'
                '<node name="ROOT_INFO" id="ROOT_INFO" sid="ROOT_INFOE"><translate sid="translate">0 0 0</translate>'
                '<node name="Class[MultiMesh]_Version[512]" id="Class[MultiMesh]_Version[512]" sid="ClassE"/>'
                '<node name="UVSets[1]" id="UVSets[1]" sid="UVSetsE"/></node>\n'
                '</visual_scene></library_visual_scenes>\n'
                '<scene><instance_visual_scene url="#scene"/></scene>\n</COLLADA>\n')
    print(f"{dae}: {total} triangles ({flipped} rewound), {len(groups)} materials")
    if not a.no_hodor:
        print("HODOR hangs when started from Python/PowerShell (not from Git Bash); use tools/build_ship.sh")



if __name__ == "__main__":
    main()
