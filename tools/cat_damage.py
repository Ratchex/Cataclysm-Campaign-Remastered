"""Survey: Cataclysm health and per-gun damage / DPS per mapped ship (shipmap.tsv) next to Cataclysm Remastered's.

Cataclysm's damage (NOTES.md "Damage model"): a gun's bullet type = FUN_0048b7c0(weapon level, GunSize) (the GS_*
enum, strings at 0x889da0); damage per hit = table 0x72b228 [bullet type][target armour level 0-2] x the gun's
DamageMult x the shooter's multiplier (rank). Missiles: the same with row MissleLauncher. Beams (ion) hit every
collision tick for BulletLifeTime, so their "dmg" here is per tick, not per shot.
Usage: cat_damage.py > survey.txt
"""
import os
import re
import sys

sys.path.insert(0, r"C:\Modding\Cataclysm-HWRM\tools")
from make_upgrades import Exe, EXE, BIG, HERE, MOD

GS = ["LargeEnergyCannon", "LargeIonCannon", "LargePlasmaBomb", "LargeProjectile", "MediumEnergyCannon",
      "MediumIonCannon", "MediumPlasmaBomb", "MediumProjectile", "MineLauncher", "MissleLauncher",
      "SmallEnergyCannon", "SmallIonCannon", "SmallPlasmaBomb", "SmallProjectile", "VeryLargeEnergyCannon",
      "VeryLargeIonCannon", "VeryLargePlasmaBomb", "Laser", "BigGun", "BeastWeapon"]
SIZE = {"GUNSIZE_SMALL": "Small", "GUNSIZE_MEDIUM": "Medium", "GUNSIZE_LARGE": "Large", "GUNSIZE_VERYLARGE": "VeryLarge"}
LEVEL = {"WEAPON_PROJECTILE": "Projectile", "WEAPON_ENERGY": "EnergyCannon", "WEAPON_ION": "IonCannon",
         "WEAPON_PLASMABOMB": "PlasmaBomb"}
exe = Exe(EXE)
TABLE = [exe.read(0x72B228 + 12 * r, "<3f") for r in range(20)]


def gs(size, level):
    size, level = size.upper(), level.upper()
    if level == "WEAPON_MISSILE":
        return GS.index("MissleLauncher")
    if level == "WEAPON_MINE":
        return GS.index("MineLauncher")
    if level == "WEAPON_LASER":
        return GS.index("Laser")
    if level == "WEAPON_BIGGUN":
        return GS.index("BigGun")
    if level == "WEAPON_BEASTINFECT":
        return GS.index("BeastWeapon")
    if level == "WEAPON_PROJECTILE" and size == "GUNSIZE_VERYLARGE":
        return GS.index("LargeProjectile")       # FUN_0048b7c0 has no case: it returns the size (3)
    name = SIZE[size] + LEVEL[level]
    return GS.index(name) if name in GS else None


def shp_file(race, name):
    p = os.path.join(BIG, "race_" + race, name + ".shp")
    return p if os.path.exists(p) else None


def cat_ship(race, name):
    p = shp_file(race, name)
    if not p:
        return None, []
    t = open(p, encoding="latin-1").read()
    h = re.search(r"^maxhealth\s+([\d.]+)", t, re.M)
    guns = []
    for m in re.finditer(r"^GUN\s+\d+(.*?)(?=^GUN\s+\d+|^\[|\Z)", t, re.M | re.S):
        b = m.group(1)

        def v(k, d=None):
            x = re.search(r"^" + k + r"\s+([\w.\-]+)", b, re.M)
            return x.group(1) if x else d
        size, s0, s1 = v("GunSize"), v("StartUpgradeLevel"), v("EndUpgradeLevel")
        if not size or not s0:
            continue
        mult = float(v("DamageMult", "1"))
        ft, bf, bw = float(v("FireTime", "1")), float(v("BurstFireTime", "0")), float(v("BurstWaitTime", "0"))
        rows = []
        for lvl in dict.fromkeys([s0, s1 or s0]):
            r = gs(size, lvl)
            dmg = TABLE[r][0] * mult if r is not None else None
            duty = bf / (bf + bw) if bf > 0 else 1.0
            dps = dmg / ft * duty if dmg is not None else None
            rows.append((GS[r] if r is not None else "?" + lvl, dmg, dps))
        guns.append((v("Type"), rows, ft, bf, bw))
    return (float(h.group(1)) if h else None), guns


def find(name, ext):
    for root, _, files in os.walk(os.path.join(MOD, "data")):
        for f in files:
            if f.lower() == name.lower() + ext:
                return os.path.join(root, f)
    return None


def cr_ship(name):
    p = find(name, ".ship")
    if not p:
        return None, []
    t = open(p, encoding="latin-1").read()
    h = re.search(r'maxhealth\s*=\s*getShipNum\(NewShipType,\s*"maxhealth",\s*([\d.]+)\)', t)
    out = []
    for w in dict.fromkeys(re.findall(r'^\s*StartShipWeaponConfig\(NewShipType,\s*"([^"]+)"', t, re.M)):
        wp = find(w, ".wepn")
        if not wp:
            continue
        s = open(wp, encoding="latin-1").read()
        cfg = re.search(r"StartWeaponConfig\(NewWeaponType,(.*?)\);", s, re.S)
        args = [a.strip() for a in cfg.group(1).split(",")] if cfg else []
        d = re.search(r'AddWeaponResult\(NewWeaponType,\s*"Hit",\s*"DamageHealth",\s*"Target",\s*([\d.]+),\s*([\d.]+)', s)
        dmg = (float(d.group(1)) + float(d.group(2))) / 2 if d else None
        ft = eval(args[13], {}) if len(args) > 15 else None
        out.append((w, dmg, ft, args[14:16] if len(args) > 15 else None))
    return (float(h.group(1)) if h else None), out


races = {"RACE_SECT": "sect", "RACE_BEAST": "beast", "RACE_KUSHAN": "kushan", "RACE_TAIDAN": "taidan"}
seen = set()
for line in list(open(os.path.join(HERE, "shipmap.tsv"), encoding="utf-8"))[1:]:
    c = line.rstrip("\n").split("\t")
    if len(c) < 3 or not c[2] or c[0] not in races or c[2] in seen:
        continue
    seen.add(c[2])
    h1, guns = cat_ship(races[c[0]], c[1])
    if h1 is None:
        continue
    h2, weps = cr_ship(c[2])
    print(f"{c[2]:28s} {c[1]:24s} health cat {h1:g}  cr {h2}")
    for typ, rows, ft, bf, bw in guns:
        print("   cat", typ, " | ".join(f"{n} {d:g} dmg {p:.1f} dps" if d is not None else n for n, d, p in rows),
              f"(fire {ft:g} burst {bf:g}/{bw:g})")
    for w, d, ft, b in weps:
        print("   cr ", w, d, "fire", ft, "burst", b)
