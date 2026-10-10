"""The Mimic's transformation (Cataclysm FUN_005b8f30 / FUN_004b5c90; NOTES.md "Mimic") as HWRM mesh effects.

Cataclysm: a phase runs 1 -> 0 (mimic) or 0 -> 1 (unmimic) by 0.05 per universe update (16 a second: 1.25 s). The
target's model is drawn as a shell: each vertex pushed out from the centre onto a sphere of radius R = 1.2 x the
larger of the two ships' radii, by the phase (at 1 a sphere, at 0 the model), its material faded by the phase. The
Mimic's own model is drawn while the phase is above 0.25; at 0 the shell is the target's model.

HWRM can't move a model's vertices from script, so the shell is a mesh effect (STYLE_RING with UseMesh: the Keeper's
phase effects): the target's model as one mesh (an effect mesh shows one mesh's material: its texture pages in
one atlas, tools/geo2dae.py --fx-mesh), additive and self-lit like the Keeper's (it fades by colour), scaled from R / (target radius) to 1. shiprules.lua plays them and swaps the ship:
  cat_mimic_in_<target>    on the Mimic when it starts: the shell shrinks and fades in over 1.25 s; the swap to the
                           disguise is at CAT_MIMIC_SWAP (1 s, two ship updates; Cataclysm drops the Mimic's model
                           at 0.94 s)
  cat_mimic_tail_<target>  on the disguise from the swap: the rest of the shell, onto its real model, fading out
  cat_mimic_out_<target>   on the Mimic swapped back (Unmimic): the shell from the disguise's model out to the sphere,
                           fading out over 1.25 s
Radii: Cataclysm's own models (lod0 .geo, the farthest vertex from the ship's centre).

Writes data/art/fx/cat_mimic_*.lua, data/art/fx/cat_mimic/<target>.hod, data/art/fx/textures/cat_white.tga.
Usage: tools/build_mimicfx.sh (the meshes, then this)
"""
import math
import os
import re
import shutil
import struct
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ship_variants  # noqa: E402

sys.path.insert(0, r"C:\Modding\Cataclysm-decomp\tools")
import geo2obj  # noqa: E402

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIG = r"C:\Modding\Cataclysm-decomp\extracted\big"
PHASE_TIME = 20 / 16      # 1 / 0.05 updates at 16 a second
SHELL = 1.2               # _DAT_0087813c
SWAP = 1.0                # shiprules.lua CAT_MIMIC_SWAP
COLOUR = (1.0, 1.0, 1.0)  # the shell's tint over its texture
ALPHA = 0.85              # the shell's brightness when formed (additive, as the Keeper's: it fades by colour)
MIMIC = "race_sect/smimic"
# Cataclysm's model of each disguise target (its Taiidan and Kushan fighters are the HW1 heavy ones)
CATACLYSM_MODEL = {
    "tai_interceptor": "race_taidan/theavyinterceptor", "tai_attackbomber": "race_taidan/tattackbomber",
    "tai_defender": "race_taidan/theavydefender", "kus_interceptor": "race_kushan/kheavyinterceptor",
    "kus_attackbomber": "race_kushan/kattackbomber", "bst_acolyte": "race_beast/bacolyte",
    "smt_acolyte": "race_sect/sacolyte",
}


def radius(model):
    path = os.path.join(BIG, model, "rl0", "lod0", os.path.basename(model) + ".geo")
    b, _, _, objs = geo2obj.parse(path)
    cache, r = {}, 0.0
    for i, o in enumerate(objs):
        w = geo2obj.world(objs, i, cache)
        for v in range(o["nV"]):
            x, y, z, _ = struct.unpack_from("<fffi", b, o["pV"] + v * 16)
            r = max(r, math.sqrt(sum(c * c for c in geo2obj.xform(w, x, y, z))))
    return r


FX = '''fx = {{
style = "STYLE_RING",
properties = {{
property_00 = {{ name = "Radius", type = "VARTYPE_ARRAY_TIMEFLOAT", value = {{ {radius} }}, }},
property_01 = {{ name = "Offset", type = "VARTYPE_ARRAY_TIMEVECTOR3", value = {{ entry_00 = {{ 0, 0, 0, 0, }}, entry_01 = {{ 1, 0, 0, 0, }}, }}, }},
property_02 = {{ name = "SpinX", type = "VARTYPE_ARRAY_TIMEFLOAT", value = {{ 0, 0, 1, 0, }}, }},
property_03 = {{ name = "SpinY", type = "VARTYPE_ARRAY_TIMEFLOAT", value = {{ 0, 0, 1, 0, }}, }},
property_04 = {{ name = "SpinZ", type = "VARTYPE_ARRAY_TIMEFLOAT", value = {{ 0, 0, 1, 0, }}, }},
property_05 = {{ name = "Colour", type = "VARTYPE_ARRAY_TIMECOLOUR", value = {{ {colour} }}, }},
property_06 = {{ name = "RadiusEpsilon", type = "VARTYPE_FLOAT", value = 0, }},
property_07 = {{ name = "RateEpsilon", type = "VARTYPE_FLOAT", value = 0, }},
property_08 = {{ name = "SpinEpsilonX", type = "VARTYPE_FLOAT", value = 0, }},
property_09 = {{ name = "SpinEpsilonY", type = "VARTYPE_FLOAT", value = 0, }},
property_10 = {{ name = "SpinEpsilonZ", type = "VARTYPE_FLOAT", value = 0, }},
property_11 = {{ name = "SpinRandom", type = "VARTYPE_BOOL", value = 0, }},
property_12 = {{ name = "Duration", type = "VARTYPE_FLOAT", value = {duration}, }},
property_13 = {{ name = "UseMesh", type = "VARTYPE_BOOL", value = 1, }},
property_14 = {{ name = "UseDepthTest", type = "VARTYPE_BOOL", value = 1, }},
property_15 = {{ name = "UseDepthSort", type = "VARTYPE_BOOL", value = 0, }},
property_16 = {{ name = "Loop", type = "VARTYPE_BOOL", value = 0, }},
property_17 = {{ name = "Billboard", type = "VARTYPE_BOOL", value = 0, }},
property_18 = {{ name = "AlternateFOV", type = "VARTYPE_BOOL", value = 0, }},
property_19 = {{ name = "SelfIlluminated", type = "VARTYPE_BOOL", value = 1, }},
property_20 = {{ name = "Blending", type = "VARTYPE_INT", value = 2, }},
property_21 = {{ name = "Texture", type = "VARTYPE_STRING", value = "DATA:ART/FX/TEXTURES/CAT_WHITE.TGA", }},
property_22 = {{ name = "Mesh", type = "VARTYPE_STRING", value = "{mesh}", }},
property_23 = {{ name = "SortOrder", type = "VARTYPE_INT", value = 0, }},
property_24 = {{ name = "RandomBitmap", type = "VARTYPE_BOOL", value = 0, }},
property_25 = {{ name = "BirthSpawn_Fx", type = "VARTYPE_STRING", value = "", }},
property_26 = {{ name = "Spawn_Fx", type = "VARTYPE_STRING", value = "", }},
property_27 = {{ name = "DepthOffset", type = "VARTYPE_FLOAT", value = 0, }},
property_28 = {{ name = "PointDistance", type = "VARTYPE_FLOAT", value = -1, }},
}},
}}
'''


def curve(points):
    """TIMEFLOAT {t, v, t, v, ...} over the effect's own 0-1 time."""
    return ", ".join(f"{t:.4f}, {v:.4f}" for t, v in points) + ","


def colours(points):
    """TIMECOLOUR entries {t, r, g, b, a}."""
    return " ".join(f"entry_{i:02d} = {{ {t:.4f}, {COLOUR[0] * a:.4f}, {COLOUR[1] * a:.4f}, {COLOUR[2] * a:.4f}, 1, }},"
                    for i, (t, a) in enumerate(points))


def write(name, mesh, duration, scale, alpha):
    with open(os.path.join(MOD, "data", "art", "fx", name + ".lua"), "w", newline="\n") as f:
        f.write(FX.format(radius=curve(scale), colour=colours(alpha), duration=f"{duration:.4f}", mesh=mesh))


ANIM = ("    {name} = {{ name = \"{name}\", length = {length:.4f}, loop = 0, parent = \"\", minimum = 0, "
        "maximum = 0, markers = {{ \"\" }} }},\n")
EVENT = ("    {name}_fx = {{ {{ \"anim\", \"{name}\" }}, {{ \"animtime\", \"0\" }}, {{ \"marker\", \"Root\" }}, "
         "{{ \"fx\", \"{fx}\" }}, {{ \"fx_scale\", \"1\" }}, }},\n")


def patch_events(path):
    """Add MimicIn_ / MimicOut_ / MimicTail_<target> (each playing that effect on the Root marker) to a ship's .events:
    started by shiprules.lua FX_StartEvent, they move with the ship (FX_PlayEffect stayed where it was started)."""
    text = open(path, encoding="latin-1").read()
    if "MimicIn_" in text:
        return
    anims, events = "", ""
    for target in sorted(ship_variants.DISGUISES):
        for name, fx, length in ((f"MimicIn_{target}", f"cat_mimic_in_{target}", PHASE_TIME),
                                 (f"MimicOut_{target}", f"cat_mimic_out_{target}", PHASE_TIME),
                                 (f"MimicTail_{target}", f"cat_mimic_tail_{target}", PHASE_TIME - SWAP)):
            anims += ANIM.format(name=name, length=length)
            events += EVENT.format(name=name, fx=fx)
    for table, add in (("animations", anims), ("events", events)):
        m = re.search(table + r"\s*=\s*\{", text)
        assert m, f"{path}: no {table} table"
        text = (text[:m.end()] + "\n    -- Cataclysm-HWRM: the Mimic's transformation (tools/make_mimicfx.py)\n" + add +
                text[m.end():])
    open(path, "w", encoding="latin-1", newline="").write(text)


def patch_all_events():
    for ship in ["smt_mimic"]:
        path = os.path.join(MOD, "data", "ship", ship, ship + ".events")
        if not os.path.exists(path):
            with open(path, "w", newline="\n") as f:
                f.write("effects = {\nanimations = {},\nevents = {}\n}\n")
        patch_events(path)


def main():
    tex = os.path.join(MOD, "data", "art", "fx", "textures")
    os.makedirs(tex, exist_ok=True)
    Image.new("RGBA", (8, 8), (255, 255, 255, 255)).save(os.path.join(tex, "cat_white.tga"))
    rm = radius(MIMIC)
    k = SWAP / PHASE_TIME                     # how far the shell has formed at the swap
    for target in sorted(ship_variants.DISGUISES):
        rt = radius(CATACLYSM_MODEL[target])
        s0 = SHELL * max(rt, rm) / rt          # the sphere, as a scale of the target's model
        at_swap = s0 + (1 - s0) * k
        # the target's Cataclysm model as one plain mesh (tools/build_mimicfx.sh): HWRM drew nothing of a ship model
        # (many meshes and materials on joints) as an effect mesh; the Keeper's one-mesh effect model showed
        mdir = os.path.join(MOD, "data", "art", "fx", "cat_mimic")
        os.makedirs(mdir, exist_ok=True)
        shutil.copyfile(os.path.join(MOD, "build", "ships", "fx_" + target, "fx_" + target + ".hod"),
                        os.path.join(mdir, target + ".hod"))
        mesh = f"DATA:ART/FX/CAT_MIMIC/{target.upper()}.HOD"
        # phase 1 -> 0 linear: scale s0 -> 1, opacity 0 -> ALPHA
        write(f"cat_mimic_in_{target}", mesh, PHASE_TIME, [(0, s0), (1, 1)], [(0, 0), (1, ALPHA)])
        # from the swap: the rest of the shrink, fading off the real model as Cataclysm's shell gives way to it
        write(f"cat_mimic_tail_{target}", mesh, PHASE_TIME - SWAP, [(0, at_swap), (1, 1)], [(0, ALPHA * k), (1, 0)])
        # phase 0 -> 1: the shell grows from the model to the sphere and fades out
        write(f"cat_mimic_out_{target}", mesh, PHASE_TIME, [(0, 1), (1, s0)], [(0, ALPHA), (1, 0)])
        print(f"{target}: radius {rt:.1f} (Mimic {rm:.1f}), shell from x{s0:.2f}")
    patch_all_events()


if __name__ == "__main__":
    if "--list-builds" in sys.argv:      # for tools/build_mimicfx.sh
        print(" ".join(f"{t}={CATACLYSM_MODEL[t]}" for t in ship_variants.DISGUISES))
    else:
        main()
