"""Cataclysm's health and weapon damage on our ships, 1:1 (user, 2026-10-09: all mapped ships, Cataclysm's scale; the stock
per-class accuracy kept; armour upgrade levels later; NOTES.md "Damage model"). Run by install_base.py.

Health: the .shp maxhealth. Damage: Cataclysm's per-hit damage (table 0x72b228 [bullet type][armour level 0] x the
gun's DamageMult; beams hit 16 times a second for BulletLifeTime: per shot = per hit x 16 x lifetime) and its fire /
burst times give each ship a damage per second. The ship's HWRM weapons (ship weapon configs and its innate turret
subsystems' weapons; a weapon whose hit spawns another weapon, e.g. flak, has its damage there) keep their visuals,
cadence and accuracy; their damage is scaled so the ship's total matches Cataclysm's, and they hit every armour family
alike (Cataclysm's damage depends on armour level, not ship class). A weapon shared by ship types that need different
scales gets a per-ship copy (cat_<ship>_<weapon>). Our own weapons (cat_*) carry Cataclysm's values themselves.
Not yet: Beast ships (their infection weapons are their own mechanic), mines, armour levels, the Energy upgrade's
damage; ships Cataclysm gives no guns keep their template's weapons (the Somtaaw ramming frigate).

Originals are read from the source layers (Players Patch, HW1 campaign, stock), never from
data/, so re-running doesn't scale twice.
Usage: make_damage.py [--report]     (--report: print the per-ship factors, change nothing)
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cat_damage  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
DATA = os.path.join(MOD, "data")
REF = r"C:\Modding\Cataclysm-decomp\reference"
SOURCES = [os.path.join(REF, "players_patch"), os.path.join(REF, "hwrm", "HW1Campaign"),
           os.path.join(REF, "hwrm", "Homeworld2")]
BEAM_TICKS = 16          # beam damage per original-rate universe update (HW1 Collision.c collCheckBeamColl)
RACES = {"RACE_SECT": "sect", "RACE_BEAST": "beast", "RACE_KUSHAN": "kushan", "RACE_TAIDAN": "taidan"}
SKIP_PREFIX = ("bst_",)  # Beast ships: later (infection weapons)


def find(kind, name, ext, roots=None):
    """<root>/<kind>/<name>/<name><ext> in the first root that has it (case-insensitive)."""
    for root in roots or ([DATA] + SOURCES):
        folder = os.path.join(root, kind)
        if not os.path.isdir(folder):
            continue
        d = next((x for x in os.listdir(folder) if x.lower() == name.lower()), None)
        if d:
            f = next((x for x in os.listdir(os.path.join(folder, d)) if x.lower() == name.lower() + ext), None)
            if f:
                return os.path.join(folder, d, f)
    return None


def original(name):
    """A weapon's unmodified file: ours (cat_*, tracked in data/) or the first source layer's."""
    if name.lower().startswith("cat_"):
        return find("weapon", name, ".wepn", [DATA])
    return find("weapon", name, ".wepn", SOURCES)


def active(text):
    return "\n".join(l for l in text.split("\n") if not l.lstrip().startswith("--"))


# damage values: a number or a product / quotient of numbers (tai_cruiserion's 2400*2: read as no damage, it was
# left at HWRM's 4800 a hit, and Mission01's Taiidan heavy cruiser beat the Kushan at full strength, user)
_VAL = r"[\d.]+(?:\s*[*/]\s*[\d.]+)*"
HIT = re.compile(r'(AddWeaponResult\(NewWeaponType,\s*"Hit",\s*"DamageHealth",\s*"Target",\s*)(' + _VAL + r')(,\s*)('
                 + _VAL + r')')


def num(v):
    """a damage value (number, or a product / quotient of numbers) as a float"""
    return float(eval(v, {"__builtins__": {}}))
SPAWN = re.compile(r'AddWeaponResult\(NewWeaponType,\s*"Hit",\s*"SpawnWeaponFire",\s*"Target",[^)]*?"([^"]+)"\s*\)')


def weapon(name):
    """{fire type, seconds per shot (averaged over bursts), damage per shot, the weapon holding the damage}."""
    p = original(name)
    if not p:
        return None
    t = active(open(p, encoding="latin-1").read())
    cfg = re.search(r"StartWeaponConfig\(\s*NewWeaponType\s*,(.*?)\)\s*;?\s*$", t, re.M)
    if not cfg:
        return None
    a = [x.strip().strip('"') for x in cfg.group(1).split(",")]
    try:
        fire = float(eval(a[13], {}))
        on, off = float(eval(a[14], {})), float(eval(a[15], {}))
    except (SyntaxError, NameError, IndexError, ValueError):
        print(f"  damage: can't read {os.path.relpath(p, REF if p.startswith(REF) else DATA)}'s StartWeaponConfig")
        return None
    duty = on / (on + off) if on > 0 and off > 0 else 1.0
    holder, hit = name, HIT.search(t)
    if not hit:
        s = SPAWN.search(t)
        if not s:
            return None
        holder = s.group(1)
        sp = original(holder)
        hit = HIT.search(active(open(sp, encoding="latin-1").read())) if sp else None
        if not hit:
            return None
    dmg = (num(hit.group(2)) + num(hit.group(4))) / 2
    return {"type": a[1], "spf": fire / duty if fire > 0 else None, "dmg": dmg, "holder": holder}


SHIP_WEAPON = re.compile(r'^(\s*StartShipWeaponConfig\(NewShipType,\s*")([^"]+)(")', re.M)
HARDPOINT = re.compile(r'^\s*StartShipHardPointConfig\(NewShipType,\s*"[^"]*",\s*"[^"]*",\s*"Weapon",\s*"Innate",'
                       r'\s*"[^"]*",\s*"([^"]+)"', re.M)


def ship_weapons(ship):
    """(weapon, via) for each weapon a ship type fires: its own configs ("ship") and its innate turret subsystems'."""
    p = os.path.join(DATA, "ship", ship, ship + ".ship")
    if not os.path.exists(p):
        return []
    t = active(open(p, encoding="latin-1").read())
    out = [(m.group(2), "ship") for m in SHIP_WEAPON.finditer(t)]
    for sub in HARDPOINT.findall(t):
        sp = find("subsystem", sub, ".subs")
        if sp:
            st = active(open(sp, encoding="latin-1").read())
            out += [(w, sub) for w in re.findall(r'StartSubSystemWeaponConfig\(NewSubSystemType,\s*"([^"]+)"', st)]
    return out


def cat_guns(race, name):
    """Cataclysm: maxhealth, and guns (gun / missile / mine, damage per shot, seconds per shot over bursts)."""
    p = cat_damage.shp_file(race, name)
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
        size, lvl = v("GunSize"), v("StartUpgradeLevel")
        r = cat_damage.gs(size, lvl) if size and lvl else None
        if r is None:
            continue
        per = cat_damage.TABLE[r][0] * float(v("DamageMult", "1"))
        if "Ion" in cat_damage.GS[r]:
            per *= BEAM_TICKS * float(v("BulletLifeTime", "0"))
        fire, on, off = float(v("FireTime", "1")), float(v("BurstFireTime", "0")), float(v("BurstWaitTime", "0"))
        duty = on / (on + off) if on > 0 and off > 0 else 1.0
        kind = "mine" if cat_damage.GS[r] == "MineLauncher" else ("missile" if v("Type") == "GUN_MissileLauncher" else "gun")
        guns.append((kind, per, fire / duty))
    return (float(h.group(1)) if h else None), guns


def ships():
    seen = {}
    for line in list(open(os.path.join(HERE, "shipmap.tsv"), encoding="utf-8"))[1:]:
        c = line.rstrip("\n").split("\t")
        if (len(c) >= 3 and c[2] and c[0] in RACES and c[2] not in seen and not c[2].endswith("_dummy")
                and not c[2].startswith(SKIP_PREFIX)):
            seen[c[2]] = (RACES[c[0]], c[1])
    return seen


def plan():
    """ship -> (Cataclysm health, Cataclysm DPS, HWRM DPS, factor, [(weapon, via, info)]). Our own cat_* weapons
    stand for the Cataclysm guns of their kind (missile launchers) and are left out of both totals."""
    rows = {}
    for ship, (race, cat) in ships().items():
        health, guns = cat_guns(race, cat)
        if health is None:
            continue
        weps = [(w, via, weapon(w)) for w, via in ship_weapons(ship)]
        ours_missiles = any(w.lower().startswith("cat_") and i and i["type"] == "Missile" for w, _, i in weps)
        # mines are left as they are (not comparable as damage per second)
        cdps = sum(per / spf for kind, per, spf in guns
                   if kind != "mine" and not (kind == "missile" and ours_missiles))
        pool = [(w, via, i) for w, via, i in weps
                if i and i["spf"] and i["type"] != "Mine" and not w.lower().startswith("cat_")]
        hdps = sum(i["dmg"] / i["spf"] for _, _, i in pool)
        rows[ship] = (health, cdps, hdps, (cdps / hdps if hdps > 0 and cdps > 0 else None), pool)
    return rows


def set_health(ship, health):
    p = os.path.join(DATA, "ship", ship, ship + ".ship")
    t = open(p, encoding="latin-1").read()
    n = re.sub(r'(getShipNum\(NewShipType,\s*"maxhealth",\s*)[\d.]+', r"\g<1>%g" % health, t, count=1)
    if n == t:
        n = re.sub(r'(NewShipType(?:\.maxhealth|\["maxhealth"\])\s*=\s*)[\d.]+', r"\g<1>%g" % health, t, count=1)
    if n != t:
        open(p, "w", encoding="latin-1", newline="").write(n)
    return n != t


def scaled(text, factor):
    """Damage x factor; every armour family alike (setPenetration's default 1, no per-family list)."""
    text = HIT.sub(lambda m: f"{m.group(1)}{num(m.group(2)) * factor:.4g}{m.group(3)}{num(m.group(4)) * factor:.4g}",
                   text)
    return re.sub(r"setPenetration\(NewWeaponType,\s*([\d.]+)\s*,.*?\}\s*\)", r"setPenetration(NewWeaponType, \1, 1)",
                  text, flags=re.S)


def write_weapon(name, text):
    folder = os.path.join(DATA, "weapon", name.lower())
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name.lower() + ".wepn"), "w", encoding="latin-1", newline="") as f:
        f.write(text)
    return f"weapon/{name.lower()}/{name.lower()}.wepn"


def apply(rows):
    """Write health and the scaled weapons into data/; returns the paths written (for install_base's manifest)."""
    written, wants = [], {}
    for ship, (health, _, _, f, pool) in rows.items():
        set_health(ship, health)
        if f is None:
            continue
        for w, via, i in pool:
            wants.setdefault(i["holder"].lower(), {}).setdefault(round(f, 4), set()).add((ship, w, via))
    for holder, by_factor in sorted(wants.items()):
        factors = sorted(by_factor, key=lambda k: -len(by_factor[k]))
        src = original(holder)
        text = open(src, encoding="latin-1").read()
        written.append(write_weapon(holder, scaled(text, factors[0])))      # the most used scale in place
        for k in factors[1:]:                                                 # the others: per-ship copies
            for ship, w, via in by_factor[k]:
                if via != "ship" or w.lower() != holder:
                    print(f"  damage: {holder} x{k} for {ship} needs a copy via {via}/{w}: not done (x{factors[0]})")
                    continue
                copy = f"cat_{ship}_{holder}"
                written.append(write_weapon(copy, scaled(text, k)))
                p = os.path.join(DATA, "ship", ship, ship + ".ship")
                t = open(p, encoding="latin-1").read()
                t = SHIP_WEAPON.sub(lambda m: m.group(1) + (copy if m.group(2).lower() == holder else m.group(2))
                                    + m.group(3), t)
                open(p, "w", encoding="latin-1", newline="").write(t)
    print(f"  Cataclysm health on {len(rows)} ships, damage on {len(wants)} weapons")
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    rows = plan()
    if a.report:
        for ship, (health, cdps, hdps, f, pool) in sorted(rows.items()):
            print(f"{ship:26s} health {health:g}  cat {cdps:.0f} dps / hwrm {hdps:.0f}" + (f" -> x{f:.3g}" if f else ""))
        return
    apply(rows)


if __name__ == "__main__":
    main()
