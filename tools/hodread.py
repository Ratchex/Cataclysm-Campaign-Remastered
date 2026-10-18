"""Read an HWRM .hod (stock HWRM and Cataclysm Remastered, old and new HODOR layouts): joints, materials, textures and
meshes, so Remastered models can be rebuilt into ours (tools/hod2dae.py). Gearbox's RODOH reads only Homeworld 2
Classic HODs (it writes nothing for these).

Layout (HomeworldRM.exe's loader: FUN_007c11f0 HVMD / POOL, FUN_007c1b30 the HVMD handlers, FUN_007ca6a0 MULT,
FUN_007b5f70 BMSH, FUN_007c2270 STAT, FUN_007be730 LMIP, FUN_007c0eb0 the pools):
  chunks: "FORM", u32 size (big-endian), type, children | "NRML", u32 size, type, u32 version (big-endian), data |
          any other tag, u32 size, data.
  POOL (new HODOR): u32 3518, three pools (tools/hodpool.py): 0 every LMIP's pixels, 1 every vertex, 2 every index,
          each read in file order. Without a POOL (old HODOR, CR's) the same bytes sit inline where they are read.
  HVMD: LMIP (texture: name, format "DXT1"/"DXT5"/..., u32 mips, per mip u32 w, u32 h, pixels), NRML STAT (material:
          name, shader, u32 params, per param u32 type, u32 size, data, then (version >= 1001) its name; type 5 a
          texture (data: the LMIP index), type 4 four floats), NRML MULT (mesh: name, parent joint, u32 LODs, then per
          LOD a NRML BMSH: u32 LOD, u32 parts, per part u32 material, u32 vertex mask, u32 vertices, the vertices
          (mask bits: 1 position xyzw, 2 normal xyzw, 4 colour u32, 8 uv0, 0x10 / 0x20 / 0x40 uv1-3 (version 1401),
          0x2000 tangent xyz, 0x4000 binormal xyz), u16 0xffff, u32 indices, the u16 indices: a triangle list).
  DTRM: FORM HIER: joints (name, parent, 9 floats: position, rotation (radians, x y z), joint orient).
"""
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hodpool  # noqa: E402
import hodtex  # noqa: E402

DECODE_DXT = True   # False: DXT textures left undecoded (slow in pure Python), "image" None


class Reader:
    def __init__(self, path):
        self.d = open(path, "rb").read()
        self.pools = None
        self.cur = [0, 0, 0]
        self.textures, self.materials, self.meshes, self.joints = [], [], [], []

    # -- the pools, or inline data when there are none
    def take(self, pool, n, inline):
        if self.pools is None:
            b = self.d[inline[0]:inline[0] + n]
            inline[0] += n
            return b
        b = self.pools[pool][self.cur[pool]:self.cur[pool] + n]
        self.cur[pool] += n
        return b

    def read_pool(self, o):
        p = o + 4
        self.pools = []
        for _ in range(3):
            ps, us = struct.unpack_from("<II", self.d, p)
            raw = self.d[p + 8:p + 8 + ps]
            self.pools.append(bytes(raw) if ps == us else bytes(hodpool.unpack(raw, us)))
            p += 8 + ps

    def walk(self, o, end, parent=""):
        d = self.d
        while o + 8 <= end:
            tag = d[o:o + 4].decode("latin-1")
            size = struct.unpack_from(">I", d, o + 4)[0]
            nxt = o + 8 + size
            if tag == "FORM":
                kind = d[o + 8:o + 12].decode("latin-1")
                if kind == "HIER":
                    self.read_hier(o + 12, nxt)
                elif kind not in ("VERS", "NAME"):
                    self.walk(o + 12, nxt, kind)
            elif tag == "NRML":
                kind = d[o + 8:o + 12].decode("latin-1")
                ver = struct.unpack_from(">I", d, o + 12)[0]
                if kind == "STAT":
                    self.read_stat(o + 16, ver)
                elif kind == "MULT":
                    self.read_mult(o + 16, nxt, ver)
            elif tag == "POOL":
                self.read_pool(o + 8)
            elif tag == "LMIP":
                self.read_lmip(o + 8)
            o = nxt

    @staticmethod
    def string(d, p):
        n = struct.unpack_from("<I", d, p)[0]
        return d[p + 4:p + 4 + n].decode("latin-1"), p + 4 + n

    def read_lmip(self, p):
        d = self.d
        name, p = self.string(d, p)
        fmt = d[p:p + 4].decode("latin-1")
        mips = struct.unpack_from("<I", d, p + 4)[0]
        p += 8
        inline = [p]
        img = None
        for k in range(mips):
            w, h = struct.unpack_from("<II", d, inline[0])
            inline[0] += 8
            if fmt in ("DXT1", "DXT3", "DXT5"):
                n = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * (8 if fmt == "DXT1" else 16)
            elif fmt == "8888":
                n = w * h * 4
            else:
                n = w * h * 4
            data = self.take(0, n, inline)
            if k == 0 and fmt in ("DXT1", "DXT5") and DECODE_DXT:
                img = hodtex.decode(data, w, h, fmt)
            elif k == 0 and fmt == "8888":   # uncompressed RGBA (stock skies' sphere textures: ez14 orange)
                import numpy as np
                img = np.frombuffer(bytes(data), np.uint8).reshape(h, w, 4)
        self.textures.append({"name": name, "format": fmt, "image": img})

    def read_stat(self, p, ver):
        d = self.d
        name, p = self.string(d, p)
        shader, p = self.string(d, p)
        n = struct.unpack_from("<I", d, p)[0]
        p += 4
        params = []
        for _ in range(n):
            typ, size = struct.unpack_from("<II", d, p)
            data = d[p + 8:p + 8 + size]
            p += 8 + size
            pname = ""
            if ver >= 1001:
                pname, p = self.string(d, p)
            params.append((typ, pname, data))
        tex = {}
        for typ, pname, data in params:
            if typ == 5:
                tex[pname.lstrip("$")] = struct.unpack_from("<i", data)[0]
        self.materials.append({"name": name, "shader": shader, "textures": tex, "params": params})

    def read_mult(self, p, end, ver):
        d = self.d
        name, p = self.string(d, p)
        parent, p = self.string(d, p)
        lods = struct.unpack_from("<I", d, p)[0]
        p += 4
        mesh = {"name": name, "parent": parent, "lods": {}}
        while p + 8 <= end:
            size = struct.unpack_from(">I", d, p + 4)[0]
            if d[p:p + 4] == b"NRML" and d[p + 8:p + 12] == b"BMSH":
                bver = struct.unpack_from(">I", d, p + 12)[0]
                lod, parts = self.read_bmsh(p + 16, bver)
                mesh["lods"][lod] = parts
            elif d[p:p + 4] == b"FORM" and d[p + 8:p + 12] == b"TAGS":
                mesh["tags"] = d[p + 12:p + 8 + size]      # (u32 length, text: "DoScar")
            p += 8 + size
        self.meshes.append(mesh)

    def read_bmsh(self, p, ver):
        d = self.d
        lod, nparts = struct.unpack_from("<II", d, p)
        inline = [p + 8]
        parts = []
        for _ in range(nparts):
            mat, mask, nv = struct.unpack_from("<III", d, inline[0])
            inline[0] += 12
            fields = [(1, "pos", 16), (2, "nrm", 16), (4, "col", 4), (8, "uv0", 8)]
            if ver != 1400:
                fields += [(0x10, "uv1", 8), (0x20, "uv2", 8), (0x40, "uv3", 8)]
            fields += [(0x2000, "tan", 12), (0x4000, "bin", 12)]
            stride = sum(sz for bit, _, sz in fields if mask & bit)
            raw = self.take(1, nv * stride, inline)
            pos, nrm, uv = [], [], []
            for i in range(nv):
                q = i * stride
                for bit, key, sz in fields:
                    if not mask & bit:
                        continue
                    if key == "pos":
                        pos.append(struct.unpack_from("<3f", raw, q))
                    elif key == "nrm":
                        nrm.append(struct.unpack_from("<3f", raw, q))
                    elif key == "uv0":
                        uv.append(struct.unpack_from("<2f", raw, q))
                    q += sz
            kind = struct.unpack_from("<h", d, inline[0])[0]
            inline[0] += 2
            ni = struct.unpack_from("<I", d, inline[0])[0]
            inline[0] += 4
            idx = struct.unpack(f"<{ni}H", self.take(2, ni * 2, inline))
            parts.append({"material": mat, "mask": mask, "pos": pos, "nrm": nrm, "uv": uv, "idx": idx,
                          "kind": kind})
        return lod, parts

    def read_hier(self, p, end):
        d = self.d
        # (stock: an i32 minus the joint count first) u32 name length, name, u32 parent length, parent, 9 floats;
        # CR's older layout: 12 floats + 3 bytes
        for start, nfloat, extra in ((p + 4, 9, 0), (p, 9, 0), (p + 4, 12, 3), (p, 12, 3)):
            q, out = start, []
            try:
                while q + 8 <= end:
                    name, q = self.string(d, q)
                    par, q = self.string(d, q)
                    v = struct.unpack_from(f"<{nfloat}f", d, q)
                    q += 4 * nfloat + extra
                    if not name.isprintable():
                        raise ValueError
                    out.append({"name": name, "parent": par, "pos": v[0:3], "rot": v[3:6], "orient": v[6:9]})
                if out and out[0]["name"] == "Root":
                    self.joints = out
                    return
            except (struct.error, ValueError, UnicodeDecodeError):
                pass

    def read(self):
        self.walk(0, len(self.d))
        return self


def read(path):
    return Reader(path).read()


if __name__ == "__main__":
    r = read(sys.argv[1])
    print(f"{len(r.textures)} textures, {len(r.materials)} materials, {len(r.meshes)} meshes, {len(r.joints)} joints")
    for t in r.textures:
        print("  tex", t["name"], t["format"], None if t["image"] is None else t["image"].shape)
    for m in r.materials:
        print("  mat", m["name"], m["shader"], m["textures"])
    for m in r.meshes:
        print("  mesh", m["name"], "parent", m["parent"], {k: [(p["material"], len(p["pos"]), len(p["idx"])) for p in v]
                                                          for k, v in sorted(m["lods"].items())})
    for j in r.joints[:12]:
        print("  joint", j["name"], j["parent"], [round(x, 2) for x in j["pos"]], [round(x, 3) for x in j["rot"]])
    if r.pools is not None:
        print("pools used", r.cur, "of", [len(x) for x in r.pools])
