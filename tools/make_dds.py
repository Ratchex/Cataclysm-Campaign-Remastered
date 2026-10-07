"""Write an uncompressed BGRA8888 DDS with a full mip chain - the format HWRM uses for campaign tiles and
mission thumbnails (checked against the Taiidan Republic mod's trp.dds: 1024x512, 11 mips, 32-bit masks
00ff0000/0000ff00/000000ff/ff000000).

Usage: make_dds.py <input image> <output.dds> <width> <height>
The image is scaled to cover the target size and centre-cropped.
"""
import struct
import sys

from PIL import Image

DDSD_CAPS, DDSD_HEIGHT, DDSD_WIDTH, DDSD_PITCH, DDSD_PIXELFORMAT, DDSD_MIPMAPCOUNT = 0x1, 0x2, 0x4, 0x8, 0x1000, 0x20000
DDPF_ALPHAPIXELS, DDPF_RGB = 0x1, 0x40
DDSCAPS_COMPLEX, DDSCAPS_TEXTURE, DDSCAPS_MIPMAP = 0x8, 0x1000, 0x400000


def cover(img, w, h):
    scale = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((left, top, left + w, top + h))


def write_dds(img, path):
    img = img.convert("RGBA")
    w, h = img.size
    levels = [img]
    while levels[-1].width > 1 or levels[-1].height > 1:
        prev = levels[-1]
        levels.append(prev.resize((max(1, prev.width // 2), max(1, prev.height // 2)), Image.LANCZOS))
    header = struct.pack(
        "<4sIIIIIII44x", b"DDS ", 124,
        DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PITCH | DDSD_PIXELFORMAT | DDSD_MIPMAPCOUNT,
        h, w, w * 4, 0, len(levels))
    pixfmt = struct.pack("<II4sIIIII", 32, DDPF_RGB | DDPF_ALPHAPIXELS, b"\0\0\0\0", 32,
                         0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    caps = struct.pack("<IIIII", DDSCAPS_COMPLEX | DDSCAPS_TEXTURE | DDSCAPS_MIPMAP, 0, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(header + pixfmt + caps)
        for lvl in levels:
            r, g, b, a = lvl.split()
            f.write(Image.merge("RGBA", (b, g, r, a)).tobytes())  # BGRA byte order
    return len(levels)


if __name__ == "__main__":
    src, dst, w, h = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    n = write_dds(cover(Image.open(src), w, h), dst)
    print(f"{dst}: {w}x{h}, {n} mip levels")
