"""HWRM .hod POOL chunks (current HODOR's compressed texture data): read and write.

POOL (decompiled from HODOR.exe: writer 0x421840, reader 0x434f60 / 0x434ea0, packer 0x4482a0, unpacker 0x448600):
  "POOL", u32 size (big-endian), u32 3518, then three pools, each u32 packed size, u32 unpacked size, data
  (packed == unpacked: stored as it is). Pool 1 is every LMIP's pixel data in order (mip 0 first).
Packed data: 32-bit little-endian flag words, read lowest bit first (a word holds 31 flags over a 1 sentinel bit),
each flag 0 = one literal byte, 1 = a match: back <offset> bytes from the output, <length> bytes (overlapping
copies byte by byte), coded by its low bits (HODOR 0x4481d0):
  ......00  1 byte:  offset = v >> 2,                         length 3
  ......01  2 bytes: offset = v >> 2,                         length 3
  ......10  2 bytes: offset = v >> 6,  length = (v >> 2 & 15) + 3
  .....011  3 bytes: offset = v >> 8,  length = (v >> 3 & 31) + 3
  .....111  4 bytes: offset = v >> 11, length = (v >> 3 & 255) + 3

Used by tools/make_background.py (a stock sky's texture, edited and stored unpacked).
"""
import struct


def unpack(src, size):
    out = bytearray(size)
    o = i = 0
    flags = 1
    n = len(src)
    while o < size:
        if flags == 1:
            flags = struct.unpack_from("<I", src, i)[0]
            i += 4
        if flags & 1:
            v = src[i] | src[i + 1] << 8 | src[i + 2] << 16 | (src[i + 3] << 24 if i + 3 < n else 0)
            t = v & 3
            if t == 0:
                off, ln, i = (v & 0xff) >> 2, 3, i + 1
            elif t == 1:
                off, ln, i = (v & 0xffff) >> 2, 3, i + 2
            elif t == 2:
                off, ln, i = (v & 0xffff) >> 6, ((v >> 2) & 15) + 3, i + 2
            elif v & 7 == 3:
                off, ln, i = (v & 0xffffff) >> 8, ((v >> 3) & 31) + 3, i + 3
            else:
                off, ln, i = v >> 11, ((v >> 3) & 255) + 3, i + 4
            s = o - off
            if off >= ln:
                out[o:o + ln] = out[s:s + ln]
            else:
                for k in range(ln):
                    out[o + k] = out[s + k]
            o += ln
        else:
            out[o] = src[i]
            o += 1
            i += 1
        flags >>= 1
    return out


def pools(hod):
    """(offset of the POOL chunk, [(packed, unpacked, data offset)] x 3)"""
    p = hod.index(b"POOL")
    q = p + 12
    out = []
    for _ in range(3):
        packed, unpacked = struct.unpack_from("<II", hod, q)
        out.append((packed, unpacked, q + 8))
        q += 8 + packed
    return p, out


def texture_data(hod):
    """pool 1 (every LMIP's pixels), unpacked"""
    _, ps = pools(hod)
    packed, unpacked, at = ps[0]
    raw = hod[at:at + packed]
    return bytes(raw) if packed == unpacked else bytes(unpack(raw, unpacked))


def replace_texture_data(hod, data):
    """the .hod with pool 1 replaced by <data>, stored unpacked"""
    p, ps = pools(hod)
    packed, unpacked, at = ps[0]
    assert len(data) == unpacked
    out = bytearray(hod[:at - 8]) + struct.pack("<II", len(data), len(data)) + data + hod[at + packed:]
    old = struct.unpack(">I", hod[p + 4:p + 8])[0]
    out[p + 4:p + 8] = struct.pack(">I", old + len(data) - packed)
    return bytes(out)
