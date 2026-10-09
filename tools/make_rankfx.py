"""Rank stars for data/scripts/cataclysm/shiprules.lua: Cataclysm draws one star (overlayicons/expstar.lif,
magenta) per rank beside a selected ship's health bar (FUN_00507630). HWRM's health bars can't be
scripted, so each rank is a camera-facing sprite centred on the ship whose texture has the stars along its top
edge: they sit above the ship on screen. Writes data/art/fx/cat_rank<1-4>.lua and
data/art/fx/textures/cat_rank<1-4>.tga.

Usage: make_rankfx.py
"""
import os
import struct

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
LIF = r"C:\Modding\Cataclysm-decomp\extracted\big\overlayicons\expstar.lif"
SIZE = 128            # texture is SIZE x SIZE; each star SIZE / 4 (4 fit along the top)
RADIUS = 12           # sprite radius in metres at fx scale 1 (a fighter): stars 6 m, 12 m above its centre
DURATION = 1.0        # replayed every 0.5 s while the ship is selected (shiprules.lua CAT_TICK)


def star():
    """The 16x16 star (Willy 7 lif, flags 0x08: RGBA), magenta (194, 0, 255) as in the original (user)."""
    d = open(LIF, "rb").read()
    w, h, data = struct.unpack_from("<II", d, 16) + (struct.unpack_from("<I", d, 32)[0],)
    return Image.frombytes("RGBA", (w, h), d[data:data + w * h * 4])


FX = '''fx = {{
style = "STYLE_RING",
properties = {{
property_00 = {{ name = "Radius", type = "VARTYPE_ARRAY_TIMEFLOAT", value = {{ 0, {r}, 1, {r}, }}, }},
property_01 = {{ name = "Offset", type = "VARTYPE_ARRAY_TIMEVECTOR3", value = {{ entry_00 = {{ 0, 0, 0, 0, }}, entry_01 = {{ 1, 0, 0, 0, }}, }}, }},
property_02 = {{ name = "SpinZ", type = "VARTYPE_ARRAY_TIMEFLOAT", value = {{ 0, 0, 1, 0, }}, }},
property_03 = {{ name = "Colour", type = "VARTYPE_ARRAY_TIMECOLOUR", value = {{ entry_00 = {{ 0, 1, 1, 1, 1, }}, entry_01 = {{ 1, 1, 1, 1, 1, }}, }}, }},
property_04 = {{ name = "RadiusEpsilon", type = "VARTYPE_FLOAT", value = 0, }},
property_05 = {{ name = "RateEpsilon", type = "VARTYPE_FLOAT", value = 0, }},
property_06 = {{ name = "SpinEpsilon", type = "VARTYPE_FLOAT", value = 0, }},
property_07 = {{ name = "SpinRandom", type = "VARTYPE_BOOL", value = 0, }},
property_08 = {{ name = "Duration", type = "VARTYPE_FLOAT", value = {d}, }},
property_09 = {{ name = "UseMesh", type = "VARTYPE_BOOL", value = 0, }},
property_10 = {{ name = "UseDepthTest", type = "VARTYPE_BOOL", value = 0, }},
property_11 = {{ name = "Loop", type = "VARTYPE_BOOL", value = 0, }},
property_12 = {{ name = "Billboard", type = "VARTYPE_BOOL", value = 1, }},
property_13 = {{ name = "SelfIlluminated", type = "VARTYPE_BOOL", value = 1, }},
property_14 = {{ name = "Blending", type = "VARTYPE_INT", value = 1, }},
property_15 = {{ name = "Texture", type = "VARTYPE_STRING", value = "DATA:ART/FX/TEXTURES/CAT_RANK{n}.TGA", }},
property_16 = {{ name = "Mesh", type = "VARTYPE_STRING", value = "Data:art/fx/box.hod", }},
}},
frames = {{ timeStart = {{ 0, 1, }}, }},
}}
'''


def main():
    s = star().resize((SIZE // 4, SIZE // 4), Image.LANCZOS)
    tex = os.path.join(MOD, "data", "art", "fx", "textures")
    os.makedirs(tex, exist_ok=True)
    for n in range(1, 5):
        im = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 0))
        x0 = (SIZE - n * s.width) // 2
        for i in range(n):
            im.alpha_composite(s, (x0 + i * s.width, 0))
        im.save(os.path.join(tex, f"cat_rank{n}.tga"))
        with open(os.path.join(MOD, "data", "art", "fx", f"cat_rank{n}.lua"), "w", newline="\n") as f:
            f.write(FX.format(r=RADIUS, d=DURATION, n=n))
    print("rank star effects: data/art/fx/cat_rank1-4")


if __name__ == "__main__":
    main()
