"""The Ramming Frigate's push flames (user: a stronger version of its engines, with thruster flames, while it pushes).

A flame-shaped tube along -Z from each engine nozzle (the nozzle joints are unrotated: its BURN flames trail along
-Z, geo2dae.py), on stock fx_harvest like the Processor's beams (tools/make_procbeam.py: the texture scrolls along
the flame, pulses run down it), grey noise tinted blue-white by the effect (the Kuun-Lan engine glow's colour),
faded to nothing at the tip by vertex colours, flickering. Played by smt_rammingfrigate.madstate (RamThrust) when
shiprules.lua CatRam_Tick starts the push.

  --dae   the flame mesh into build/ships/fx_ramflame/ for HODOR
  (none)  install: data/art/fx/cat_ramflame.lua and cat_ramflame/cat_ramflame.hod
Run tools/build_ramflame.sh (--dae, HODOR, install).
"""
import math
import os
import shutil
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_procbeam import STOCK_TEX, fl  # noqa: E402

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(MOD, "build", "ships", "fx_ramflame")
LENGTH = 70.0      # the flame behind each nozzle (the frigate is 137 long)
RADIUS = 6.0       # at the nozzle (its three nozzles are ~15 across)
RINGS, SEGS = 40, 12
V_REPEAT = 2.0


def radius(f):
    """swells a little, then narrows to a point"""
    return RADIUS * (1 + 0.35 * math.sin(math.pi * f)) * (1 - f) ** 0.6


def write_dae():
    os.makedirs(BUILD, exist_ok=True)
    pos, nrm, uv, col, tris = [], [], [], [], []
    for ring in range(RINGS + 1):
        f = ring / RINGS
        z, rad = -LENGTH * f, radius(f)
        c = (1 - f) ** 1.5
        for k in range(SEGS + 1):
            a = 2 * math.pi * k / SEGS
            pos.append((rad * math.cos(a), rad * math.sin(a), z))
            nrm.append((math.cos(a), math.sin(a), 0.0))
            uv.append((k / SEGS, f * V_REPEAT))
            col.append((c, c, c, c))
    n = SEGS + 1
    for ring in range(RINGS):
        for k in range(SEGS):
            a, b, c, d = ring * n + k, ring * n + k + 1, (ring + 1) * n + k, (ring + 1) * n + k + 1
            tris += [(a, c, b), (b, c, d), (a, b, c), (b, d, c)]
    name = "fx_ramflame"
    g = f"MULT[{name}_0]"
    mat = "MAT[ramflame]_SHD[fx_harvest]"
    img = f"IMG[{name}_DIFF]"

    def src(sid, data, params):
        flat = [c for v in data for c in v]
        p = "".join(f'<param name="{q}" type="float"/>' for q in params)
        return (f'<source id="{g}-{sid}"><float_array id="{g}-{sid}-a" count="{len(flat)}">{fl(flat)}</float_array>'
                f'<technique_common><accessor source="#{g}-{sid}-a" count="{len(data)}" stride="{len(params)}">{p}'
                f'</accessor></technique_common></source>')
    dae = f'''<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
<asset><contributor><authoring_tool>Cataclysm-HWRM make_ramflame.py</authoring_tool></contributor><unit meter="1.0" name="meter"/><up_axis>Y_UP</up_axis></asset>
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
<geometry id="{g}" name="{g}"><mesh>{src("pos", pos, "XYZ")}{src("nrm", nrm, "XYZ")}{src("uv0", uv, "ST")}{src("col", col, "RGBA")}<vertices id="{g}-v"><input semantic="POSITION" source="#{g}-pos"/></vertices><triangles count="{len(tris)}" material="{mat}"><input semantic="VERTEX" offset="0" source="#{g}-v"/><input semantic="NORMAL" offset="0" source="#{g}-nrm"/><input semantic="TEXCOORD" offset="0" set="0" source="#{g}-uv0"/><input semantic="COLOR" offset="0" set="0" source="#{g}-col"/><p>{" ".join(str(i) for t in tris for i in t)}</p></triangles></mesh></geometry>
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
    # grey noise (the stock repair beam's, tileable: it scrolls), lifted so the flame is never black inside
    im = Image.open(STOCK_TEX).convert("L")
    im = im.point(lambda v: int(90 + v * 165 / 255)).convert("RGBA")
    im.save(os.path.join(BUILD, name + "_DIFF.tga"))
    print(f"{BUILD}/{name}.dae: flame {LENGTH:g} long, radius {RADIUS:g}, {len(tris)} triangles")


FX = '''-- Cataclysm-HWRM: the Ramming Frigate's push flames (tools/make_ramflame.py; on its EngineNozzle joints while it
-- pushes: smt_rammingfrigate.madstate RamThrust). The flame mesh on stock fx_harvest, tinted the Kuun-Lan engine
-- glow's blue-white, flickering.
fx = {
style = "STYLE_RING",
properties = {
property_00 = { name = "Radius", type = "VARTYPE_ARRAY_TIMEFLOAT", value = { 0, 1, 1, 1, }, },
property_01 = { name = "Offset", type = "VARTYPE_ARRAY_TIMEVECTOR3", value = { entry_00 = { 0, 0, 0, 0, }, entry_01 = { 1, 0, 0, 0, }, }, },
property_02 = { name = "SpinX", type = "VARTYPE_ARRAY_TIMEFLOAT", value = { 0, 0, 1, 0, }, },
property_03 = { name = "SpinY", type = "VARTYPE_ARRAY_TIMEFLOAT", value = { 0, 0, 1, 0, }, },
property_04 = { name = "SpinZ", type = "VARTYPE_ARRAY_TIMEFLOAT", value = { 0, 0, 1, 0, }, },
property_05 = { name = "Colour", type = "VARTYPE_ARRAY_TIMECOLOUR", value = { entry_00 = { 0, 0.55, 0.78, 1, 1, }, entry_01 = { 0.3, 0.75, 0.9, 1, 1, }, entry_02 = { 0.55, 0.5, 0.72, 1, 1, }, entry_03 = { 0.8, 0.7, 0.88, 1, 1, }, entry_04 = { 1, 0.55, 0.78, 1, 1, }, }, },
property_06 = { name = "RadiusEpsilon", type = "VARTYPE_FLOAT", value = 0, },
property_07 = { name = "RateEpsilon", type = "VARTYPE_FLOAT", value = 0, },
property_08 = { name = "SpinEpsilonX", type = "VARTYPE_FLOAT", value = 0, },
property_09 = { name = "SpinEpsilonY", type = "VARTYPE_FLOAT", value = 0, },
property_10 = { name = "SpinEpsilonZ", type = "VARTYPE_FLOAT", value = 0, },
property_11 = { name = "SpinRandom", type = "VARTYPE_BOOL", value = 0, },
property_12 = { name = "Duration", type = "VARTYPE_FLOAT", value = 0.4, },
property_13 = { name = "UseMesh", type = "VARTYPE_BOOL", value = 1, },
property_14 = { name = "UseDepthTest", type = "VARTYPE_BOOL", value = 1, },
property_15 = { name = "UseDepthSort", type = "VARTYPE_BOOL", value = 1, },
property_16 = { name = "Loop", type = "VARTYPE_BOOL", value = 1, },
property_17 = { name = "Billboard", type = "VARTYPE_BOOL", value = 0, },
property_18 = { name = "AlternateFOV", type = "VARTYPE_BOOL", value = 0, },
property_19 = { name = "SelfIlluminated", type = "VARTYPE_BOOL", value = 1, },
property_20 = { name = "Blending", type = "VARTYPE_INT", value = 4, },
property_21 = { name = "Texture", type = "VARTYPE_STRING", value = "", },
property_22 = { name = "Mesh", type = "VARTYPE_STRING", value = "DATA:ART/FX/CAT_RAMFLAME/CAT_RAMFLAME.HOD", },
property_23 = { name = "SortOrder", type = "VARTYPE_INT", value = 2, },
property_24 = { name = "RandomBitmap", type = "VARTYPE_BOOL", value = 0, },
property_25 = { name = "BirthSpawn_Fx", type = "VARTYPE_STRING", value = "", },
property_26 = { name = "Spawn_Fx", type = "VARTYPE_STRING", value = "", },
property_27 = { name = "DepthOffset", type = "VARTYPE_FLOAT", value = 0, },
property_28 = { name = "PointDistance", type = "VARTYPE_FLOAT", value = -1, },
},
}
'''


def install():
    hod = os.path.join(BUILD, "fx_ramflame.hod")
    if not os.path.exists(hod):
        sys.exit(f"{hod} missing: run tools/build_ramflame.sh")
    fx = os.path.join(MOD, "data", "art", "fx")
    os.makedirs(os.path.join(fx, "cat_ramflame"), exist_ok=True)
    shutil.copyfile(hod, os.path.join(fx, "cat_ramflame", "cat_ramflame.hod"))
    with open(os.path.join(fx, "cat_ramflame.lua"), "w", newline="\n") as f:
        f.write(FX)
    print("installed data/art/fx/cat_ramflame.lua, cat_ramflame/cat_ramflame.hod")


if __name__ == "__main__":
    write_dae() if sys.argv[1:] == ["--dae"] else install()
