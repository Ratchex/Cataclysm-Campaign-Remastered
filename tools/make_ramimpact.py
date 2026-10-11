"""The Ramming Frigate's impact effect: Cataclysm's ramfrigateimpact.ebg ported.

Cataclysm (etg/ramfrigateimpact.ebg, EGT_RAMMING_FRIGATE_IMPACT_EFFECT): a white shock "bowl", mesh ETG/meshes/
RamHit0-2 morphing (0 -> 1 -> 2), its texture the 12-frame SHOCK animation (shock00-11), additive (alpha mode 0),
gone after 0.6 s. Here: the final bowl (RamHit2) as an effect mesh with one shock frame baked in (an effect mesh
draws its own texture), growing into shape and fading out over 0.6 s (HWRM can't morph an effect mesh). Played on
the frigate's marker_ram (its nose tip, tools/build_ship.sh) by smt_rammingfrigate.madstate NIS01 (the impact).

  --dae   the bowl mesh into build/ships/fx_ramimpact/ for HODOR
  (none)  install: data/art/fx/cat_ramimpact.lua and cat_ramimpact/cat_ramimpact.hod
Run tools/build_ramimpact.sh (--dae, HODOR, install).
"""
import os
import shutil
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_procbeam import fl  # noqa: E402

sys.path.insert(0, r"C:\Modding\Cataclysm-decomp\tools")
import geo2obj  # noqa: E402
import lif2png  # noqa: E402

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ETG = r"C:\Modding\Cataclysm-decomp\extracted\big\etg"
BUILD = os.path.join(MOD, "build", "ships", "fx_ramimpact")
SCALE = 0.35        # HW1 -> HWRM units (the bowl is ~126 across: the frigate's size, as in Cataclysm)
FRAME = "shock04"   # the shock animation frame baked in (of shock00-11)
LIFE = 0.6          # Cataclysm setLifespan(0.6)


def write_dae():
    os.makedirs(BUILD, exist_ok=True)
    b, _, _, objs = geo2obj.parse(os.path.join(ETG, "meshes", "ramhit2.geo"))
    o = objs[0]
    verts = [struct.unpack_from("<fff", b, o["pV"] + v * 16) for v in range(o["nV"])]
    pos, uv = [], []
    for p in range(o["nP"]):
        _, i0, i1, i2, _, s0, t0, s1, t1, s2, t2, _ = geo2obj.POLY.unpack_from(b, o["pP"] + p * geo2obj.POLY.size)
        for i, s, t in ((i0, s0, t0), (i1, s1, t1), (i2, s2, t2)):
            x, y, z = verts[i]
            pos.append((-y * SCALE, x * SCALE, z * SCALE))      # HWRM = 0.35 (-y, x, z) (geo2dae.py)
            uv.append((s, 1 - t))
    n = len(pos)
    tris = [(k, k + 1, k + 2) for k in range(0, n, 3)]
    tris += [(a, c, b2) for a, b2, c in tris]                  # both windings: seen from inside and out
    name = "fx_ramimpact"
    g = f"MULT[{name}_0]"
    mat = "MAT[ramimpact]_SHD[fx]"
    img = f"IMG[{name}_DIFF]"

    def src(sid, data, params):
        flat = [c for v in data for c in v]
        p = "".join(f'<param name="{q}" type="float"/>' for q in params)
        return (f'<source id="{g}-{sid}"><float_array id="{g}-{sid}-a" count="{len(flat)}">{fl(flat)}</float_array>'
                f'<technique_common><accessor source="#{g}-{sid}-a" count="{len(data)}" stride="{len(params)}">{p}'
                f'</accessor></technique_common></source>')
    nrm = [(0.0, 0.0, 1.0)] * n
    dae = f'''<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
<asset><contributor><authoring_tool>Cataclysm-HWRM make_ramimpact.py</authoring_tool></contributor><unit meter="1.0" name="meter"/><up_axis>Y_UP</up_axis></asset>
<library_images>
<image id="{img}-image" name="{img}_FMT[DXT5]"><init_from>{name}_DIFF.tga</init_from></image>
</library_images>
<library_materials>
<material id="{mat}" name="{mat}"><instance_effect url="#{mat}-fx"/></material>
</library_materials>
<library_effects>
<effect id="{mat}-fx" name="{mat}"><profile_COMMON><technique sid="standard"><phong><diffuse><texture texture="{img}-image" texcoord="CHANNEL0"/></diffuse></phong></technique></profile_COMMON></effect>
</library_effects>
<library_geometries>
<geometry id="{g}" name="{g}"><mesh>{src("pos", pos, "XYZ")}{src("nrm", nrm, "XYZ")}{src("uv0", uv, "ST")}<vertices id="{g}-v"><input semantic="POSITION" source="#{g}-pos"/></vertices><triangles count="{len(tris)}" material="{mat}"><input semantic="VERTEX" offset="0" source="#{g}-v"/><input semantic="NORMAL" offset="0" source="#{g}-nrm"/><input semantic="TEXCOORD" offset="0" set="0" source="#{g}-uv0"/><p>{" ".join(str(i) for t in tris for i in t)}</p></triangles></mesh></geometry>
</library_geometries>
<library_visual_scenes><visual_scene id="scene" name="scene">
<node name="ROOT_LOD[0]" id="ROOT_LOD[0]" sid="ROOT_LOD[0]E"><translate sid="translate">0 0 0</translate>
<node name="JNT[Root]" id="JNT[Root]" sid="JNT[Root]E"><translate sid="translate">0 0 0</translate>
<node name="{g}" id="{g}" sid="{g}E"><translate sid="translate">0 0 0</translate><instance_geometry url="#{g}"><bind_material><technique_common><instance_material symbol="{mat}" target="#{mat}"><bind_vertex_input semantic="CHANNEL0" input_semantic="TEXCOORD" input_set="0"/></instance_material></technique_common></bind_material></instance_geometry></node>
</node>
</node>
<node name="ROOT_INFO" id="ROOT_INFO" sid="ROOT_INFOE"><translate sid="translate">0 0 0</translate><node name="Class[MultiMesh]_Version[512]" id="Class[MultiMesh]_Version[512]" sid="ClassE"/><node name="UVSets[1]" id="UVSets[1]" sid="UVSetsE"/></node>
</visual_scene></library_visual_scenes>
<scene><instance_visual_scene url="#scene"/></scene>
</COLLADA>
'''
    with open(os.path.join(BUILD, name + ".dae"), "w", encoding="utf-8", newline="\n") as f:
        f.write(dae)
    # the shock frame, square and a power of two (HODOR), its brightness as alpha (added on)
    _, w, h, rgba, _ = lif2png.convert(os.path.join(ETG, "textures", "shock", FRAME + ".lif"))
    im = Image.fromarray(np.ascontiguousarray(rgba)).convert("RGB")
    side = 1 << max(6, max(w, h) - 1).bit_length()
    im = im.resize((side, side))
    a = im.convert("L")
    im.putalpha(a)
    im.save(os.path.join(BUILD, name + "_DIFF.tga"))
    ext = [(min(p[k] for p in pos), max(p[k] for p in pos)) for k in range(3)]
    print(f"{BUILD}/{name}.dae: {len(tris)} triangles, extent " + ", ".join(f"{a:.0f}..{b:.0f}" for a, b in ext))


FX = f'''-- Cataclysm-HWRM: the Ramming Frigate's impact (tools/make_ramimpact.py: Cataclysm's ramfrigateimpact shock bowl),
-- on its marker_ram at the impact (smt_rammingfrigate.madstate NIS01): grows into shape and fades over {LIFE} s.
fx = {{
style = "STYLE_RING",
properties = {{
property_00 = {{ name = "Radius", type = "VARTYPE_ARRAY_TIMEFLOAT", value = {{ 0, 0.35, 0.3, 0.85, 1, 1, }}, }},
property_01 = {{ name = "Offset", type = "VARTYPE_ARRAY_TIMEVECTOR3", value = {{ entry_00 = {{ 0, 0, 0, 0, }}, entry_01 = {{ 1, 0, 0, 0, }}, }}, }},
property_02 = {{ name = "SpinX", type = "VARTYPE_ARRAY_TIMEFLOAT", value = {{ 0, 0, 1, 0, }}, }},
property_03 = {{ name = "SpinY", type = "VARTYPE_ARRAY_TIMEFLOAT", value = {{ 0, 0, 1, 0, }}, }},
property_04 = {{ name = "SpinZ", type = "VARTYPE_ARRAY_TIMEFLOAT", value = {{ 0, 0, 1, 0, }}, }},
property_05 = {{ name = "Colour", type = "VARTYPE_ARRAY_TIMECOLOUR", value = {{ entry_00 = {{ 0, 1, 1, 1, 1, }}, entry_01 = {{ 0.4, 0.9, 0.95, 1, 1, }}, entry_02 = {{ 1, 0, 0, 0, 0, }}, }}, }},
property_06 = {{ name = "RadiusEpsilon", type = "VARTYPE_FLOAT", value = 0, }},
property_07 = {{ name = "RateEpsilon", type = "VARTYPE_FLOAT", value = 0, }},
property_08 = {{ name = "SpinEpsilonX", type = "VARTYPE_FLOAT", value = 0, }},
property_09 = {{ name = "SpinEpsilonY", type = "VARTYPE_FLOAT", value = 0, }},
property_10 = {{ name = "SpinEpsilonZ", type = "VARTYPE_FLOAT", value = 0, }},
property_11 = {{ name = "SpinRandom", type = "VARTYPE_BOOL", value = 0, }},
property_12 = {{ name = "Duration", type = "VARTYPE_FLOAT", value = {LIFE}, }},
property_13 = {{ name = "UseMesh", type = "VARTYPE_BOOL", value = 1, }},
property_14 = {{ name = "UseDepthTest", type = "VARTYPE_BOOL", value = 1, }},
property_15 = {{ name = "UseDepthSort", type = "VARTYPE_BOOL", value = 1, }},
property_16 = {{ name = "Loop", type = "VARTYPE_BOOL", value = 0, }},
property_17 = {{ name = "Billboard", type = "VARTYPE_BOOL", value = 0, }},
property_18 = {{ name = "AlternateFOV", type = "VARTYPE_BOOL", value = 0, }},
property_19 = {{ name = "SelfIlluminated", type = "VARTYPE_BOOL", value = 1, }},
property_20 = {{ name = "Blending", type = "VARTYPE_INT", value = 4, }},
property_21 = {{ name = "Texture", type = "VARTYPE_STRING", value = "", }},
property_22 = {{ name = "Mesh", type = "VARTYPE_STRING", value = "DATA:ART/FX/CAT_RAMIMPACT/CAT_RAMIMPACT.HOD", }},
property_23 = {{ name = "SortOrder", type = "VARTYPE_INT", value = 2, }},
property_24 = {{ name = "RandomBitmap", type = "VARTYPE_BOOL", value = 0, }},
property_25 = {{ name = "BirthSpawn_Fx", type = "VARTYPE_STRING", value = "", }},
property_26 = {{ name = "Spawn_Fx", type = "VARTYPE_STRING", value = "", }},
property_27 = {{ name = "DepthOffset", type = "VARTYPE_FLOAT", value = 0, }},
property_28 = {{ name = "PointDistance", type = "VARTYPE_FLOAT", value = -1, }},
}},
}}
'''


def install():
    hod = os.path.join(BUILD, "fx_ramimpact.hod")
    if not os.path.exists(hod):
        sys.exit(f"{hod} missing: run tools/build_ramimpact.sh")
    fx = os.path.join(MOD, "data", "art", "fx")
    os.makedirs(os.path.join(fx, "cat_ramimpact"), exist_ok=True)
    shutil.copyfile(hod, os.path.join(fx, "cat_ramimpact", "cat_ramimpact.hod"))
    with open(os.path.join(fx, "cat_ramimpact.lua"), "w", newline="\n") as f:
        f.write(FX)
    print("installed data/art/fx/cat_ramimpact.lua, cat_ramimpact/cat_ramimpact.hod")


if __name__ == "__main__":
    write_dae() if sys.argv[1:] == ["--dae"] else install()
