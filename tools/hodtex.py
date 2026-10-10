"""Textures out of an old-format (uncompressed) HWRM .hod, e.g. Cataclysm Remastered's smt_ms_sp.hod.

LMIP chunk: "LMIP", u32 size (big-endian), u32 name length, name + format ("DXT1" / "DXT5"), u32 mip count, then per
mip u32 width, u32 height and the DXT blocks (mip 0 first). Newer HODs (ours, from the current HODOR) keep the pixel
data in one compressed POOL chunk instead; this reads only the old layout.

Used by geo2dae.py --glow-from: CR's textures are Cataclysm's own upscaled 4x (same UV layout: luminance
correlation 0.99+ with the originals), so their GLOW maps fit our models.
"""
import re
import struct

import numpy as np


def _rgb565(c):
    return np.array([(c >> 11 & 31) * 255 / 31, (c >> 5 & 63) * 255 / 63, (c & 31) * 255 / 31])


def _colour_block(b, four):
    c0, c1, idx = struct.unpack("<HHI", b)
    p0, p1 = _rgb565(c0), _rgb565(c1)
    pal = [p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3] if (four or c0 > c1) else \
        [p0, p1, (p0 + p1) / 2, np.zeros(3)]
    return np.array([pal[idx >> (2 * k) & 3] for k in range(16)]).reshape(4, 4, 3)


def _alpha_block(b):
    a0, a1 = b[0], b[1]
    bits = int.from_bytes(b[2:8], "little")
    al = [a0, a1] + ([((6 - k) * a0 + (k + 1) * a1) / 7 for k in range(6)] if a0 > a1 else
                     [((4 - k) * a0 + (k + 1) * a1) / 5 for k in range(4)] + [0, 255])
    return np.array([al[bits >> (3 * k) & 7] for k in range(16)]).reshape(4, 4)


def decode(data, w, h, fmt):
    """DXT1 / DXT5 blocks -> RGBA float array (h, w, 4)."""
    bpb = 8 if fmt == "DXT1" else 16
    img = np.zeros((h, w, 4), np.float32)
    img[..., 3] = 255
    bw, bh = max(1, w // 4), max(1, h // 4)
    if len(data) < bw * bh * bpb:
        raise ValueError("truncated texture data")
    for by in range(bh):
        for bx in range(bw):
            blk = data[(by * bw + bx) * bpb:(by * bw + bx + 1) * bpb]
            y, x = by * 4, bx * 4
            if bpb == 8:
                img[y:y + 4, x:x + 4, :3] = _colour_block(blk, False)
            else:
                img[y:y + 4, x:x + 4, 3] = _alpha_block(blk[:8])
                img[y:y + 4, x:x + 4, :3] = _colour_block(blk[8:], True)
    return img


def textures(path, want):
    """{texture name: RGBA array} for the LMIP chunks whose name matches the regex want."""
    d = open(path, "rb").read()
    out = {}
    for m in re.finditer(rb"LMIP", d):
        j = m.start()
        if j + 16 > len(d):
            continue
        nl = struct.unpack_from("<I", d, j + 8)[0]
        if not 0 < nl < 200 or j + 16 + nl + 12 > len(d):
            continue
        name = d[j + 12:j + 12 + nl].decode("latin-1")
        fmt = d[j + 12 + nl:j + 16 + nl].decode("latin-1")
        if fmt not in ("DXT1", "DXT5") or not re.search(want, name, re.I):
            continue
        p = j + 16 + nl
        _, w, h = struct.unpack_from("<III", d, p)
        if not (0 < w <= 4096 and 0 < h <= 4096):
            continue
        n = max(1, w // 4) * max(1, h // 4) * (8 if fmt == "DXT1" else 16)
        out[name] = decode(d[p + 12:p + 12 + n], w, h, fmt)
    return out
