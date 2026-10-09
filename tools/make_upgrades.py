"""Cataclysm's ship upgrades, read from cataclysm.exe, for data/scripts/cataclysm/shiprules.lua.

Cataclysm (Cataclysm-decomp, NOTES.md "Upgrades"): a ship's upgrades are ability bits (ship + 0x3f4) and an armour
level (ship + 0x3f0). The player's research sets player bits (FUN_00514140: table 0x72b9e8 {tech, bits, bits2}) and
an armour level (TECH_ARMOUR2 -> 1, TECH_ARMOUR3 -> 2); a ship gets (its type's mask, table 0x72b7a0) & (the
player's bits), its armour capped by its type (table 0x72b31c) (FUN_00514490). The Upgrade command (FUN_0044de80)
upgrades the selected ships over a time (FUN_00514540): 10 s per new ability bit (20 for INFECT: FUN_00513f40), plus
10/20/30 s for the armour level reached (0x72b1f8), x the ship's upgradeTimeModifier (.shp). Strike craft
(UpgradeByDocking TRUE) dock to upgrade ("Docking Ships to Upgrade"), the rest upgrade where they are. New ships
come with the player's upgrades.

Weapons (FUN_00514140 / FUN_005142e0 / FUN_00514490): research sets the player's weapon levels (table 0x72bb18
{tech, level}: TECH_ENERGY -> 1 ENERGY, TECH_ION -> 2, ...), but the upgrade only ever moves a gun from level 0
(PROJECTILE) to 1 (ENERGY): a gun whose .shp EndUpgradeLevel is WEAPON_ENERGY, once TECH_ENERGY is researched, for
10 s of upgrade time (0x72b204[0]). Here that is the pseudo-ability WEAPON_ENERGY on every type with such a gun.

Writes data/scripts/cataclysm/upgrades_gen.lua.
Usage: make_upgrades.py
"""
import os
import re
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
DECOMP = r"C:\Modding\Cataclysm-decomp"
EXE = os.path.join(DECOMP, "bin", "cataclysm.exe")
BIG = os.path.join(DECOMP, "extracted", "big")

# ABILITY_* (the enum's order: its strings at 0x88a5f4-0x88a7f4, last first)
ABILITIES = ["ADRIVE_FIGHTER", "ADRIVE_FRIGATE", "ADRIVE_DESTROYER", "LINK", "UNLINK", "MIMIC", "LEECH",
             "EXPLOSIVE_CHARGE", "AFTERBURNER", "EMP", "REPULSE", "SWARM", "FORCE_FIELD1", "FORCE_FIELD2",
             "FORCE_FIELD3", "DEFLECT", "INFECT", "CLOAK", "REPAIR", "SALVAGE", "CRYSTAL_HARVEST", "REPAIRBOTS",
             "VACCINE", "ADVANCED_SENSORS", "GRAVWELL", "RAMMINGLASER", "ORDINANCE"]
# TechnologyType: TECH_ARMOUR2 = 14 / TECH_ARMOUR3 = 15 (FUN_00514140) pins it to the TECH_* strings' order
TECHS = ["TECH_CLOAKING", "TECH_TARGETING_SYSTEMS", "TECH_PLASMA_WEAPONS", "TECH_MEDIUM_GUNS", "TECH_DEFENSE_FIELD",
         "TECH_HEAVY_GUNS", "TECH_REPAIR", "TECH_SALVAGE", "TECH_DRIVE_FIGHTER", "TECH_ADRIVE_FIGHTER",
         "TECH_DRIVE_FRIGATE", "TECH_ADRIVE_FRIGATE", "TECH_DRIVE_DESTROYER", "TECH_ADRIVE_DESTROYER",
         "TECH_ARMOUR2", "TECH_ARMOUR3", "TECH_SUPPORT_SYSTEMS", "TECH_MICRO_SHIP", "TECH_ENERGY", "TECH_ION",
         "TECH_MISSILE", "TECH_REPULSE", "TECH_EMP", "TECH_EXPLOSIVE_CHARGE", "TECH_LINK", "TECH_MIMIC",
         "TECH_AFTERBURNER", "TECH_BIG_GUN", "TECH_ADVANCED_SENSORS", "TECH_FORCE_FIELD1", "TECH_FORCE_FIELD2",
         "TECH_FORCE_FIELD3", "TECH_INFECT", "TECH_REPAIRBOTS", "TECH_CRYSTAL_HARVEST",
         "TECH_RESEARCH_CLEESAN_ATTACK", "TECH_BEAST_VACCINE", "TECH_PHASED_TELEMETRY", "TECH_INERTIALESS_DRIVE",
         "TECH_BIOWARHEAD", "TECH_DRIVE_CORVETTE"]
ABILITY_TIME, INFECT_TIME = 10.0, 20.0          # FUN_00513f40 (0x72a4f0, 0x72a4d0 for bit 16)
WEAPON_ENERGY = "WEAPON_ENERGY"                  # pseudo-ability: a gun projectile -> energy (0x72b204[0] = 10 s)


class Exe:
    def __init__(self, path):
        self.d = open(path, "rb").read()
        pe = struct.unpack_from("<I", self.d, 0x3C)[0]
        n, opt = struct.unpack_from("<H", self.d, pe + 6)[0], struct.unpack_from("<H", self.d, pe + 20)[0]
        self.base = struct.unpack_from("<I", self.d, pe + 24 + 28)[0]
        self.secs = [struct.unpack_from("<8sIIII", self.d, pe + 24 + opt + 40 * i) for i in range(n)]

    def read(self, va, fmt):
        r = va - self.base
        for _, _, vaddr, rsize, raw in self.secs:
            if vaddr <= r < vaddr + rsize:
                return struct.unpack_from(fmt, self.d, raw + r - vaddr)
        raise ValueError(hex(va))


def ship_types():
    """ShipType order: english.script's first ship name strings (sRecon 0, sAcolyte 1, ... confirmed by the masks)."""
    names = []
    for line in open(os.path.join(BIG, "english.script"), encoding="latin-1"):
        m = re.match(r"str([a-z]+[A-Z]\w*)\s", line)
        if m:
            names.append(m.group(1).lower())
        if m and m.group(1) == "dMessagePod":
            break
    return names


def shp_value(race, ship, key, default):
    path = os.path.join(BIG, "race_" + race, ship + ".shp")
    if os.path.exists(path):
        for line in open(path, encoding="latin-1"):
            f = line.split()
            if len(f) >= 2 and f[0].lower() == key.lower():
                return f[1]
    return default


def energy_guns(race, ship):
    """Guns that upgrade from WEAPON_PROJECTILE to WEAPON_ENERGY (.shp StartUpgradeLevel / EndUpgradeLevel)."""
    path = os.path.join(BIG, "race_" + race, ship + ".shp")
    if not os.path.exists(path):
        return 0
    text = open(path, encoding="latin-1").read()
    return sum(1 for a, b in re.findall(r"StartUpgradeLevel\s+(\w+)\s+EndUpgradeLevel\s+(\w+)", text)
               if a == "WEAPON_PROJECTILE" and b == "WEAPON_ENERGY")


def type_rows(exe, types):
    """(HWRM type, Cataclysm type, abilities, armour cap, docks to upgrade, upgradeTimeModifier) per mapped ship."""
    races = {"RACE_SECT": "sect", "RACE_BEAST": "beast", "RACE_KUSHAN": "kushan", "RACE_TAIDAN": "taidan"}
    rows, seen = [], set()
    for line in list(open(os.path.join(HERE, "shipmap.tsv"), encoding="utf-8"))[1:]:
        cols = line.rstrip("\n").split("\t")
        if len(cols) < 3 or not cols[2] or cols[0] not in races or cols[1] not in types or cols[2] in seen:
            continue
        seen.add(cols[2])
        t = types.index(cols[1])
        mask = exe.read(0x72B7A0 + 4 * t, "<I")[0]
        armour_max = exe.read(0x72B31C + 8 * t, "<i")[0]
        dock = shp_value(races[cols[0]], cols[1], "UpgradeByDocking", "FALSE").upper() == "TRUE"
        tmod = float(shp_value(races[cols[0]], cols[1], "upgradeTimeModifier", "1"))
        abil = [n for i, n in enumerate(ABILITIES) if mask >> i & 1]
        # Somtaaw and Beast only: their races research TECH_ENERGY; the Kushan / Taiidan ships had no upgrades and
        # ship code asking for a research their race lacks is untested (a Lua error there is fatal)
        if cols[0] in ("RACE_SECT", "RACE_BEAST") and energy_guns(races[cols[0]], cols[1]):
            abil.append(WEAPON_ENERGY)
        rows.append((cols[2], cols[1], abil, armour_max, dock, tmod))
    return rows


def upgradable():
    """HWRM types that have upgrades (not the Kuun-Lan module dummies)."""
    return [r[0] for r in type_rows(Exe(EXE), ship_types()) if (r[2] or r[3] > 0) and not r[0].endswith("_dummy")]


def main():
    exe = Exe(EXE)
    types = ship_types()
    tech_bits = {}                                   # ability -> tech
    a = 0x72B9E8
    while a < 0x72BB18 - 12:                         # the last row (tech 0) is a debug "everything" grant
        tech, b1, b2 = exe.read(a, "<3I")
        for i, name in enumerate(ABILITIES):
            if (b1 | b2) >> i & 1:
                tech_bits.setdefault(name, TECHS[tech])
        a += 12
    tech_bits[WEAPON_ENERGY] = "TECH_ENERGY"         # table 0x72bb18
    armour_time = exe.read(0x72B1F8, "<3f")
    rows = type_rows(exe, types)
    out = ["-- Generated by tools/make_upgrades.py from cataclysm.exe's upgrade tables: see that tool.",
           "CatUpgradeTech = {"] + [f'    {n} = "{t}",' for n, t in sorted(tech_bits.items())] + ["}",
           f"CatArmourTech = {{ \"TECH_ARMOUR2\", \"TECH_ARMOUR3\" }}",
           f"CatArmourTime = {{ {armour_time[0]:g}, {armour_time[1]:g}, {armour_time[2]:g} }}   -- reaching level 1-3",
           f"CAT_UPGRADE_TIME, CAT_UPGRADE_TIME_INFECT = {ABILITY_TIME:g}, {INFECT_TIME:g}",
           "-- HWRM type: Cataclysm type, abilities it can be upgraded with, armour cap (0-2), docks to upgrade,",
           "-- upgradeTimeModifier",
           "CatUpgradeType = {"]
    for hwrm, cat, abil, amax, dock, tmod in rows:
        out.append(f'    ["{hwrm}"] = {{ cat = "{cat}", abilities = {{ {", ".join(chr(34) + x + chr(34) for x in abil)} }}, '
                   f'armour = {amax}, dock = {1 if dock else 0}, time = {tmod:g} }},')
    out.append("}")
    path = os.path.join(MOD, "data", "scripts", "cataclysm", "upgrades_gen.lua")
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    print(f"upgrades: {len(tech_bits)} abilities, {len(rows)} ship types -> {os.path.relpath(path, MOD)}")


if __name__ == "__main__":
    main()
