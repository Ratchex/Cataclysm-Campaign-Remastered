"""Convert a HW1/Cataclysm MissionMan mission folder (.mission + .missphere + extension-less team files) into an
HWRM .level, following the conventions of Gearbox's HomeworldLevelConverter output (HWRM's homeworldclassic).

Transform (derived from HW1 Mission01 vs Gearbox's mission01.level, every paired object matches):
  position  HW1 (x, y, z), z up  ->  HWRM {-0.35*x, 0.35*z, 0.35*y}
  yaw       HW1 rot (deg about z) ->  HWRM {0, rot - 90, 0}  (Gearbox's Mission10 writes some of these as the
            equivalent Euler triple {180, 90 - rot, 180}; compare_level.py normalises that form)
  spheres   radius * 0.175 (Gearbox halves it relative to positions)
  bounds    inner = 0.35 * (smUniverseSizeX, smUniverseSizeZ, smUniverseSizeY), outer = 1.2 * inner
  .missphere positions are absolute (not relative to the sphere).
Ownership (HW1 Game/LevelLoad.c scriptSetShipsCB): default = the MissionSphere's player (-1 -> 0); any labelled
team -> computer player 1; CryoTray -> player 0. HW1's generic R1/R2 races take the owning player's race.

AIBox -> addAxisAlignBox(name, centre, 0.35 x largest dimension), as Gearbox did.
Not converted yet (listed in the output's "unconverted" comment): Resources, Derelict, Mine, lighting.

Usage: mission2level.py <mission_dir> <out.level> [--shipmap shipmap.tsv] [--placeholder Kus_Scout]
         [--player-race Kushan] [--enemy-race Taiidan] [--background ez01] [--player-start-ship Kus_Mothership]
  --background         override the HW1/Cataclysm background name (Cataclysm's have no HWRM version yet)
  --player-start-ship  stand-in for the player's fleet, placed at StartPointPlayer (Cataclysm missions don't
                       place the player's fleet themselves)
  --player-fleet       several ships, e.g. "Kus_Mothership,Kus_Scout*3,Kus_ResourceCollector*2", spread in a
                       line beside StartPointPlayer (first one on the point)
"""
import argparse
import csv
import os
import re
from collections import Counter, OrderedDict

SCALE, RADIUS_SCALE, OUTER = 0.35, 0.175, 1.2


def pos(x, y, z):
    return (-SCALE * x, SCALE * z, SCALE * y)


def fmt(v):
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def vec(t):
    return "{" + ", ".join(fmt(v) for v in t) + "}"


def ident(s):
    return re.sub(r"[^A-Za-z0-9_]", "_", s)


class Level:
    def __init__(self, shipmap, placeholder, races):
        self.shipmap, self.placeholder, self.races = shipmap, placeholder, races
        self.squadrons, self.groups = [], OrderedDict()
        self.points, self.spheres, self.paths = [], [], OrderedDict()
        self.boxes = []
        self.settings, self.unconverted, self.unmapped = {}, Counter(), Counter()
        self.label_counts = Counter()

    def ship_type(self, race, shiptype, owner):
        if race in ("R1", "R2"):  # HW1 generic races follow the owning player's race
            prefix = {"Kushan": "Kus_", "Taiidan": "Tai_"}.get(self.races[owner], "Kus_")
            return prefix + shiptype
        key = f"{race}:{shiptype}".lower()
        if key in self.shipmap:
            return self.shipmap[key]
        self.unmapped[f"{race}:{shiptype}"] += 1
        return self.placeholder or f"MISSING_{shiptype}"

    def add_ships(self, fields, sphere_player):
        label = fields[0]
        x, y, z, rot = (float(v) for v in fields[1:5])
        race, shiptype, count = fields[5], fields[6], int(fields[7])
        owner = 1 if label not in ("?", "") else max(sphere_player, 0)
        if shiptype.lower() == "cryotray":
            owner = 0
        htype = self.ship_type(race, shiptype, owner)
        base = label if label not in ("?", "") else f"{ident(shiptype)}_unlabelled"
        for _ in range(count):
            name = f"{base}{self.label_counts[base]}"
            self.label_counts[base] += 1
            self.squadrons.append((name, htype, pos(x, y, z), owner, (0, rot - 90, 0), f"{race} {shiptype}"))
            if label not in ("?", ""):
                self.groups.setdefault(label, []).append(name)
        if count == 0 and label not in ("?", ""):
            self.groups.setdefault(label, [])  # empty KAS team: the group must still exist

    def line(self, kind, args, sphere_player):
        f = [a.strip() for a in args.split(",")]
        if kind == "Ships":
            self.add_ships(f, sphere_player)
        elif kind == "AIPoint":
            self.points.append((f[0], pos(*map(float, f[1:4])), (0, float(f[4]) - 90 if len(f) > 4 else 0, 0)))
        elif kind == "AISphere":
            self.spheres.append((f[0], pos(*map(float, f[1:4])), float(f[4]) * RADIUS_SCALE))
        elif kind == "AIBox":
            # Gearbox: addAxisAlignBox(name, centre, size) with size = 0.35 x the box dimension (one value)
            self.boxes.append((f[0], pos(*map(float, f[1:4])), SCALE * max(float(v) for v in f[4:7])))
        elif kind == "AIPath":
            idx = int(f[5].split("/")[0]) - 1 if len(f) > 5 else len(self.paths.get(f[0], []))
            self.paths.setdefault(f[0], []).append((idx, pos(*map(float, f[1:4])), f[4] if len(f) > 4 else "Open"))
        elif kind == "MissionSphere":
            pass  # handled by the caller (it names a .missphere file)
        else:
            self.unconverted[kind] += 1

    def write(self, path, source):
        L = [f"-- Generated by tools/mission2level.py from {source}. Do not edit by hand; regenerate.", "",
             "function DetermChunk()"]
        for name, htype, p, owner, rot, src in self.squadrons:
            L.append(f'    addSquadron("{name}", "{htype}", {vec(p)}, {owner}, {vec(rot)}, 0, 0) -- {src}')
        L.append("")
        for g, members in self.groups.items():
            L.append(f'    createSOBGroup("{g}")')
            L += [f'    addToSOBGroup("{m}", "{g}")' for m in members]
        L.append("")
        for name, p, r in self.spheres:
            L.append(f'    addSphere("{name}", {vec(p)}, {fmt(r)})')
        for name, p, size in self.boxes:
            L.append(f'    addAxisAlignBox("{name}", {vec(p)}, {fmt(size)})')
        for name, p, rot in self.points:
            L.append(f'    addPoint("{name}", {vec(p)}, {vec(rot)})')
        for name, pts in self.paths.items():
            pts.sort()
            for i, p, _ in pts:
                L.append(f'    addPoint("{name}_{i}", {vec(p)}, {{0, 0, 0}})')
            L.append(f'    addPath("{name}", ' + ", ".join(f'"{name}_{i}"' for i, _, _ in pts) + ")")
        s = self.settings
        if all(k in s for k in ("smUniverseSizeX", "smUniverseSizeY", "smUniverseSizeZ")):
            inner = (SCALE * s["smUniverseSizeX"], SCALE * s["smUniverseSizeZ"], SCALE * s["smUniverseSizeY"])
            L.append(f"    setWorldBoundsInner({{0, 0, 0}}, {vec(inner)})")
            L.append(f"    setWorldBoundsOuter({{0, 0, 0}}, {vec(tuple(OUTER * v for v in inner))})")
        L += ["end", "", "function NonDetermChunk()", "    fogSetActive(0)", "    setGlareIntensity(0.0)",
              "    setLevelShadowColour(0, 0, 0, 1)"]
        if "Background" in s:
            L.append(f'    loadBackground("{s["Background"]}")')
        L.append("    setSensorsManagerCameraDistances(10500, 87500)")
        L += ["end", "", "maxPlayers = 2", "", "player = {}"]
        for i in (0, 1):
            L.append(f'player[{i}] = {{ id = {i}, name = "{self.races[i]}", resources = 0, '
                     f'raceName = "{self.races[i]}", startPos = 0 }}')
        if self.unconverted or self.unmapped:
            L += ["", "-- unconverted MissionMan lines: " + ", ".join(f"{k} x{v}" for k, v in sorted(self.unconverted.items())),
                  "-- unmapped ship types (placeholder used): " +
                  ", ".join(f"{k} x{v}" for k, v in sorted(self.unmapped.items()))]
        with open(path, "w", newline="\n") as fh:
            fh.write("\n".join(L) + "\n")


LINE = re.compile(r"^(\w+)\s+(.*)$")


def read_file(level, path, sphere_player, folder, seen):
    for raw in open(path, encoding="latin-1"):
        line = raw.split(";")[0].strip()
        m = LINE.match(line)
        if not m:
            continue
        kind, args = m.groups()
        if kind == "MissionSphere":
            f = [a.strip() for a in args.split(",")]
            target = next((x for x in os.listdir(folder) if x.lower() == f[-1].lower()), None)
            if target and target not in seen:
                seen.add(target)
                read_file(level, os.path.join(folder, target), int(f[0]), folder, seen)
        elif kind in ("Ships", "AIPoint", "AISphere", "AIPath", "AIBox", "Resources", "Derelict", "Mine"):
            level.line(kind, args, sphere_player)
        elif kind.startswith("smUniverseSize"):
            level.settings[kind] = float(args)
        elif kind == "Background":
            level.settings["Background"] = args.split(",")[0].strip()


def convert(folder, out, shipmap, placeholder, races, background=None, start_ship=None, player_fleet=None):
    level = Level(shipmap, placeholder, races)
    files = sorted(os.listdir(folder))
    mission = next(f for f in files if f.lower().endswith(".mission"))
    seen = {mission}
    read_file(level, os.path.join(folder, mission), 0, folder, seen)
    for f in files:  # extension-less team files (Cataclysm); HW1 keeps everything in .missphere files
        if "." not in f and f not in seen and os.path.isfile(os.path.join(folder, f)):
            seen.add(f)
            read_file(level, os.path.join(folder, f), 0, folder, seen)
    if background:
        level.settings["Background"] = background
    fleet = []
    if start_ship:
        fleet.append(start_ship)
    for item in (player_fleet or "").split(","):
        if item.strip():
            t, _, n = item.strip().partition("*")
            fleet += [t] * int(n or 1)
    if fleet:
        start = next((p for p in level.points if p[0].lower() == "startpointplayer"), None)
        where, rot = (start[1], start[2]) if start else ((0, 0, 0), (0, 0, 0))
        for i, t in enumerate(fleet):
            pos_i = (where[0] + 600 * i, where[1], where[2])
            level.squadrons.insert(i, (f"PlayerFleet{i}", t, pos_i, 0, rot, "stand-in player fleet"))
    level.write(out, os.path.basename(folder))
    return level


def load_shipmap(path):
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        return {f"{r['race']}:{r['ship']}".lower(): r["hwrm"] for r in csv.DictReader(f, delimiter="\t") if r["hwrm"]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mission_dir")
    ap.add_argument("out")
    ap.add_argument("--shipmap")
    ap.add_argument("--placeholder")
    ap.add_argument("--player-race", default="Kushan")
    ap.add_argument("--enemy-race", default="Taiidan")
    ap.add_argument("--background")
    ap.add_argument("--player-start-ship")
    ap.add_argument("--player-fleet")
    a = ap.parse_args()
    lv = convert(a.mission_dir, a.out, load_shipmap(a.shipmap), a.placeholder, {0: a.player_race, 1: a.enemy_race},
                 a.background, a.player_start_ship, a.player_fleet)
    print(f"{a.out}: {len(lv.squadrons)} squadrons, {len(lv.groups)} groups, {len(lv.points)} points, "
          f"{len(lv.spheres)} spheres, {len(lv.paths)} paths; unmapped types {sum(lv.unmapped.values())}; "
          f"unconverted {dict(lv.unconverted)}")
