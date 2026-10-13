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
Resources: Asteroid spheres (HW1 LevelLoad.c). Labelled RACE_KUSHAN teams belong to an allied computer player 2.
Not converted yet (listed in the output's "unconverted" comment): other resource layouts, Derelict, Mine, lighting.

Usage: mission2level.py <mission_dir> <out.level> [--shipmap shipmap.tsv] [--placeholder Kus_Scout]
         [--player-race Kushan] [--enemy-race Taiidan] [--background ez01] [--player-start-ship Kus_Mothership]
  --background         override the HW1/Cataclysm background name (Cataclysm's have no HWRM version yet)
  --player-start-ship  stand-in for the player's fleet, placed at StartPointPlayer (Cataclysm missions don't
                       place the player's fleet themselves)
  --player-fleet       several ships, e.g. "Kus_Mothership,Kus_Scout*3,Kus_ResourceCollector*2", spread in a
                       line beside StartPointPlayer (first one on the point)
"""
import argparse
import math
import csv
import os
import sys
import random
import re
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_colours  # noqa: E402

# Gearbox's HW1 factor (0.35, ship models too) spread out: the maps felt cramped and slow with ships, speeds, sensors
# and the camera at Cataclysm's proportions (user, Missions 1-2: bigger map, ships / camera / UI unchanged)
MAP_SPREAD = 1.5
SCALE = 0.35 * MAP_SPREAD
RADIUS_SCALE, OUTER = SCALE / 2, 1.2


# Camera on the player's hyperspace arrival (cataclysmkas.lua K_498230, Camera_UseCameraPoint), offsets from
# StartPointPlayer: SobGroup_HyperspaceTo brings the Kuun-Lan in unrotated (bow +Z, port +X, up +Y), whatever the
# point's rotation (two in-game tries: a camera placed for its -241 degree heading showed the port stern, then
# starboard abeam). Ahead of and below the port bow, looking up at it as in Cataclysm (user's screenshot of the
# original warp-in), a little below the ship's level (pitch and yaw confirmed by the user); the first
# confirmed-angle distance, ~2200 from the ship centre = cataclysmkas.lua KAS_ArrivalCameraDistance (the focus;
# 3700 was too far).
# (1x, 2x and 6x all started at the hangar: the old focus call zoomed in). Level addCamera(name, target, eye).
# 0.8: a little closer (user, Mission01; cataclysmkas.lua KAS_ArrivalCameraDistance with it).
# --arrival-yaw: the Kuun-Lan is turned that many degrees left once in (cataclysmkas.lua KAS_FaceArrival, the
# mission's KAS_ArrivalYaw), the camera with it.
ARRIVAL_TARGET = (0.0, 0.0, 600.0)
ARRIVAL_DIRECTION = (900.0, -200.0, 1380.0)     # eye - target, confirmed angle
ARRIVAL_DISTANCE_SCALE = 0.8
ARRIVAL_EYE = tuple(ARRIVAL_TARGET[k] + ARRIVAL_DISTANCE_SCALE * ARRIVAL_DIRECTION[k] for k in range(3))
ARRIVAL_YAW = 0.0


def arrival_camera(p, rot):
    c, s = math.cos(math.radians(ARRIVAL_YAW)), math.sin(math.radians(ARRIVAL_YAW))

    def world(v):       # turned left (bow +Z toward port +X) about up
        v = (v[0] * c + v[2] * s, v[1], -v[0] * s + v[2] * c)
        return tuple(p[k] + v[k] for k in range(3))
    return world(ARRIVAL_TARGET), world(ARRIVAL_EYE)


CAT_ASTEROIDS = r"C:\Modding\Cataclysm-decomp\extracted\big\resources\asteroids"
HW1_ASTEROIDS = r"C:\Modding\Cataclysm-decomp\reference\hwrm\HW1Campaign\resource\asteroid"


def ru_percent(t):
    """addAsteroid's RU percentage giving the asteroid Cataclysm's RUs (its .shp resourcevalue: Asteroid1 160,
    Asteroid2 400, Asteroid3 1000, Asteroid4 2000): HWRM's HW1 asteroids are worth resourceValue x percent / 100,
    with resourceValue 100 (Asteroid0: 11). Cataclysm's asteroids are about 10x HW1's; at 100% Mission 1's were
    worth a tenth of the original's (user: resource starved)."""
    cat = next(float(l.split()[1]) for l in open(os.path.join(CAT_ASTEROIDS, t.lower() + ".shp"), encoding="latin-1")
               if l.lower().startswith("resourcevalue"))
    res = os.path.join(HW1_ASTEROIDS, t.lower(), t.lower() + ".resource")
    base = float(re.search(r"resourceValue=([\d.]+)", open(res, encoding="latin-1").read()).group(1))
    return round(cat / base * 100)


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
    def __init__(self, shipmap, placeholder, races, folder="", ally_races=()):
        self.shipmap, self.placeholder, self.races = shipmap, placeholder, races
        self.folder, self.ally_races, self.asteroids = folder, {r.upper() for r in ally_races}, []
        self.squadrons, self.groups = [], OrderedDict()
        self.points, self.spheres, self.paths = [], [], OrderedDict()
        self.boxes = []
        self.settings, self.unconverted, self.unmapped = {}, Counter(), Counter()
        self.label_counts = Counter()
        self.schemes, self.team_players = {}, {}   # labelled team -> its colorScheme(n) / owning player

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
        if owner == 1 and race.upper() in self.ally_races:
            owner = 2                                  # allied computer player (Cataclysm's Kiith Naabal)
        if shiptype.lower() == "cryotray":
            owner = 0
        htype = self.ship_type(race, shiptype, owner)
        m = re.search(r"colorScheme\((\d+)\)", ",".join(fields[8:]))
        if m and label not in ("?", ""):
            self.schemes[label] = int(m.group(1))
            self.team_players[label] = owner
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
        elif kind == "Resources" and len(f) >= 9 and f[0].lower() == "asteroid" and f[4].lower() == "sphere":
            self.add_asteroids(f)
        elif kind == "Resources" and len(f) >= 11 and f[0].lower() == "asteroid" and f[4].lower() == "cylinder":
            self.add_asteroids(f, self.cylinder_point(f))
        else:
            self.unconverted[kind] += 1

    @staticmethod
    def cylinder_point(f):
        """HW1 LevelLoad.c AddResourceToCylinder: a point in a length x diameter x diameter box along x, turned
        roty degrees about Y, then rotz degrees about Z (HW1 matMakeRotAboutY/Z, matrix x vector)."""
        radius, length = float(f[7]), float(f[8])
        ry, rz = math.radians(float(f[9])), math.radians(float(f[10]))

        def point(rng):
            x, y, z = rng.uniform(-length / 2, length / 2), rng.uniform(-radius, radius), rng.uniform(-radius, radius)
            x, z = math.cos(ry) * x + math.sin(ry) * z, -math.sin(ry) * x + math.cos(ry) * z
            x, y = math.cos(rz) * x - math.sin(rz) * y, math.sin(rz) * x + math.cos(rz) * y
            return x, y, z
        return point

    def add_asteroids(self, f, offset=None):
        """HW1 LevelLoad.c scriptSetResourcesCB, Sphere layout: <number> asteroids at random within <radius> of the
        point, types weighted by the .dist file. Seeded per line, so every build places them identically.
        offset(rng) -> (x, y, z) replaces the sphere's for other layouts (cylinder_point)."""
        centre = tuple(map(float, f[1:4]))
        n, radius = int(f[6]), float(f[7])
        weights = []
        dist = next((x for x in os.listdir(self.folder) if x.lower() == f[5].lower()), None)
        if dist:
            for l in open(os.path.join(self.folder, dist), encoding="latin-1"):
                m = re.match(r"\s*(Asteroid\d)\s+(\d+)", l)
                if m and int(m.group(2)) > 0:
                    weights.append((m.group(1), int(m.group(2))))
        if not weights:
            weights = [("Asteroid2", 1)]
        rng = random.Random(",".join(f))
        for _ in range(n):
            if offset:
                d, radius = offset(rng), 1
            else:
                while True:
                    d = [rng.uniform(-1, 1) for _ in range(3)]
                    if sum(c * c for c in d) <= 1:
                        break
            p = tuple(centre[i] + d[i] * radius for i in range(3))
            pick = rng.uniform(0, sum(w for _, w in weights))
            for t, w in weights:
                pick -= w
                if pick <= 0:
                    break
            self.asteroids.append((t, pos(*p), (rng.uniform(0, 360), rng.uniform(0, 360), rng.uniform(0, 360))))

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
        for t, p, rot in self.asteroids:
            L.append(f'    addAsteroid("{t}", {vec(p)}, {ru_percent(t)}, {fmt(rot[0])}, {fmt(rot[1])}, {fmt(rot[2])}, 0)')
        for name, p, r in self.spheres:
            L.append(f'    addSphere("{name}", {vec(p)}, {fmt(r)})')
        for name, p, size in self.boxes:
            L.append(f'    addAxisAlignBox("{name}", {vec(p)}, {fmt(size)})')
        for name, p, rot in self.points:
            L.append(f'    addPoint("{name}", {vec(p)}, {vec(rot)})')
            if name == "StartPointPlayer":
                target, eye = arrival_camera(p, rot)
                L.append(f'    addCamera("KAS_ArrivalCamera", {vec(target)}, {vec(eye)})')
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
        players = (0, 1, 2) if any(sq[3] == 2 for sq in self.squadrons) else (0, 1)
        L += ["end", "", f"maxPlayers = {len(players)}", "", "player = {}"]
        for i in players:
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
        elif kind in ("Ships", "AIPoint", "AISphere", "AIPath", "AIBox", "Resources", "Derelict", "Mine", "MeteorStorm",
                      "Slipgate"):
            level.line(kind, args, sphere_player)
        elif kind.startswith("smUniverseSize"):
            level.settings[kind] = float(args)
        elif kind == "Background":
            level.settings["Background"] = args.split(",")[0].strip()


def convert(folder, out, shipmap, placeholder, races, background=None, start_ship=None, player_fleet=None,
            ally_races=("RACE_KUSHAN",)):
    level = Level(shipmap, placeholder, races, folder, ally_races)
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
    else:
        # no fleet placed: the engine brings the previous mission's (persist<n>.lua, else the mission folder's
        # StartingPlayerFleet.lua) to a point that must be called PlayerStartPoint (HWRM FUN_005d423b)
        start = next((p for p in level.points if p[0].lower() == "startpointplayer"), None)
        if start:
            level.points.append(("PlayerStartPoint", start[1], start[2]))
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
    ap.add_argument("--ally-race", default="Kushan")
    ap.add_argument("--background")
    ap.add_argument("--player-start-ship")
    ap.add_argument("--player-fleet")
    ap.add_argument("--arrival-yaw", type=float, default=0.0, help="degrees the Kuun-Lan turns left on arrival")
    a = ap.parse_args()
    ARRIVAL_YAW = a.arrival_yaw
    lv = convert(a.mission_dir, a.out, load_shipmap(a.shipmap), a.placeholder,
                 {0: a.player_race, 1: a.enemy_race, 2: a.ally_race},
                 a.background, a.player_start_ship, a.player_fleet)
    # the paths for the runtime too: kasfPatrolPath patrols point to point (cataclysmkas.lua K_4929d0)
    with open(os.path.splitext(a.out)[0] + "_paths.lua", "w", newline="\n") as f:
        f.write("-- Generated by tools/mission2level.py: level paths (HWRM coordinates) for kasfPatrolPath\n")
        f.write("KAS_Paths = {\n")
        for name, pts in lv.paths.items():
            closed = 1 if any(c.lower() == "closed" for _, _, c in pts) else 0
            coords = ", ".join(vec(p) for _, p, _ in sorted(pts))
            # Lua 4: list items, then ';', then named fields (mixed with ',' the whole file failed to load)
            f.write(f'\t["{name}"] = {{ {coords}; closed = {closed} }},\n')
        f.write("}\n")
        # each team's Cataclysm colour scheme (cataclysmkas.lua KAS_ApplyColourSchemes; tools/make_colours.py)
        s = lv.settings
        if all(k in s for k in ("smUniverseSizeX", "smUniverseSizeY", "smUniverseSizeZ")):
            # HW1 clamps KAS vectors to +-the universe size per axis (cataclysm.exe 0x4991d0); HWRM axes
            f.write(f"KAS_Universe = {{ {fmt(SCALE * s['smUniverseSizeX'])}, {fmt(SCALE * s['smUniverseSizeZ'])}, "
                    f"{fmt(SCALE * s['smUniverseSizeY'])} }}\n")
        f.write("KAS_TeamSchemes = {\n")
        for team, n in sorted(lv.schemes.items()):
            f.write(f'\t["{team}"] = {n},\n')
        f.write("}\n")
    make_colours.teamcolour(os.path.join(os.path.dirname(a.out), "teamcolour.lua"),
                            {0: a.player_race, 1: a.enemy_race, 2: a.ally_race}, lv.schemes, lv.team_players)
    print(f"{a.out}: {len(lv.squadrons)} squadrons, {len(lv.groups)} groups, {len(lv.points)} points, "
          f"{len(lv.spheres)} spheres, {len(lv.paths)} paths; unmapped types {sum(lv.unmapped.values())}; "
          f"unconverted {dict(lv.unconverted)}")
