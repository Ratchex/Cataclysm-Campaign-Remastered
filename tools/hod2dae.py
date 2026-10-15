"""A Remastered model (stock HWRM / Cataclysm Remastered .hod, tools/hodread.py) as a Collada file for HODOR, so it
can be rebuilt with more on it: the pirate corvettes' disguises (Cataclysm's kasfShipsDisguise teams, Missions 02,
10, 12) are other ships' Remastered models on the corvette, one shown at a time by its .madstate, as the Mimic's
(tools/make_mimic.py; Gearbox's RODOH reads only Homeworld 2 Classic HODs).

  hod2dae.py <out_dir> <name> --body <hod> [--body-joint MimicBody] [--part <joint>@<hod>[@<colour scheme>] ...]

The body keeps its joints (weapons, engine nozzles, capture / repair points...: the .ship refers to them), its LOD 0
meshes on their joints, its materials (diffuse, glow; the team map's paint baked into the diffuse in the given scheme's
colours, as our other models: HWRM team masks through HODOR went wrong, NOTES.md "Ships and HODOR") and its engine
shapes (ETSH) with HODOR's flame divisions (BURN). Each --part is another model's LOD 0 meshes (its own joint
transforms applied) under a hidden joint at the origin. Writes <out_dir>/<name>.dae and its textures; then HODOR
(tools/build_hodship.sh, from Git Bash).

Texture paint (HWRM sob_ship.frag): team colour where the team map's red is low, stripe colour where its green is.
UVs: the .hod's (top-left origin, as Cataclysm's) written as 1 - v (geo2dae.py's).
"""
import argparse
import math
import os
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hodread  # noqa: E402
import make_colours  # noqa: E402
from geo2dae import fl, jnode, pow2  # noqa: E402


def rx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def ry(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def rot(e):
    """a .hod joint's Euler angles (radians): Z x Y x X, HODOR's order (geo2dae.py jnode)"""
    return rz(e[2]) @ ry(e[1]) @ rx(e[0])


def euler_zyx_deg(m):
    """degrees (x, y, z) with m = Rz Ry Rx"""
    sy = -m[2, 0]
    y = math.asin(max(-1.0, min(1.0, sy)))
    if abs(sy) < 0.99999:
        x = math.atan2(m[2, 1], m[2, 2])
        z = math.atan2(m[1, 0], m[0, 0])
    else:
        x = math.atan2(-m[1, 2], m[1, 1])
        z = 0.0
    return tuple(math.degrees(a) for a in (x, y, z))


def skip_mesh(model, mesh):
    """invisible helper meshes (stock: Innate_mesh, a matteScissor material)"""
    if mesh["name"].lower().startswith("innate"):
        return True
    parts = mesh["lods"].get(0, [])
    return all(model.materials[p["material"]]["shader"] in ("matteScissor", "default") for p in parts) if parts else True


class Writer:
    def __init__(self, out_dir, name):
        self.out, self.name = out_dir, name
        self.images, self.materials, self.effects, self.geoms = [], [], [], []
        self.done = {}
        self.ngeom = 0

    def square(self, img):
        im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGB")
        n = max(64, pow2(im.width), pow2(im.height))
        return im.resize((n, n), Image.LANCZOS) if im.size != (n, n) else im

    def material(self, model, tag, mi, scheme):
        """the material's id (written once per model and material)"""
        key = (tag, mi)
        if key in self.done:
            return self.done[key]
        mat = model.materials[mi]
        tx = mat["textures"]
        base = f"{self.name}_{tag}_{mi}"
        di = tx.get("diffuse", tx.get("diffuseOn"))
        if di is None or model.textures[di]["image"] is None:
            diff = np.full((64, 64, 4), 128.0)
        else:
            diff = model.textures[di]["image"].copy()
        ti = tx.get("team")
        if ti is not None and model.textures[ti]["image"] is not None and scheme is not None:
            team = model.textures[ti]["image"]
            if team.shape[:2] != diff.shape[:2]:
                team = np.asarray(Image.fromarray(team.astype(np.uint8)).resize(diff.shape[1::-1]), np.float32)
            s = make_colours.read()[scheme]
            for colour, ch in ((s["BaseColor"], 0), (s["StripeColor"], 1)):
                m = 1 - team[..., ch:ch + 1] / 255.0
                diff[..., :3] = diff[..., :3] * (1 - m) + np.array(colour) * 255 * m
        im = self.square(diff)
        im.save(os.path.join(self.out, base + "_DIFF.tga"))
        gi = tx.get("glow", tx.get("glowOn"))
        if gi is not None and model.textures[gi]["image"] is not None:
            g = self.square(model.textures[gi]["image"])
            g.resize(im.size).save(os.path.join(self.out, base + "_GLOW.tga"))
        img = f"IMG[{base}_DIFF]"
        mname = f"MAT[{base}]_SHD[ship]"
        self.images.append(f'<image id="{img}-image" name="{img}_FMT[DXT1]"><init_from>{base}_DIFF.tga</init_from></image>')
        self.materials.append(f'<material id="{mname}" name="{mname}"><instance_effect url="#{mname}-fx"/></material>')
        self.effects.append(f'<effect id="{mname}-fx" name="{mname}"><profile_COMMON><technique sid="standard"><phong>'
                            f'<diffuse><texture texture="{img}-image" texcoord="CHANNEL0"/></diffuse></phong>'
                            f'</technique></profile_COMMON></effect>')
        self.done[key] = mname
        return mname

    def mesh(self, model, tag, part, scheme, xform=None):
        """a mesh node for one LOD 0 part (xform: (rotation, translation) applied to its vertices)"""
        mname = self.material(model, tag, part["material"], scheme)
        P = np.array(part["pos"], float)
        N = np.array(part["nrm"], float) if part["nrm"] else np.zeros_like(P)
        if xform is not None:
            R, t = xform
            P = P @ R.T + t
            N = N @ R.T
        UV = np.array(part["uv"], float) if part["uv"] else np.zeros((len(P), 2))
        UV = np.column_stack([UV[:, 0], 1 - UV[:, 1]])
        idx = part["idx"]
        nt = len(idx) // 3
        gid = f"MULT[{self.name}_{self.ngeom}]"
        self.ngeom += 1
        nv = len(P)
        self.geoms.append(
            f'<geometry id="{gid}" name="{gid}"><mesh>'
            f'<source id="{gid}-pos"><float_array id="{gid}-pos-a" count="{nv * 3}">{fl(P.ravel())}</float_array>'
            f'<technique_common><accessor source="#{gid}-pos-a" count="{nv}" stride="3"><param name="X" type="float"/>'
            f'<param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>'
            f'<source id="{gid}-nrm"><float_array id="{gid}-nrm-a" count="{nv * 3}">{fl(N.ravel())}</float_array>'
            f'<technique_common><accessor source="#{gid}-nrm-a" count="{nv}" stride="3"><param name="X" type="float"/>'
            f'<param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>'
            f'<source id="{gid}-uv0"><float_array id="{gid}-uv0-a" count="{nv * 2}">{fl(UV.ravel())}</float_array>'
            f'<technique_common><accessor source="#{gid}-uv0-a" count="{nv}" stride="2"><param name="S" type="float"/>'
            f'<param name="T" type="float"/></accessor></technique_common></source>'
            f'<vertices id="{gid}-v"><input semantic="POSITION" source="#{gid}-pos"/></vertices>'
            f'<triangles count="{nt}" material="{mname}">'
            f'<input semantic="VERTEX" offset="0" source="#{gid}-v"/><input semantic="NORMAL" offset="0" source="#{gid}-nrm"/>'
            f'<input semantic="TEXCOORD" offset="0" set="0" source="#{gid}-uv0"/>'
            f'<p>{" ".join(map(str, idx[:nt * 3]))}</p></triangles></mesh></geometry>')
        return (f'<node name="{gid}" id="{gid}" sid="{gid}E"><translate sid="translate">0 0 0</translate>'
                f'<instance_geometry url="#{gid}"><bind_material><technique_common>'
                f'<instance_material symbol="{mname}" target="#{mname}"><bind_vertex_input semantic="CHANNEL0" '
                f'input_semantic="TEXCOORD" input_set="0"/></instance_material>'
                f'</technique_common></bind_material></instance_geometry></node>')


def world_frames(model):
    J = {j["name"]: j for j in model.joints}
    W = {}

    def world(n):
        if n in W:
            return W[n]
        j = J.get(n)
        if j is None:
            return np.eye(3), np.zeros(3)
        # (a HODOR-built model has HODOR's Root above ours, also named Root)
        pr, pt = world(j["parent"]) if j["parent"] and j["parent"] != n else (np.eye(3), np.zeros(3))
        W[n] = (pr @ rot(j["orient"]) @ rot(j["rot"]), pt + pr @ np.array(j["pos"]))
        return W[n]
    return world


def engine_shapes(path):
    """ETSH chunks: name, parent joint, u32 count, vertices (local to the parent)"""
    d = open(path, "rb").read()
    out = {}
    i = 0
    while True:
        i = d.find(b"ETSH", i)
        if i < 0:
            return out
        p = i + 8
        try:
            name, p = hodread.Reader.string(d, p)
            parent, p = hodread.Reader.string(d, p)
            n = struct.unpack_from("<I", d, p)[0]
            if 0 < n < 64 and name.isprintable() and parent.isprintable():
                out.setdefault(parent, []).append((name, [struct.unpack_from("<3f", d, p + 4 + 12 * k)
                                                          for k in range(n)]))
        except (struct.error, UnicodeDecodeError):
            pass
        i += 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("name")
    ap.add_argument("--body", required=True)
    ap.add_argument("--body-joint")
    ap.add_argument("--body-scheme", type=int)
    ap.add_argument("--part", action="append", default=[])
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    w = Writer(a.out_dir, a.name)
    body = hodread.read(a.body)
    kids = {}                          # joint -> its child joint names
    for j in body.joints:
        kids.setdefault(j["parent"], []).append(j["name"])
    meshes = {}                        # joint -> mesh nodes on it
    for m in body.meshes:
        if skip_mesh(body, m):
            continue
        for part in m["lods"].get(0, []):
            meshes.setdefault(m["parent"], []).append(w.mesh(body, "body", part, a.body_scheme))
    shapes = engine_shapes(a.body)
    J = {j["name"]: j for j in body.joints}
    nengine = 0

    hide = []                          # --body-joint: the joints holding body meshes (hidden by the .madstate)

    def body_meshes(name):
        if not meshes.get(name):
            return ""
        if not a.body_joint:
            return "".join(meshes[name])
        jn = a.body_joint if name == "Root" else f"{a.body_joint}_{name}"
        hide.append(jn)
        return jnode(f"JNT[{jn}]", (0, 0, 0), "".join(meshes[name]))

    def tree(name):
        nonlocal nengine
        j = J[name]
        inner = body_meshes(name)
        for sh_name, vs in shapes.get(name, []):
            # the engine's glow shape and HODOR's flame divisions (geo2dae.py's layout)
            nengine += 1
            gid = f"ETSH[{sh_name}]"
            P = [c for v in vs for c in v]
            idx = [k for t in range(1, len(vs) - 1) for k in (0, t, t + 1)]
            nv = len(vs)
            w.geoms.append(f'<geometry id="{gid}" name="{gid}"><mesh>'
                           f'<source id="{gid}-pos"><float_array id="{gid}-pos-a" count="{len(P)}">{fl(P)}</float_array>'
                           f'<technique_common><accessor source="#{gid}-pos-a" count="{nv}" stride="3"><param name="X" '
                           f'type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor>'
                           f'</technique_common></source>'
                           f'<source id="{gid}-nrm"><float_array id="{gid}-nrm-a" count="{len(P)}">{fl([0, 0, -1] * nv)}'
                           f'</float_array><technique_common><accessor source="#{gid}-nrm-a" count="{nv}" stride="3">'
                           f'<param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/>'
                           f'</accessor></technique_common></source>'
                           f'<vertices id="{gid}-v"><input semantic="POSITION" source="#{gid}-pos"/></vertices>'
                           f'<triangles count="{len(idx) // 3}"><input semantic="VERTEX" offset="0" source="#{gid}-v"/>'
                           f'<input semantic="NORMAL" offset="0" source="#{gid}-nrm"/><p>{" ".join(map(str, idx))}</p>'
                           f'</triangles></mesh></geometry>')
            inner += (f'<node name="{gid}" id="{gid}" sid="{gid}E"><translate sid="translate">0 0 0</translate>'
                      f'<instance_geometry url="#{gid}"></instance_geometry></node>')
            num = "".join(c for c in sh_name if c.isdigit()) or str(nengine)
            inner += jnode(f"BURN[EngineBurn{num}]", (0, 0, 0),
                           "".join(jnode(f"Flame[0]_Div[{k}]", (0, 0, -2.0 * k)) for k in range(5)))
        for c in kids.get(name, []):
            inner += tree(c)
        m = rot(j["orient"]) @ rot(j["rot"])
        return jnode(f"JNT[{name}]", tuple(j["pos"]), inner, euler_zyx_deg(m))

    # (--body-joint: each joint's body meshes on a child joint the .madstate can hide, so turrets still turn with
    # their weapon joints; bodyjoints.txt lists them)
    root_inner = body_meshes("Root") + "".join(tree(c) for c in kids.get("Root", []))
    with open(os.path.join(a.out_dir, "bodyjoints.txt"), "w", newline="\n") as f:
        f.write("\n".join(hide) + "\n")
    for spec in a.part:
        joint, path, *sc = spec.split("@")
        scheme = int(sc[0]) if sc else None
        model = hodread.read(path)
        world = world_frames(model)
        nodes = ""
        for m in model.meshes:
            if skip_mesh(model, m):
                continue
            xf = world(m["parent"])
            for part in m["lods"].get(0, []):
                nodes += w.mesh(model, joint, part, scheme, xf)
        root_inner += jnode(f"JNT[{joint}]", (0, 0, 0), nodes)
        print(f"  part {joint}: {os.path.basename(path)}, {len(model.meshes)} meshes")
    dae = os.path.join(a.out_dir, a.name + ".dae")
    with open(dae, "w", encoding="utf-8", newline="\n") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n'
                '<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">\n'
                '<asset><contributor><authoring_tool>Cataclysm-HWRM hod2dae.py</authoring_tool></contributor>'
                '<unit meter="1.0" name="meter"/><up_axis>Y_UP</up_axis></asset>\n'
                '<library_images>\n' + "\n".join(w.images) + '\n</library_images>\n'
                '<library_materials>\n' + "\n".join(w.materials) + '\n</library_materials>\n'
                '<library_effects>\n' + "\n".join(w.effects) + '\n</library_effects>\n'
                '<library_geometries>\n' + "\n".join(w.geoms) + '\n</library_geometries>\n'
                '<library_visual_scenes><visual_scene id="scene" name="scene">\n'
                '<node name="ROOT_LOD[0]" id="ROOT_LOD[0]" sid="ROOT_LOD[0]E"><translate sid="translate">0 0 0</translate>\n'
                '<node name="JNT[Root]" id="JNT[Root]" sid="JNT[Root]E"><translate sid="translate">0 0 0</translate>\n'
                + root_inner + '\n</node>\n</node>\n'
                '<node name="ROOT_INFO" id="ROOT_INFO" sid="ROOT_INFOE"><translate sid="translate">0 0 0</translate>'
                '<node name="Class[MultiMesh]_Version[512]" id="Class[MultiMesh]_Version[512]" sid="ClassE"/>'
                '<node name="UVSets[1]" id="UVSets[1]" sid="UVSetsE"/></node>\n'
                '</visual_scene></library_visual_scenes>\n'
                '<scene><instance_visual_scene url="#scene"/></scene>\n</COLLADA>\n')
    print(f"{dae}: {w.ngeom} meshes, {len(w.done)} materials, {len(body.joints)} joints, {nengine} engine shapes")


if __name__ == "__main__":
    main()
