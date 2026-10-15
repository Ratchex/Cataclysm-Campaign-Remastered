"""Convert a Cataclysm background (.btg) to an HWRM background (data/background/<name>/).

HW1 (Game/BTG.c): the background is a sphere of Gouraud-coloured triangles plus textured star quads, drawn from a
2D page (pageWidth x pageHeight): btgConvertAVert maps page (x, y) to theta = 2 pi (pageWidth - 1 - x) / pageWidth
+ 90 deg + the level's theta offset (mission file "Background <name>, <theta>, <phi>": btgSetTheta stores -theta),
phi = pi y / pageHeight + phi offset; HW1 world (cos t sin p, sin t sin p, cos p). Vertex colour = rgb x alpha x
brightness (on the black background). Stars: a quad of the texture's pixel size, colour rgba.

HWRM background .hod (decoded from stock background/ez01/ez01.hod, Gearbox's HW1 conversions):
  FORM VERS (u32 1000) | NRML BGLT (u32 0) | FORM BGMS { NRML BMSH ... } | FORM BGSG ... | NRML STRF
  BMSH: "BMSH", 5 header words (copied from stock), u32 vertex count, per vertex x y z w(1) f32 + colour bytes
        (127, r/2, g/2, b/2), then u16 0xFFFF, u32 index count, u16 triangle-list indices. Positions on a radius-100
        sphere, HWRM axes = HW1 (-x, z, y) (tools/mission2level.py pos).
  BGSG: one FORM per star texture: "BGSG", u32 name length, name (background/stars/<name>), u32 count, per star
        x y z, size, r g b a (f32; size ~0.2 per texture pixel, colours half scale like the vertices').
  STRF: the far star field (stock ez01's kept: HW1's universe stars are generic too); BGLT: stock's (empty).
That .hod is legacy data: what HWRM draws is <name>_light.hod, an ordinary HODOR model (stock ez01_light.hod:
mesh PRE_Space, a sphere with material "ez01" on shader "background", texture ez01_remastered_DIFF 8888 4096x2048
equirectangular; a planet mesh POST_Planet; HVMD LITE: directionalLight1/2 + ambientLight1, the scene's lights).
Ours (--sky, run by tools/build_background.sh, which also runs HODOR): the BTG page itself is equirectangular
(theta linear in x, phi in y), so it is rendered to a texture (Gouraud triangles, colour x alpha x brightness; the
star bitmaps added at their pixel size) and put on a sphere whose vertices come from page points through the same
projection; HODOR builds build/backgrounds/<name>/<name>_light.hod, and --splice adds stock ez01's LITE chunk (the
lights; Cataclysm's own, the mission's .hsf, not converted yet). No planet, so no .mad, and the .lua files are
ez01's without the lens flare / sun following the planet rig's Flare_Key joint. No cube maps (mods' backgrounds
ship without them, e.g. Battlestar Galactica: Fleet Command's).

Usage: make_background.py <btg> <name> [--theta DEG] [--phi DEG]   e.g. mission01.btg cat_m01 --theta 200
       (tools/install_base.py runs it for BACKGROUNDS: the light .hod is 22 MB of stock data, not kept in git)
"""
import argparse
import math
import os
import shutil
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
BIG = r"C:\Modding\Cataclysm-decomp\extracted\big\btg"
STOCK = r"C:\Modding\Cataclysm-decomp\reference\hwrm\bg\background"   # HWBackgrounds.big (tools/hw2big.py)
TEMPLATE = "ez01"
RADIUS = 100.0
STAR_SIZE = 0.2          # HWRM size per texture pixel (stock ez01: 16-px B02 stars 3.19, 8-px B03 1.6)


def read_btg(path):
    d = open(path, "rb").read()
    fmt = "<4I2iI2i6i5Ii"
    h = dict(zip("ver nverts nstars npolys xs ys zoom pw ph r g b bgr bgg bgb bv bp bs bo bb mode".split(),
                 struct.unpack_from(fmt, d, 0)))
    o = struct.calcsize(fmt)
    verts, stars, polys = [], [], []
    for _ in range(h["nverts"]):
        verts.append(struct.unpack_from("<I2d5i", d, o))
        o += 40
    for _ in range(h["nstars"]):
        s = struct.unpack_from("<I2d4i", d, o)
        o += 36
        n = struct.unpack_from("<I", d, o)[0]
        name = d[o + 4:o + 4 + n].split(b"\0")[0].decode("latin-1")
        o += 4 + n
        stars.append(s + (name,))
    for _ in range(h["npolys"]):
        polys.append(struct.unpack_from("<4I", d, o))
        o += 16
    return h, verts, stars, polys


def project(h, x, y, theta, phi):
    """btgConvertAVert, then HW1 world -> HWRM axes, on the radius-100 sphere."""
    pw, ph = h["pw"], h["ph"]
    t = 2 * math.pi * ((pw - 1.0) - x) / pw + math.radians(-theta) + math.radians(90)
    p = math.pi * y / ph + math.radians(-phi)
    hx, hy, hz = math.cos(t) * math.sin(p), math.sin(t) * math.sin(p), math.cos(p)
    return (-hx * RADIUS, hz * RADIUS, hy * RADIUS)


def chunks(d, o, end):
    while o + 8 <= end:
        tag, n = d[o:o + 4], struct.unpack(">I", d[o + 4:o + 8])[0]
        yield tag, o, n
        o += 8 + n


def chunk(tag, body):
    return tag + struct.pack(">I", len(body)) + body


def texture_size(name):
    from PIL import Image
    return Image.open(os.path.join(BIG, "bitmaps", name.lower())).size


# Cataclysm missions' backgrounds: HWRM name -> (.btg, theta, phi) from the mission file's "Background" line
# Off: Mission 1 uses stock ez14 (user: port a sky only when no stock HWRM one fits; build_mission.py BACKGROUNDS).
# The converted cat_m01 looked wrong in game (2026-10-09); fix it here before porting a sky that has no equivalent.
BACKGROUNDS = {}

# Stock skies relit with a Cataclysm mission's lights (user: Mission 1 looked harshly lit and shadowed; Cataclysm's
# mission01.hsf has a high pale-yellow ambient, a moderate orange key and a weak red fill, stock ez14 two key lights
# above 1.0 and little ambient). Written to data/background/<sky>/<sky>_light.hod by tools/install_base.py.
RELIGHT = {"ez14": "mission01"}
# ...and with a glow in their sky texture dimmed: sky -> (u, v centre, u, v radius (Gaussian sigma), r, g, b cut at the
# centre). ez14: the bright glow behind its main nebula (user: the nebula is supposed to be a dark smear; reduce the
# light behind it a decent amount). Blue cut most, red least: cut evenly the white core went grey.
DARKEN = {"ez14": (0.533, 0.508, 0.13, 0.15, (0.35, 0.5, 0.65))}
HSF_DIR = r"C:\Modding\Cataclysm-decomp\extracted\big\hsf"
BIGFILE = r"C:\Program Files (x86)\Steam\steamapps\common\Homeworld\HomeworldRM\Data\HWBackgrounds.big"


def read_hsf(path):
    """HW1 Game/Light.c lightParseHSF: header "rrasberry"[12], version, nLights; per light (44 bytes) type (0 distant,
    5 ambient), x y z, h p b, cone, edge, r g b (bytes), pad, intensity. -> [(type, xyz, rgb x intensity)]."""
    d = open(path, "rb").read()
    n = struct.unpack_from("<I", d, 16)[0]
    out = []
    for k in range(min(n, (len(d) - 20) // 44)):
        q = 20 + 44 * k
        t, x, y, z = struct.unpack_from("<I3f", d, q)
        inten = struct.unpack_from("<f", d, q + 40)[0]
        out.append((t, (x, y, z), tuple(c / 255 * inten for c in d[q + 36:q + 39])))
    return out


def hsf_to_hwrm(v):
    """HSF light vector -> HWRM: HW1 _inplace_glify (-90 about Z, then -90 about X) gives HW1 world (y, z, x); HW1
    world -> HWRM axes (-x, z, y) as tools/mission2level.py pos. (Gearbox's own ez skies were relit by hand: no
    axis map matches their lights to HW1's.)"""
    x, y, z = v
    return (-y, x, z)


def relight(sky, mission):
    """Copy stock <sky>_light.hod with its LITE lights replaced by Cataclysm's <mission>.hsf: ambientLight1 = the
    ambient light, directionalLight1/2 = the distant lights in order (same names, so the chunk keeps its size), each
    at its stock light's distance; colour = rgb x intensity (diffuse and specular), the ambient not doubled (Gearbox's
    ez14 ambient 0.25 = its HW1 .hsf value). LITE: u32 count; per light name, u32 type (2 directional, 0 ambient),
    position 3f, colour 3f, specular 3f, 2f. Returns the written path relative to data/."""
    src = os.path.join(STOCK, sky, sky + "_light.hod")
    if not os.path.exists(src):
        import subprocess
        import sys
        subprocess.run([sys.executable, r"C:\Modding\Cataclysm-decomp\tools\hw2big.py", BIGFILE,
                        os.path.dirname(STOCK), sky + "_light.hod"], check=True)
    d = bytearray(open(src, "rb").read())
    i = d.index(b"LITE")
    end = i + 8 + struct.unpack(">I", d[i + 4:i + 8])[0]
    lights = read_hsf(os.path.join(HSF_DIR, mission + ".hsf"))
    ambient = [l for l in lights if l[0] == 5]
    distant = [l for l in lights if l[0] == 0]
    q, n = i + 12, struct.unpack_from("<I", d, i + 8)[0]
    for _ in range(n):
        ln = struct.unpack_from("<I", d, q)[0]
        name = d[q + 4:q + 4 + ln].decode()
        f = q + 8 + ln
        if f + 44 > end:
            raise SystemExit(f"{src}: LITE chunk shorter than expected")
        pos = struct.unpack_from("<3f", d, f)
        light = None
        if name.startswith("ambient") and ambient:
            light = ambient[0]
        elif name.startswith("directional") and distant:
            k = int(name[-1]) - 1
            light = distant[k] if k < len(distant) else None
        if light is None:                    # no such Cataclysm light: switch it off
            struct.pack_into("<6f", d, f + 12, *([0.0] * 6))
        else:
            if name.startswith("directional"):
                v = hsf_to_hwrm(light[1])
                m = math.sqrt(sum(c * c for c in v)) or 1.0
                dist = math.sqrt(sum(c * c for c in pos)) or 200.0
                struct.pack_into("<3f", d, f, *(c / m * dist for c in v))
            struct.pack_into("<6f", d, f + 12, *(light[2] + light[2]))
        print(f"  {sky} {name}: {'off' if light is None else tuple(round(c, 3) for c in light[2])}")
        q = f + 44
    if sky in DARKEN:
        d = darken(bytes(d), *DARKEN[sky])
    out = os.path.join(MOD, "data", "background", sky, sky + "_light.hod")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "wb").write(d)
    return [f"background/{sky}/{sky}_light.hod"]


def darken(hod, cu, cv, ru, rv, cut):
    """The sky texture (one 8888 LMIP, RGBA, its pixels in the compressed POOL: tools/hodpool.py) with a Gaussian
    patch dimmed by <cut> per channel at its centre; mips rebuilt from it; stored unpacked."""
    import numpy as np
    from PIL import Image
    import hodpool
    i = hod.index(b"LMIP")
    n = struct.unpack_from("<I", hod, i + 8)[0]
    fmt = hod[i + 12 + n:i + 16 + n]
    if fmt != b"8888":
        raise SystemExit(f"darken: texture format {fmt}, only 8888")
    mips = struct.unpack_from("<I", hod, i + 16 + n)[0]
    dims = [struct.unpack_from("<II", hod, i + 20 + n + 8 * k) for k in range(mips)]
    data = hodpool.texture_data(hod)
    w, h = dims[0]
    img = np.frombuffer(data[:w * h * 4], np.uint8).reshape(h, w, 4).astype(np.float32)
    v, u = np.mgrid[0:h, 0:w]
    g = np.exp(-(((u / w - cu) / ru) ** 2 + ((v / h - cv) / rv) ** 2) / 2)[:, :, None]
    img[:, :, :3] *= 1 - np.array(cut, np.float32) * g
    top = Image.fromarray(img.clip(0, 255).astype(np.uint8), "RGBA")
    out = b"".join(top.resize((mw, mh), Image.BOX).tobytes() if k else top.tobytes()
                   for k, (mw, mh) in enumerate(dims))
    print(f"  darkened: glow at ({cu}, {cv}), cut {cut}, {mips} mips")
    return hodpool.replace_texture_data(hod, out)


def convert(btg, name, theta=0.0, phi=0.0):
    """Write data/background/<name>/; returns the written paths relative to data/ ('/' separated)."""
    import sys
    sys.argv = [sys.argv[0], btg, name, "--theta", str(theta), "--phi", str(phi)]
    return main()


SKY = os.path.join(MOD, "build", "backgrounds")
SKY_TEX = 2048           # square (HODOR loops on non-square textures); the page is 2560 x 2048
SKY_RADIUS = 200.0       # stock ez01's sky sphere (its bounding box)
SKY_GRID = (64, 32)      # sphere segments around / top to bottom


def render_page(h, verts, stars, polys, size):
    """The BTG page as an RGB image (size x size): what HW1 draws, unprojected."""
    import numpy as np
    from PIL import Image
    sx, sy = size / h["pw"], size / h["ph"]
    img = np.zeros((size, size, 3), np.float32)
    ys, xs = np.mgrid[0:size, 0:size] + 0.5
    for _, a, b, c in polys:
        P = [verts[i] for i in (a, b, c)]
        pts = np.array([[p[1] * sx, p[2] * sy] for p in P])
        cols = np.array([[p[k] * p[6] * p[7] / 65025.0 for k in (3, 4, 5)] for p in P])
        x0, y0 = np.maximum(np.floor(pts.min(0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(pts.max(0)).astype(int), size - 1)
        if x1 < x0 or y1 < y0:
            continue
        X, Y = xs[y0:y1 + 1, x0:x1 + 1], ys[y0:y1 + 1, x0:x1 + 1]
        (ax, ay), (bx, by), (cx, cy) = pts
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-9:
            continue
        l1 = ((by - cy) * (X - cx) + (cx - bx) * (Y - cy)) / den
        l2 = ((cy - ay) * (X - cx) + (ax - cx) * (Y - cy)) / den
        l3 = 1 - l1 - l2
        m = (l1 >= -1e-4) & (l2 >= -1e-4) & (l3 >= -1e-4)
        col = l1[..., None] * cols[0] + l2[..., None] * cols[1] + l3[..., None] * cols[2]
        img[y0:y1 + 1, x0:x1 + 1][m] = col[m]
    for f, x, y, r, g, b, al, name in stars:      # additive, tinted by the star's colour
        tex = np.asarray(Image.open(os.path.join(BIG, "bitmaps", name.lower())).convert("RGB"), np.float32)
        w = max(1, int(round(tex.shape[1] * sx)))
        hgt = max(1, int(round(tex.shape[0] * sy)))
        tex = np.asarray(Image.fromarray(tex.astype(np.uint8)).resize((w, hgt), Image.BILINEAR), np.float32)
        tex *= np.array([r, g, b]) / 255.0 * (al / 255.0)
        cx, cy = int(round(x * sx - w / 2)), int(round(y * sy - hgt / 2))
        X0, Y0, X1, Y1 = max(cx, 0), max(cy, 0), min(cx + w, size), min(cy + hgt, size)
        if X1 > X0 and Y1 > Y0:
            img[Y0:Y1, X0:X1] += tex[Y0 - cy:Y1 - cy, X0 - cx:X1 - cx]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def write_sky(h, verts, stars, polys, name, theta, phi):
    """build/backgrounds/<name>/<name>_light.dae + its texture, for HODOR (tools/build_background.sh)."""
    out = os.path.join(SKY, name)
    os.makedirs(out, exist_ok=True)
    tex = f"{name}_remastered_DIFF.tga"
    render_page(h, verts, stars, polys, SKY_TEX).save(os.path.join(out, tex))
    gu, gv = SKY_GRID
    P, T, idx = [], [], []
    for j in range(gv + 1):
        for i in range(gu + 1):
            x, y = h["pw"] * i / gu, h["ph"] * j / gv
            P += [c * SKY_RADIUS / RADIUS for c in project(h, x, y, theta, phi)]
            T += [i / gu, 1.0 - j / gv]
    row = gu + 1
    for j in range(gv):
        for i in range(gu):
            a, b, c, d = j * row + i, j * row + i + 1, (j + 1) * row + i, (j + 1) * row + i + 1
            idx += [a, c, b, b, c, d]           # facing the inside (the camera)
    n = len(P) // 3
    N = []
    for k in range(n):                          # normals inward
        x, y, z = P[3 * k:3 * k + 3]
        r = math.sqrt(x * x + y * y + z * z) or 1.0
        N += [-x / r, -y / r, -z / r]
    fl = lambda v: " ".join("%.6g" % x for x in v)
    gid, mname, img = "MULT[PRE_Space]", f"MAT[{name}]_SHD[background]", f"IMG[{name}_remastered_DIFF]"
    dae = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">\n'
        '<asset><contributor><authoring_tool>Cataclysm-HWRM make_background.py</authoring_tool></contributor>'
        '<unit meter="1.0" name="meter"/><up_axis>Y_UP</up_axis></asset>\n'
        f'<library_images><image id="{img}-image" name="{img}_FMT[8888]"><init_from>{tex}</init_from></image>'
        '</library_images>\n'
        f'<library_materials><material id="{mname}" name="{mname}"><instance_effect url="#{mname}-fx"/></material>'
        '</library_materials>\n'
        f'<library_effects><effect id="{mname}-fx" name="{mname}"><profile_COMMON><technique sid="standard"><phong>'
        f'<diffuse><texture texture="{img}-image" texcoord="CHANNEL0"/></diffuse></phong></technique>'
        '</profile_COMMON></effect></library_effects>\n'
        f'<library_geometries><geometry id="{gid}" name="{gid}"><mesh>'
        f'<source id="{gid}-pos"><float_array id="{gid}-pos-a" count="{len(P)}">{fl(P)}</float_array>'
        f'<technique_common><accessor source="#{gid}-pos-a" count="{n}" stride="3"><param name="X" type="float"/>'
        '<param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>'
        f'<source id="{gid}-nrm"><float_array id="{gid}-nrm-a" count="{len(N)}">{fl(N)}</float_array>'
        f'<technique_common><accessor source="#{gid}-nrm-a" count="{n}" stride="3"><param name="X" type="float"/>'
        '<param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>'
        f'<source id="{gid}-uv0"><float_array id="{gid}-uv0-a" count="{len(T)}">{fl(T)}</float_array>'
        f'<technique_common><accessor source="#{gid}-uv0-a" count="{n}" stride="2"><param name="S" type="float"/>'
        '<param name="T" type="float"/></accessor></technique_common></source>'
        f'<vertices id="{gid}-v"><input semantic="POSITION" source="#{gid}-pos"/></vertices>'
        f'<triangles count="{len(idx) // 3}" material="{mname}">'
        f'<input semantic="VERTEX" offset="0" source="#{gid}-v"/><input semantic="NORMAL" offset="0" source="#{gid}-nrm"/>'
        f'<input semantic="TEXCOORD" offset="0" set="0" source="#{gid}-uv0"/>'
        f'<p>{" ".join(map(str, idx))}</p></triangles></mesh></geometry></library_geometries>\n'
        '<library_visual_scenes><visual_scene id="scene" name="scene">\n'
        '<node name="ROOT_LOD[0]" id="ROOT_LOD[0]" sid="ROOT_LOD[0]E"><translate sid="translate">0 0 0</translate>\n'
        '<node name="JNT[Root]" id="JNT[Root]" sid="JNT[Root]E"><translate sid="translate">0 0 0</translate>\n'
        f'<node name="{gid}" id="{gid}" sid="{gid}E"><translate sid="translate">0 0 0</translate>'
        f'<instance_geometry url="#{gid}"><bind_material><technique_common>'
        f'<instance_material symbol="{mname}" target="#{mname}"><bind_vertex_input semantic="CHANNEL0" '
        'input_semantic="TEXCOORD" input_set="0"/></instance_material>'
        '</technique_common></bind_material></instance_geometry></node>\n'
        '</node>\n</node>\n'
        '<node name="ROOT_INFO" id="ROOT_INFO" sid="ROOT_INFOE"><translate sid="translate">0 0 0</translate>'
        '<node name="Class[MultiMesh]_Version[512]" id="Class[MultiMesh]_Version[512]" sid="ClassE"/>'
        '<node name="UVSets[1]" id="UVSets[1]" sid="UVSetsE"/></node>\n'
        '</visual_scene></library_visual_scenes>\n<scene><instance_visual_scene url="#scene"/></scene>\n</COLLADA>\n')
    with open(os.path.join(out, name + "_light.dae"), "w", encoding="utf-8", newline="\n") as f:
        f.write(dae)
    print(f"{out}: {name}_light.dae ({n} vertices) + {tex} {SKY_TEX}x{SKY_TEX}")


def splice_lights(name):
    """Add stock ez01_light.hod's LITE chunk (the scene's lights) to our HODOR-built sky."""
    path = os.path.join(SKY, name, name + "_light.hod")
    d = bytearray(open(path, "rb").read())
    stock = open(os.path.join(STOCK, TEMPLATE, TEMPLATE + "_light.hod"), "rb").read()
    i = stock.index(b"LITE")
    lite = stock[i:i + 8 + struct.unpack(">I", stock[i + 4:i + 8])[0]]
    if b"LITE" in d:
        print(f"{path}: already has lights")
        return
    for tag, o, n in chunks(d, 0, len(d)):
        if tag == b"FORM" and d[o + 8:o + 12] == b"HVMD":
            d[o + 12:o + 12] = lite
            d[o + 4:o + 8] = struct.pack(">I", n + len(lite))
            open(path, "wb").write(d)
            print(f"{path}: + stock {TEMPLATE} lights ({len(lite)} bytes)")
            return
    raise SystemExit(f"{path}: no HVMD form")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("btg")
    ap.add_argument("name")
    ap.add_argument("--theta", type=float, default=0.0)
    ap.add_argument("--phi", type=float, default=0.0)
    ap.add_argument("--sky", action="store_true", help="write the sky model's DAE and texture to build/backgrounds")
    ap.add_argument("--splice", action="store_true", help="add the stock lights to the HODOR-built sky")
    a = ap.parse_args()
    if a.splice:
        return splice_lights(a.name)
    h, verts, stars, polys = read_btg(a.btg)
    if a.sky:
        return write_sky(h, verts, stars, polys, a.name, a.theta, a.phi)
    stock = open(os.path.join(STOCK, TEMPLATE, TEMPLATE + ".hod"), "rb").read()
    parts = {}
    for tag, o, n in chunks(stock, 0, len(stock)):
        kind = stock[o + 8:o + 12]
        parts.setdefault(kind, stock[o:o + 8 + n])
    bmsh_head = stock[stock.index(b"BMSH") + 4:stock.index(b"BMSH") + 24]

    # the triangles: one mesh
    vb = bytearray()
    for f, x, y, r, g, b, al, br in verts:
        k = al * br / (255.0 * 255.0)
        vb += struct.pack("<4f", *project(h, x, y, a.theta, a.phi), 1.0)
        vb += bytes([127] + [min(127, int(round(c * k / 2))) for c in (r, g, b)])
    ib = b"".join(struct.pack("<3H", v0, v1, v2) for _, v0, v1, v2 in polys)
    bmsh = (b"BMSH" + bmsh_head + struct.pack("<I", len(verts)) + bytes(vb) + b"\xff\xff"
            + struct.pack("<I", 3 * len(polys)) + ib)
    bgms = chunk(b"FORM", b"BGMS" + chunk(b"NRML", bmsh))

    # the stars, grouped by texture
    groups = {}
    for f, x, y, r, g, b, al, name in stars:
        w, _ = texture_size(name)
        groups.setdefault("cat_" + name, []).append(struct.pack("<8f", *project(h, x, y, a.theta, a.phi), w * STAR_SIZE,
                                                       r / 510.0, g / 510.0, b / 510.0, al / 255.0))
    bgsg = b"".join(chunk(b"FORM", b"BGSG" + struct.pack("<I", len(n)) + n.encode() + struct.pack("<I", len(s))
                          + b"".join(s)) for n, s in sorted(groups.items()))

    out = os.path.join(MOD, "data", "background", a.name)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, a.name + ".hod"), "wb") as f:
        f.write(parts[b"VERS"] + parts[b"BGLT"] + bgms + bgsg + parts[b"STRF"])
    sky = os.path.join(SKY, a.name, a.name + "_light.hod")
    if not os.path.exists(sky):
        raise SystemExit(f"{sky} missing: run tools/build_background.sh {a.name} (Git Bash) first")
    shutil.copyfile(sky, os.path.join(out, a.name + "_light.hod"))
    for ext in (".lua", "_extra.lua"):   # without the planet rig's Flare_Key (our sky has no joints)
        src = open(os.path.join(STOCK, TEMPLATE, TEMPLATE + ext), encoding="latin-1").read()
        src = "\n".join(l for l in src.split("\n") if "follow" not in l or l.strip().startswith("--"))
        open(os.path.join(out, a.name + ext), "w", encoding="latin-1", newline="\n").write(src)
    if os.path.exists(os.path.join(out, a.name + "_light.mad")):
        os.remove(os.path.join(out, a.name + "_light.mad"))
    stars_dir = os.path.join(MOD, "data", "background", "stars")
    os.makedirs(stars_dir, exist_ok=True)
    for name in groups:      # Cataclysm's star bitmaps, as cat_<name> (stock backgrounds use the HW1 names)
        shutil.copyfile(os.path.join(BIG, "bitmaps", name[4:].lower()), os.path.join(stars_dir, name))
    written = [f"background/{a.name}/{a.name}{ext}" for ext in (".hod", "_light.hod", ".lua", "_extra.lua")]
    written += [f"background/stars/{n}" for n in groups]
    print(f"{out}: {len(verts)} vertices, {len(polys)} triangles, {len(stars)} stars in {len(groups)} textures "
          f"(theta {a.theta:g}, phi {a.phi:g})")
    return written


if __name__ == "__main__":
    main()
