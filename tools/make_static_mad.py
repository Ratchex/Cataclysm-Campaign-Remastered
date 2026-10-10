"""A minimal HWRM .mad: one clip holding the given joints at rest (translation 0, rotation 0, their bind pose in a
model built with geo2dae.py --body / --part, joints at the origin). For a ship whose .madstate must run without any
animation of its own: the Mimic's showed its body and its disguise together, its madstate never called (no .mad).
Format: tools/mad2hwrm.py.

Usage: make_static_mad.py <out.mad> JOINT [JOINT ...]
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mad2hwrm import FPS, chunk, keys_blob  # noqa: E402

CLIP = ("Rest", 0.0, 1.0)


def main():
    out, joints = sys.argv[1], sys.argv[2:]
    strings, stri = {}, bytearray()

    def sid(s):
        if s not in strings:
            strings[s] = len(stri)
            stri.extend(s.encode("latin-1") + b"\0")
        return strings[s]

    name, t0, t1 = CLIP
    curves, refs = [], []
    for jn in joints:
        idx = []
        for ch in ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"):
            nk, blob = keys_blob([(t0, 0.0), (t1, 0.0)])
            curves.append(struct.pack("<II", sid(f"{jn}_{ch}"), nk) + blob)
            idx.append(len(curves) - 1)
        refs.append((jn, idx))
    m = struct.pack("<I4fI", sid(name), t0, t1, t0, t1, len(refs))
    for jn, idx in refs:
        m += struct.pack("<II", sid(jn), len(idx)) + struct.pack(f"<{len(idx)}I", *idx)
    body = (b"MAD " + chunk(b"NAME", b"Homeworld2 MAD File") + chunk(b"VERS", bytes([4, 1, 0, 0]))
            + chunk(b"INFO", struct.pack("<5I", FPS, 1, len(curves), len(refs), 6 * len(refs)))
            + chunk(b"STRI", bytes(stri)) + chunk(b"MARK", m) + chunk(b"CURV", b"".join(curves)))
    with open(out, "wb") as f:
        f.write(chunk(b"FORM", body))
    print(f"{out}: clip {name}, joints {', '.join(joints)}")


if __name__ == "__main__":
    main()
