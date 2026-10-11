"""The Ramming Frigate's push burn: a scaled-up copy of the Worker's thrusters (user), shown while it pushes.

HWRM draws an engine burn (setEngineBurn) as a row of camera-facing glow sprites trailing back from the nozzle,
shrinking and fading toward the tip, tinted the engine colour and added on (shaders fx_eng_burnbasic). A ship has
one burn and it only shows while the engine thrusts (the pushing frigate is pinned, not thrusting), so this copies
it as an effect: SPRITES billboard glows behind each nozzle along -Z (the nozzle joints are unrotated: their BURN
flames trail along -Z, geo2dae.py), the Kuun-Lan / Worker engine glow's blue (setEngineGlow 0.27 0.47 0.69),
flickering. cat_ramburn (a combo of cat_ramburn_<k>) plays on EngineNozzle1-3 while shiprules.lua CatRam_Tick pushes
(smt_rammingfrigate.events RamThrust, .madstate NIS01 / NIS02).

Usage: python tools/make_ramburn.py  (writes data/art/fx/cat_ramburn*.lua and textures/cat_ramburn.tga)
"""
import math
import os

from PIL import Image

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX = os.path.join(MOD, "data", "art", "fx")
SPRITES = 8          # (the Worker's burn has 6 divisions; 6 small ones read as separate dots, user)
LENGTH = 60.0        # behind the nozzle, last sprite (the frigate is 133 long)
R0, R1 = 20.0, 7.0   # sprite radius at the nozzle and at the tip: overlapping, one flame for its three nozzles (user)
COLOUR = tuple(round(c * 0.75, 3) for c in (0.55, 0.78, 1.0))   # the engine glow's blue (0.27, 0.47, 0.69), lifted
                                                                # toward white: a hard burn; dimmed for a frigate (user)
FLICKER = 0.12       # seconds per flicker cycle


def sprite(path, n=64):
    """a soft round glow, white (the effect tints it)"""
    im = Image.new("RGBA", (n, n))
    for y in range(n):
        for x in range(n):
            r = math.hypot(x - (n - 1) / 2, y - (n - 1) / 2) / (n / 2)
            v = int(255 * max(0.0, 1 - r) ** 1.8)
            im.putpixel((x, y), (v, v, v, v))
    im.save(path)


def ring(k):
    f = k / (SPRITES - 1)
    d, rad = LENGTH * f, R0 + (R1 - R0) * f
    a = (1 - f) ** 1.2 * 0.9 + 0.1
    c = [round(x * a, 3) for x in COLOUR]
    lo = [round(x * 0.75, 3) for x in c]
    ph = (k * 0.37) % 1          # each sprite flickers out of step
    return f'''-- Cataclysm-HWRM: sprite {k} of the Ramming Frigate's push burn (tools/make_ramburn.py)
fx = {{
style = "STYLE_RING",
properties = {{
property_00 = {{ name = "Radius", type = "VARTYPE_ARRAY_TIMEFLOAT", value = {{ 0, {rad:.3g}, {ph:.2f}, {rad * 1.15:.3g}, 1, {rad:.3g}, }}, }},
property_01 = {{ name = "Offset", type = "VARTYPE_ARRAY_TIMEVECTOR3", value = {{ entry_00 = {{ 0, 0, 0, {-d:.3g}, }}, entry_01 = {{ 1, 0, 0, {-d:.3g}, }}, }}, }},
property_02 = {{ name = "SpinX", type = "VARTYPE_ARRAY_TIMEFLOAT", value = {{ 0, 0, 1, 0, }}, }},
property_03 = {{ name = "SpinY", type = "VARTYPE_ARRAY_TIMEFLOAT", value = {{ 0, 0, 1, 0, }}, }},
property_04 = {{ name = "SpinZ", type = "VARTYPE_ARRAY_TIMEFLOAT", value = {{ 0, 0, 1, 0, }}, }},
property_05 = {{ name = "Colour", type = "VARTYPE_ARRAY_TIMECOLOUR", value = {{ entry_00 = {{ 0, {c[0]}, {c[1]}, {c[2]}, 1, }}, entry_01 = {{ {ph:.2f}, {lo[0]}, {lo[1]}, {lo[2]}, 1, }}, entry_02 = {{ 1, {c[0]}, {c[1]}, {c[2]}, 1, }}, }}, }},
property_06 = {{ name = "RadiusEpsilon", type = "VARTYPE_FLOAT", value = 0, }},
property_07 = {{ name = "RateEpsilon", type = "VARTYPE_FLOAT", value = 0, }},
property_08 = {{ name = "SpinEpsilonX", type = "VARTYPE_FLOAT", value = 0, }},
property_09 = {{ name = "SpinEpsilonY", type = "VARTYPE_FLOAT", value = 0, }},
property_10 = {{ name = "SpinEpsilonZ", type = "VARTYPE_FLOAT", value = 0, }},
property_11 = {{ name = "SpinRandom", type = "VARTYPE_BOOL", value = 0, }},
property_12 = {{ name = "Duration", type = "VARTYPE_FLOAT", value = {FLICKER}, }},
property_13 = {{ name = "UseMesh", type = "VARTYPE_BOOL", value = 0, }},
property_14 = {{ name = "UseDepthTest", type = "VARTYPE_BOOL", value = 1, }},
property_15 = {{ name = "UseDepthSort", type = "VARTYPE_BOOL", value = 1, }},
property_16 = {{ name = "Loop", type = "VARTYPE_BOOL", value = 1, }},
property_17 = {{ name = "Billboard", type = "VARTYPE_BOOL", value = 1, }},
property_18 = {{ name = "AlternateFOV", type = "VARTYPE_BOOL", value = 0, }},
property_19 = {{ name = "SelfIlluminated", type = "VARTYPE_BOOL", value = 1, }},
property_20 = {{ name = "Blending", type = "VARTYPE_INT", value = 2, }},
property_21 = {{ name = "Texture", type = "VARTYPE_STRING", value = "DATA:ART/FX/TEXTURES/CAT_RAMBURN.TGA", }},
property_22 = {{ name = "Mesh", type = "VARTYPE_STRING", value = "", }},
property_23 = {{ name = "SortOrder", type = "VARTYPE_INT", value = 2, }},
property_24 = {{ name = "RandomBitmap", type = "VARTYPE_BOOL", value = 0, }},
property_25 = {{ name = "BirthSpawn_Fx", type = "VARTYPE_STRING", value = "", }},
property_26 = {{ name = "Spawn_Fx", type = "VARTYPE_STRING", value = "", }},
property_27 = {{ name = "DepthOffset", type = "VARTYPE_FLOAT", value = 0, }},
property_28 = {{ name = "PointDistance", type = "VARTYPE_FLOAT", value = 0, }},
}},
}}
'''


def main():
    os.makedirs(os.path.join(FX, "textures"), exist_ok=True)
    sprite(os.path.join(FX, "textures", "cat_ramburn.tga"))
    for k in range(SPRITES):
        with open(os.path.join(FX, f"cat_ramburn_{k}.lua"), "w", newline="\n") as f:
            f.write(ring(k))
    props = "".join(f'property_{k:02d} = {{ name = "FX{k + 1}", type = "VARTYPE_STRING", value = "CAT_RAMBURN_{k}", }},\n'
                    for k in range(SPRITES))
    with open(os.path.join(FX, "cat_ramburn.lua"), "w", newline="\n") as f:
        f.write("-- Cataclysm-HWRM: the Ramming Frigate's push burn, its sprites together (tools/make_ramburn.py)\n"
                f'fx = {{\nstyle = "STYLE_COMBO",\nproperties = {{\n{props}}},\n}}\n')
    print(f"data/art/fx/cat_ramburn.lua: {SPRITES} sprites over {LENGTH:g}, radius {R0:g} -> {R1:g}")


if __name__ == "__main__":
    main()
