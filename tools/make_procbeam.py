"""The Processor's repair beams as aimed cones (Cataclysm: a very thin, stretched cone from each of its four side
beam points to the ship it repairs; user: it should track its target smoothly).

HWRM draws an effect on a ship's joint every frame, so a cone on a joint the ship's animation turns is smooth. The
script that knows the target (shiprules.lua CatProcessor_Tick) can't reach the madstate's Lua state (a probe: no
shared globals either way), only switch its state (SobGroup_SetMadState: NIS00-02 are the only states free on the
Processor; its 8 dock paths use the DockPath ones). So the script sends each beam's aim as bits, one per switch to
one of the two states it is not in, and the madstate (tools/overrides/ship/smt_processor/smt_processor.madstate)
decodes them and plays the beam's yaw / pitch clip toward the new angle, pausing it there.

  --mad OUT   the aim clips for the model's Beam<i>_Yaw / Beam<i>_Pitch joints (geo2dae.py --turret): Yaw<i> /
              Pitch<i> sweep -RANGE..+RANGE and back (a turn either way plays forward) once per speed tier,
              TIERS of them, each TIER_STEP times slower than the last from the ion turret's rate (the madstate
              plays the tier nearest a moving turret's speed toward its next angle); Clock (still, very long)
              is the madstate's clock
  --dae       the cone mesh (one mesh, one material, the fx shader) into build/ships/fx_procbeam/ for HODOR
  (none)      install: the cone .hod, the effect (data/art/fx/cat_procbeam.lua), its texture
Events: patch_events() (install_base.py) adds ProcBeam<i>_<band> to the Processor's .events: the cone on Beam<i>_Cone,
scaled to the band's length.

Run from tools/build_ship.sh (--mad), tools/build_procbeam.sh (--dae, HODOR, install).
"""
import math
import os
import re
import shutil
import struct
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mad2hwrm import FPS, chunk, keys_blob  # noqa: E402

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(MOD, "build", "ships", "fx_procbeam")
BEAMS = 4
RANGE = 45.0              # degrees each way: twProcessorAutoRepairConeAngle 90
CONE_LEN = 1400.0         # twProcessorAutoRepairDistance 4000 x 0.35 (shiprules.lua CAT_PROC_RANGE)
CONE_R0, CONE_R1 = 2.0, 44.0   # twProcessorAutoRepairBeamWidth 250 x 0.35 wide at full range: very thin
BANDS = (500.0, 950.0, 1400.0)  # cone lengths (shiprules.lua CAT_PROC_BANDS): the shortest that reaches the target
SEGS = 16
# the mesh is built MESH_LEN long (the events scale it to each band): stock fx_harvest's animation is in mesh units
# (pulse rings 100 apart, ripples ~13), so a shorter mesh shows the Worker's beam's few rings, not 14 of them
MESH_LEN = 350.0
RINGS = 120               # rings along the cone: fx_harvest moves vertices (ripples, rings) and lights them
V_REPEAT = 3.0            # texture repeats along the cone (it scrolls along V)
# seconds per sweep (one way) at a stock ion turret's rates (kus_destroyerion1 maxAzimuthSpeed 35, maxDeclinationSpeed
# 20 degrees a second; user: move like the destroyer's ion turret); shiprules.lua turns at the same rates
SWEEP_YAW = 90.0 / 35
SWEEP_PITCH = 90.0 / 20
TIERS = 9                 # speed tiers (smt_processor.madstate SMT_PROCESSOR_TIERS / _STEP: keep them the same)
TIER_STEP = 1.5
STOCK_TEX = "C:/Modding/Cataclysm-decomp/reference/hwrm/Homeworld2/art/fx/repair_fx/repair_beam/fx_repairbeam_diff.tga"
CLOCK = 100000.0


def write_mad(out):
    strings, stri = {}, bytearray()

    def sid(s):
        if s not in strings:
            strings[s] = len(stri)
            stri.extend(s.encode("latin-1") + b"\0")
        return strings[s]

    curves, marks, njref = [], [], 0

    def clip(name, joint, axis, samples, t1):
        nonlocal njref
        idx = []
        for ch in ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"):
            keys = samples if ch == "rotate" + axis else [(0.0, 0.0), (t1, 0.0)]
            nk, blob = keys_blob(keys)
            curves.append(struct.pack("<II", sid(f"{joint}_{ch}"), nk) + blob)
            idx.append(len(curves) - 1)
        marks.append(struct.pack("<I4fI", sid(name), 0.0, t1, 0.0, t1, 1)
                     + struct.pack("<II", sid(joint), 6) + struct.pack("<6I", *idx))
        njref += 1

    r = math.radians(RANGE)
    def tiers(sweep):
        keys, t = [(0.0, -r)], 0.0
        for k in range(TIERS):
            s = sweep * TIER_STEP ** k
            keys += [(t + s, r), (t + 2 * s, -r)]
            t += 2 * s
        return keys, t

    for i in range(BEAMS):
        clip(f"Yaw{i}", f"Beam{i}_Yaw", "Y", *tiers(SWEEP_YAW))
        clip(f"Pitch{i}", f"Beam{i}_Pitch", "X", *tiers(SWEEP_PITCH))
    clip("Clock", "Beam0_Cone", "Z", [(0.0, 0.0), (CLOCK, 0.0)], CLOCK)
    body = (b"MAD " + chunk(b"NAME", b"Homeworld2 MAD File") + chunk(b"VERS", bytes([4, 1, 0, 0]))
            + chunk(b"INFO", struct.pack("<5I", FPS, len(marks), len(curves), njref, 6 * njref))
            + chunk(b"STRI", bytes(stri)) + chunk(b"MARK", b"".join(marks)) + chunk(b"CURV", b"".join(curves)))
    with open(out, "wb") as f:
        f.write(chunk(b"FORM", body))
    print(f"{out}: {len(marks)} clips (Yaw/Pitch 0-{BEAMS - 1}, Clock)")


def fl(v):
    return " ".join(f"{c:.5g}" for c in v)


def write_dae():
    """A thin cone along +Z (the marker's axis: a -Z one rested pointing into the hull, calibration 2026-10-10), both
    windings (seen from inside and out), on stock fx_harvest (the shader of stock repair_beam / the Worker's repair
    beam, user: as close to it as can be; it scrolls the texture along V, ripples the cone and runs pulse rings down
    it). V runs along it, U around; the fade toward the tip is in the vertex colours (the texture scrolls)."""
    os.makedirs(BUILD, exist_ok=True)
    k_mesh = MESH_LEN / CONE_LEN
    pos, nrm, uv, col, tris = [], [], [], [], []
    for ring in range(RINGS + 1):
        f = ring / RINGS
        z, rad = MESH_LEN * f, (CONE_R0 + (CONE_R1 - CONE_R0) * f) * k_mesh
        c = max(0.0, 1 - f / 0.9) ** 1.2          # black over the last tenth (a bright tip read as a searchlight)
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
    name = "fx_procbeam"
    g = f"MULT[{name}_0]"
    mat = "MAT[procbeam]_SHD[fx_harvest]"
    img = f"IMG[{name}_DIFF]"
    dae = f'''<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
<asset><contributor><authoring_tool>Cataclysm-HWRM make_procbeam.py</authoring_tool></contributor><unit meter="1.0" name="meter"/><up_axis>Y_UP</up_axis></asset>
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
<geometry id="{g}" name="{g}"><mesh><source id="{g}-pos"><float_array id="{g}-pos-a" count="{3 * len(pos)}">{" ".join(fl(p) for p in pos)}</float_array><technique_common><accessor source="#{g}-pos-a" count="{len(pos)}" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source><source id="{g}-nrm"><float_array id="{g}-nrm-a" count="{3 * len(nrm)}">{" ".join(fl(p) for p in nrm)}</float_array><technique_common><accessor source="#{g}-nrm-a" count="{len(nrm)}" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source><source id="{g}-col"><float_array id="{g}-col-a" count="{4 * len(col)}">{" ".join(fl(p) for p in col)}</float_array><technique_common><accessor source="#{g}-col-a" count="{len(col)}" stride="4"><param name="R" type="float"/><param name="G" type="float"/><param name="B" type="float"/><param name="A" type="float"/></accessor></technique_common></source><source id="{g}-uv0"><float_array id="{g}-uv0-a" count="{2 * len(uv)}">{" ".join(fl(p) for p in uv)}</float_array><technique_common><accessor source="#{g}-uv0-a" count="{len(uv)}" stride="2"><param name="S" type="float"/><param name="T" type="float"/></accessor></technique_common></source><vertices id="{g}-v"><input semantic="POSITION" source="#{g}-pos"/></vertices><triangles count="{len(tris)}" material="{mat}"><input semantic="VERTEX" offset="0" source="#{g}-v"/><input semantic="NORMAL" offset="0" source="#{g}-nrm"/><input semantic="TEXCOORD" offset="0" set="0" source="#{g}-uv0"/><input semantic="COLOR" offset="0" set="0" source="#{g}-col"/><p>{" ".join(str(i) for t in tris for i in t)}</p></triangles></mesh></geometry>
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
    Image.open(STOCK_TEX).convert("RGBA").save(os.path.join(BUILD, name + "_DIFF.tga"))
    print(f"{BUILD}/{name}.dae: cone {MESH_LEN:g} long (scaled to the bands), {RINGS} rings, {len(tris)} triangles")


FX = '''-- Cataclysm-HWRM: the Processor's repair beam cone (tools/make_procbeam.py; on its Beam<i>_Cone joints, aimed by
-- its madstate). A mesh effect: the thin cone mesh on stock fx_harvest with stock
-- repair_beam's look (the Worker's repair beam, user: as close to it as can be): its texture, its 5 s colour cycle,
-- its blending and lighting.
fx = {
style = "STYLE_RING",
properties = {
property_00 = { name = "Radius", type = "VARTYPE_ARRAY_TIMEFLOAT", value = { 0, 1, 1, 1, }, },
property_01 = { name = "Offset", type = "VARTYPE_ARRAY_TIMEVECTOR3", value = { entry_00 = { 0, 0, 0, 0, }, entry_01 = { 1, 0, 0, 0, }, }, },
property_02 = { name = "SpinX", type = "VARTYPE_ARRAY_TIMEFLOAT", value = { 0, 0, 1, 0, }, },
property_03 = { name = "SpinY", type = "VARTYPE_ARRAY_TIMEFLOAT", value = { 0, 0, 1, 0, }, },
property_04 = { name = "SpinZ", type = "VARTYPE_ARRAY_TIMEFLOAT", value = { 0, 0, 1, 0, }, },
property_05 = { name = "Colour", type = "VARTYPE_ARRAY_TIMECOLOUR", value = { entry_00 = { 0, 1, 1, 1, 1, }, entry_01 = { 0.35224, 0.72209, 0.49140, 0.28737, 1, }, entry_02 = { 0.55224, 0.49434, 0.39566, 0.34763, 1, }, entry_03 = { 0.80000, 0.48113, 0.34909, 0.29957, 1, }, entry_04 = { 1, 1, 1, 1, 1, }, }, },
property_06 = { name = "RadiusEpsilon", type = "VARTYPE_FLOAT", value = 0, },
property_07 = { name = "RateEpsilon", type = "VARTYPE_FLOAT", value = 0, },
property_08 = { name = "SpinEpsilonX", type = "VARTYPE_FLOAT", value = 0, },
property_09 = { name = "SpinEpsilonY", type = "VARTYPE_FLOAT", value = 0, },
property_10 = { name = "SpinEpsilonZ", type = "VARTYPE_FLOAT", value = 0, },
property_11 = { name = "SpinRandom", type = "VARTYPE_BOOL", value = 0, },
property_12 = { name = "Duration", type = "VARTYPE_FLOAT", value = 5, },
property_13 = { name = "UseMesh", type = "VARTYPE_BOOL", value = 1, },
property_14 = { name = "UseDepthTest", type = "VARTYPE_BOOL", value = 1, },
property_15 = { name = "UseDepthSort", type = "VARTYPE_BOOL", value = 1, },
property_16 = { name = "Loop", type = "VARTYPE_BOOL", value = 1, },
property_17 = { name = "Billboard", type = "VARTYPE_BOOL", value = 0, },
property_18 = { name = "AlternateFOV", type = "VARTYPE_BOOL", value = 0, },
property_19 = { name = "SelfIlluminated", type = "VARTYPE_BOOL", value = 0, },
property_20 = { name = "Blending", type = "VARTYPE_INT", value = 4, },
property_21 = { name = "Texture", type = "VARTYPE_STRING", value = "DATA:ART/FX/REPAIR_FX/REPAIR_BEAM/FX_REPAIRBEAM_DIFF.TGA", },
property_22 = { name = "Mesh", type = "VARTYPE_STRING", value = "DATA:ART/FX/CAT_PROCBEAM/CAT_PROCBEAM.HOD", },
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
    hod = os.path.join(BUILD, "fx_procbeam.hod")
    if not os.path.exists(hod):
        sys.exit(f"{hod} missing: run tools/build_procbeam.sh")
    fx = os.path.join(MOD, "data", "art", "fx")
    os.makedirs(os.path.join(fx, "cat_procbeam"), exist_ok=True)
    os.makedirs(os.path.join(fx, "textures"), exist_ok=True)
    shutil.copyfile(hod, os.path.join(fx, "cat_procbeam", "cat_procbeam.hod"))
    with open(os.path.join(fx, "cat_procbeam.lua"), "w", newline="\n") as f:
        f.write(FX)
    old = os.path.join(fx, "textures", "cat_procbeam.tga")
    if os.path.exists(old):
        os.remove(old)
    print("installed data/art/fx/cat_procbeam.lua, cat_procbeam/cat_procbeam.hod")


ANIM = ("    ProcBeam{i}_{b} = {{ name = \"ProcBeam{i}_{b}\", length = 1, loop = 1, parent = \"\", minimum = 0, "
        "maximum = 0, markers = {{ \"\" }} }},\n")
EVENT = ("    ProcBeam{i}_{b}_fx = {{ {{ \"anim\", \"ProcBeam{i}_{b}\" }}, {{ \"animtime\", \"-1\" }}, "
         "{{ \"marker\", \"Beam{i}_Cone\" }}, {{ \"fx\", \"cat_procbeam\" }}, {{ \"fx_scale\", \"{s:.4f}\" }}, }},\n")


def patch_events(path=None):
    """ProcBeam<i>_<band> (band 1-3: BANDS) on the Processor's .events: the cone on Beam<i>_Cone at that length."""
    path = path or os.path.join(MOD, "data", "ship", "smt_processor", "smt_processor.events")
    text = open(path, encoding="latin-1").read()
    if "ProcBeam0_1" in text:
        return
    anims = events = ""
    for i in range(BEAMS):
        for b, length in enumerate(BANDS, 1):
            anims += ANIM.format(i=i, b=b)
            events += EVENT.format(i=i, b=b, s=length / MESH_LEN)
    for table, add in (("animations", anims), ("events", events)):
        m = re.search(table + r"\s*=\s*\{", text)
        assert m, f"{path}: no {table} table"
        text = (text[:m.end()] + "\n    -- Cataclysm-HWRM: the repair beam cones (tools/make_procbeam.py)\n" + add +
                text[m.end():])
    open(path, "w", encoding="latin-1", newline="").write(text)
    print(f"  {os.path.relpath(path, MOD)}: {BEAMS * len(BANDS)} repair beam cone events")


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--mad":
        write_mad(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == "--dae":
        write_dae()
    else:
        install()


if __name__ == "__main__":
    main()
