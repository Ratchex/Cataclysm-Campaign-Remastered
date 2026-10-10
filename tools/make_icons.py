"""Our ability button icons, made from stock HWRM command icons (data/ui/newui/taskbar/commandicons/).

A stock command icon is a 128 x 512 strip of four 128 x 128 button states, top to bottom: disabled, normal, hover,
pressed. Each state is made from a stock icon turned and recoloured with another's colours, state by state: every
pixel takes the average colour of the colour icon's pixels of the same brightness (so outlines, bevels and highlights
keep their shading), alpha kept.

  cat_ico_upgrade.dds  Upgrade: the Dock icon turned 180 degrees (chevrons up), coloured like Move (user)

Usage: python tools/make_icons.py  (then tools/make_abilities.py, tools/install_cr.py)
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_dds import write_dds  # noqa: E402

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOCK = "C:/Modding/Cataclysm-decomp/reference/hwrm/Homeworld2/ui/newui/taskbar/commandicons"
OUT = os.path.join(MOD, "data", "ui", "newui", "taskbar", "commandicons")
CELL = 128
BINS = 64

# name: (shape icon, degrees to turn it, colour icon)
ICONS = {
    "cat_ico_upgrade": ("cmd_ico_dock", 180, "cmd_ico_move"),
}


def luma(a):
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def recolour(shape, colour):
    """shape's pixels in colour's palette: brightness -> colour's mean colour at that brightness (both RGBA float)."""
    vis = colour[..., 3] > 16                       # (the disabled state is half see-through)
    if not vis.any():
        return shape
    lc, cc = luma(colour)[vis], colour[..., :3][vis]
    idx = np.clip((lc / 256 * BINS).astype(int), 0, BINS - 1)
    lut, have = np.zeros((BINS, 3)), np.zeros(BINS, bool)
    for b in range(BINS):
        sel = idx == b
        if sel.any():
            lut[b], have[b] = cc[sel].mean(0), True
    for c in range(3):                              # brightness levels the colour icon lacks: in between
        lut[~have, c] = np.interp(np.flatnonzero(~have), np.flatnonzero(have), lut[have, c])
    # stretch the shape's brightness range over the colour icon's, so its darkest and brightest meet theirs
    ls = luma(shape)
    sv = shape[..., 3] > 16
    s0, s1 = np.percentile(ls[sv], [2, 98]) if sv.any() else (0, 255)
    c0, c1 = np.percentile(lc, [2, 98])
    t = np.clip((ls - s0) / max(1e-3, s1 - s0), 0, 1) * (c1 - c0) + c0
    out = shape.copy()
    out[..., :3] = lut[np.clip((t / 256 * BINS).astype(int), 0, BINS - 1)]
    return out


def make(name, shape_name, turn, colour_name):
    shape = Image.open(os.path.join(STOCK, shape_name + ".dds")).convert("RGBA")
    colour = Image.open(os.path.join(STOCK, colour_name + ".dds")).convert("RGBA")
    out = Image.new("RGBA", shape.size)
    for k in range(shape.height // CELL):
        box = (0, k * CELL, CELL, (k + 1) * CELL)
        s = np.asarray(shape.crop(box).rotate(turn), np.float64)
        c = np.asarray(colour.crop(box), np.float64)
        out.paste(Image.fromarray(np.clip(recolour(s, c), 0, 255).astype(np.uint8)), box[:2])
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".dds")
    write_dds(out, path)
    out.save(os.path.join(MOD, "build", name + ".png"))     # preview
    print(f"{os.path.relpath(path, MOD)}: {shape_name} turned {turn}, coloured like {colour_name}")


def main():
    for name, args in ICONS.items():
        make(name, *args)


if __name__ == "__main__":
    main()
