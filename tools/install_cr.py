"""Install the Players Patch (below, PP) and Cataclysm Remastered (workshop 2195601016, "Beast Update" v2.1) as the
mod's base data layers.

Copies Cataclysm-decomp/reference/cr_beast (extracted with Cataclysm-decomp/tools/hw2big.py) into data/, except their
campaign and junk, then applies PATCHES (small edits so their ships work for the Cataclysm campaign). The copied
files are listed in data/cr_files.txt and git-ignored through data/.gitignore (their assets are not ours to commit;
permission is needed before any public release).

Usage: install_cr.py
"""
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_modules  # noqa: E402
import make_damage  # noqa: E402
import make_shipcode  # noqa: E402
import make_colours  # noqa: E402
import make_background  # noqa: E402
import ship_variants  # noqa: E402

MOD =os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = r"C:\Modding\Cataclysm-decomp\reference\cr_beast"
DATA = os.path.join(MOD, "data")

# The Homeworld Remastered 2.3 Players Patch (workshop 1190476337, extracted with hw2big.py) under theirs: the
# community's fixes (formations / strike groups, cross-race docking, SCAR library fixes) and its HW1 ships, which
# our Kushan and Taiidan use (tools/make_shipcode.py copies its .ship over stock's). Cataclysm Remastered's files
# win where both have one. Not its campaign / multiplayer levels. Its HW1 rebalance comes along for now; the target
# is Cataclysm's balance (user), when the Kushan / Taiidan stats are converted.
PP = r"C:\Modding\Cataclysm-decomp\reference\players_patch"
PP_SKIP_PREFIX = ("leveldata/", "keeper.txt")

# Only what their ships need (ship/subsystem/weapon/missile/art, ship sounds, race and ship-behaviour scripts):
# not their menus/UI, their copies of the SCAR libraries (stock HWRM's are used; their scar_util.lua differed in
# 244 lines), skirmish rules/AI/maps/badges/fleets, locale/speech logic, music or speech.
SKIP_PREFIX = ("leveldata/", "config_old.txt", "keeper.txt", "ui/", "scripts/scar/", "scripts/rules/",
               "scripts/startingfleets/", "ai/", "badges/", "locale/", "soundscripts/", "sound/music/",
               "sound/speech/")
# ...except these, which their ships do use (TOIcon "Flagship" etc.: a missing icon is a fatal exit)
# (and the faction badges of Cataclysm's colour schemes: tools/make_colours.py)
KEEP_PREFIX = ("ui/tacticalicons/",) + tuple("badges/" + b for b in make_colours.BADGES)
CATSPEECH_LINE = 'dofilepath("data:soundscripts/cataclysm/catspeech.lua")   -- Cataclysm-HWRM: Somtaaw voices'
SKIP_SUFFIX = (".swp", ".bak")

RESEARCH_HP = ('StartShipHardPointConfig(NewShipType,"Research Module","Hardpoint_GravGenerator","System","Innate",'
               '"Damageable","HW1_ResearchModule","","","","","","","","");')


TO_MOTHERSHIP = "\n".join(f"NewShipType.{k}={v}" for k, v in (
    ("TODistanceFade0", 14000), ("TODistanceDisappear0", 12000), ("TODistanceFade1", 5500),
    ("TODistanceDisappear1", 5000), ("TODistanceFade2", 12000), ("TODistanceDisappear2", 35000)))


def patch_ms_sp(text):
    """Cataclysm researches without building a research module: innate HW1 research module on the unused
    Hardpoint_GravGenerator of their single-player Kuun-Lan (after LoadModel, as hardpoints must be; their
    multiplayer model, see COPIES, has no Hardpoint_Generic5-7)."""
    # its tactical overlay icon: theirs has no TODistance* (engine defaults: it vanished zooming out before the
    # Workers' did, user); stock HW1 kus_mothership's
    if "TODistanceFade0" not in text:
        assert 'NewShipType.TOIcon="Flagship"' in text
        text = text.replace('NewShipType.TOIcon="Flagship"', 'NewShipType.TOIcon="Flagship"\n' + TO_MOTHERSHIP, 1)
    if "HW1_ResearchModule" in text:
        return text
    return text.replace("LoadModel(NewShipType, 1);",
                        "LoadModel(NewShipType, 1);\n-- Cataclysm-HWRM: innate research module\n" + RESEARCH_HP +
                        "\n-- Cataclysm-HWRM: Kuun-Lan module slots (tools/make_modules.py)\n" +
                        "\n".join(make_modules.hardpoint_lines()), 1)


def patch_sp_props(text):
    """Single-player build/research lists: ours (tools/make_race.py: Cataclysm's tech tree on their ships)."""
    if "path_build" in text:
        return text
    return text.replace("String_Properties = {", "String_Properties = {\n"
                        "\tpath_build = [[data:scripts/races/somtaaw/scripts/sp_build.lua]],\n"
                        "\tpath_research = [[data:scripts/races/somtaaw/scripts/sp_research.lua]],", 1)


MISSING_FAMILIES = ["Shipyard_Smt", "Utility_Smt", "Research_Smt", "SubSystemLarge_Smt", "Probe_Smt"]


def family_sections(text):
    """{section: [family names]} of a familylist.lua (buildFamily = { { name = "..." }, ... })."""
    return {m.group(1): re.findall(r'name\s*=\s*"([^"]+)"', m.group(2))
            for m in re.finditer(r"^(\w+)\s*=\s*\n\{(.*?)^\}", text, re.M | re.S)}


def patch_families(text):
    """Their familylist, plus: families their Kuun-Lan builds that the Beast Update's lacks, and the Players Patch's
    families theirs lacks (its ships use them; a missing family is a log error)."""
    text = text.replace("\r\n", "\n")
    add = "".join('\t{\n\t\tname = "%s",\n\t},\n' % f for f in MISSING_FAMILIES if '"%s"' % f not in text)
    text = text.replace("buildFamily =\n{\n", "buildFamily =\n{\n" + add, 1)
    ours = family_sections(text)
    pp = family_sections(open(os.path.join(PP, "scripts", "familylist.lua"), encoding="latin-1").read()
                         .replace("\r\n", "\n"))
    for section, names in pp.items():
        missing = [n for n in names if n not in ours.get(section, [])]
        if missing:
            text = text.replace(section + " =\n{\n", section + " =\n{\n" +
                                "".join('\t{\n\t\tname = "%s",\n\t},\n' % f for f in missing), 1)
    return text


def patch_race(text):
    """Single-player rules only pass races tagged race_gbx_hwrmc ("Unknown Race [Somtaaw]" otherwise)."""
    return re.sub(r'^(Tags = "(?:(?!race_gbx_hwrmc)[^"])*)"', r'\1,race_gbx_hwrmc"', text, count=1, flags=re.M)


# The repair order (Worker, Processor): HWRM repairs only the attack families listed after EndRepairRates, each
# approached in its attack style (stock repair corvette: corvettes and up). Theirs listed only the dock families
# SuperCap / Flagship (user: the order targeted nothing but the Kuun-Lan); Cataclysm's beams repair anything. Rate:
# tweak.script twRepairRate 30.
# Latching (4th argument 0, the HW2 collectors') flew the repairer onto the target's repair point and dragged it
# along (user: "jank", stuck to fighters flying off, the Processor's point inside its hull). HWRM heals only by
# latching (RepairByLatchingCommand; heal weapons never fire on it), so with 4th argument 1 the order only picks the
# target, approaches and faces it and holds off near Cataclysm's beam range (data/scripts/attack/*_catrepair.lua;
# the Processor turns its side, where its beams are), and shiprules.lua CatRepair_Tick heals.
REPAIR_FAMILIES = ("Fighter", "Fighter_hw1", "Corvette", "Corvette_hw1", "Utility", "Resource", "ResourceLarge",
                   "NonCombat", "Frigate", "SmallCapitalShip", "BigCapitalShip", "Mothership")
REPAIR_BEAMS = {   # ship: (RepairCommand range, attack style)
    "worker": (790, "Frontal_CatRepair"),
    "processor": (1400, "Broadside_CatRepair"),
}


def repair_order(text, kind):
    """Their RepairCommand (or a new one after RetireAbility) replaced by our non-latching one."""
    rng, style = REPAIR_BEAMS[kind]
    order = (f'addAbility(NewShipType,"RepairCommand",1,{rng},30,1,"{style}",{{EndRepairRates=0}},'
             + ",".join('{%s="%s"}' % (f, style) for f in REPAIR_FAMILIES) + ");   -- Cataclysm-HWRM")
    new, n = re.subn(r'^\s*addAbility\(NewShipType,\s*"RepairCommand".*?\);[^\n]*$', order, text,
                     count=1, flags=re.M | re.S)
    if not n:
        assert 'addAbility(NewShipType, "RetireAbility", 1, 1);' in text
        new = text.replace('addAbility(NewShipType, "RetireAbility", 1, 1);',
                           'addAbility(NewShipType, "RetireAbility", 1, 1);\n' + order, 1)
    return new


def patch_processor(text):
    """An ordered repair (user: Cataclysm's Processor only repaired what drifted into its beams; here also on order:
    shiprules.lua CatProcessor_* runs the automatic beams): the Worker's RepairCommand at Cataclysm's repair rate
    (tweak.script twRepairRate 30 / s). Both only once it has the Repair upgrade (shiprules.lua CatGated)."""
    return repair_order(text, "processor")


def patch_worker(text):
    """Cataclysm's Worker repairs; their RepairCommand was disabled. (How far off it harvests is set by the
    model's LatchOrientation joint, not by the Harvest ability: tools/build_ship.sh --latch.) No NLIPS (its icon
    and selection box scaled up with distance: user)."""
    text = re.sub(r"^(\s*NewShipType\.nlips(?:Range|Far|FarRange)?\s*=\s*)[\d.]+", r"\g<1>0", text, flags=re.M)
    return repair_order(text, "worker")


def patch_hw1_armour(text):
    """Their weapons rate HW2 armour only (Unarmoured, LightArmour, ...) and do no damage to the other families
    (setPenetration's default, 3rd argument, is 0 on theirs): stock HW1 ships (the Taiidan and Kushan) are
    Unarmoured_hw1 / LightArmour_hw1, so Acolytes did no damage to Taiidan fighters. Stock HW1 weapons rate the
    _hw1 families the same as their HW2 counterparts; so do these."""
    for fam in ("Unarmoured", "LightArmour"):
        if fam + "_hw1" in text:
            continue
        # {Unarmoured=1}, or {Unarmoured = 1,} -> followed by {Unarmoured_hw1=1}
        text = re.sub(r"(\{\s*%s\s*=\s*([\d.]+)\s*,?\s*\})" % fam, r"\1, {%s_hw1=\2}" % fam, text, count=1)
    return text


# the Mimic's attack (install below): its own CanAttack numbers (the collector's 1, 5, 2 took attack orders away: a
# click gave a move order, user) with stock kus_resourcecollector's kamikaze styles, on every family
MIMIC_ATTACK = ('addAbility(NewShipType, "CanAttack", 1, 5, 1, 0, 0.35, 1, "Fighter, Fighter_hw1, Corvette, '
                'Corvette_hw1, Frigate, Utility, SmallCapitalShip, BigCapitalShip, Mothership", "kamikaze", '
                '{Fighter="kamikaze"}, {Fighter_hw1="kamikaze"}, {SubSystem="kamikaze"}, {SmallCapitalShip="kamikaze"}, '
                '{BigCapitalShip="kamikaze"}, {Mothership="kamikaze"}, {ResourceLarge="kamikaze"});  -- Cataclysm-HWRM')


# Cataclysm's two launchers (our model's Weapon_GUN2/GUN3: tools/build_ship.sh)
ACOLYTE_LAUNCHERS = ["Weapon_GUN2", "Weapon_GUN3"]


def patch_acolyte(text):
    """Cataclysm's Acolyte has missile launchers only from the Missile upgrade (sacolyte.shp GUN2/GUN3,
    StartUpgradeLevel WEAPON_MISSILE): their innate special-attack missile goes; two cat_acolytemissile launchers
    ("Special Attack" weapons) fire in normal attacks only while the ship's UseSpecialWeaponsInNormalAttack ability is
    on: granted to Acolytes by research CAT_ACOLYTE_MISSILES (tools/make_race.py, given at mission start), switched on
    per Acolyte by shiprules.lua once it has the upgrade. (Tried and dropped: weapon subsystems. Added by script they
    need a ship that can build, so every Acolyte had a build menu tab; innate ones held at 0 health still fired.)"""
    if "cat_acolytemissile" in text:
        return text
    text = re.sub(r'^(StartShipWeaponConfig\(NewShipType,\s*"Ksh_Sec_AcolyteMissile".*)$',
                  r"-- Cataclysm-HWRM (missiles come with the Missile upgrade): \1", text, flags=re.M)
    guns = "\n".join(f'StartShipWeaponConfig(NewShipType,"cat_acolytemissile","{j}","{j}");' for j in ACOLYTE_LAUNCHERS)
    return text.rstrip("\n") + "\n-- Cataclysm-HWRM: missile launchers (Missile upgrade)\n" + guns + "\n"


PATCHES = {
    "ship/smt_ms_sp/smt_ms_sp.ship": patch_ms_sp,
    "ship/smt_worker/smt_worker.ship": patch_worker,
    "ship/smt_processor/smt_processor.ship": patch_processor,
    "ship/smt_acolyte/smt_acolyte.ship": patch_acolyte,
    "scripts/races/somtaaw/singleplayer/props/gbx.lua": patch_sp_props,
    "scripts/familylist.lua": patch_families,
    "scripts/races/somtaaw.lua": patch_race,
}

# Their single-player Kuun-Lan model is an old 20 MB export that fails the HWRM mesh loader ("Unknown mesh
# group type", BMSH version 0x578 with extra UV sets); their multiplayer Kuun-Lan is the same ship re-exported
# (same .mad/.events and joints, minus the unused Hardpoint_Generic5-7).
COPIES = {
    "ship/smt_ms_sp/smt_ms_sp.hod": "ship/smt_ms/smt_ms.hod",
}

# Our models (tools/build_ship.sh: Cataclysm's geometry at Gearbox's scale, matching the converted NIS and
# levels) under their ship setup. Their joint names map to ours; hardpoint/weapon configs on joints our model
# lacks are commented out.
BUILD = os.path.join(MOD, "build", "ships")
OUR_MODELS = {
    "smt_ms_sp": ("som_mothership", {
        "Hardpoint_GravGenerator": "Hardpoint_Research",
        "Weapon_TurretTopCenter": "Weapon_GUN0", "Weapon_TurretRearLeftTop": "Weapon_GUN1",
        "Weapon_TurretRearRightTop": "Weapon_GUN2", "Weapon_TurretRearLeftBot": "Weapon_GUN3",
        "Weapon_TurretRearRightBot": "Weapon_GUN4", "Weapon_TurretFrontCenter": "Weapon_GUN5"}),
    "smt_worker": ("som_worker", {}),
    "smt_scout": ("som_recon", {"Weapon_Autogun": "Weapon_GUN0"}),
    "smt_acolyte": ("som_acolyte", {"Weapon_FrontGun": "Weapon_GUN0", "Weapon_FrontBotGun": "Weapon_GUN1",
                                    "Weapon_Missile": "Weapon_GUN2"}),
    # their four guns are Cataclysm's four, in order
    "smt_acv": ("som_acv", {"Weapon_Gun": "Weapon_GUN0", "Weapon_Gun1": "Weapon_GUN1", "Weapon_Gun2": "Weapon_GUN2",
                            "Weapon_Gun3": "Weapon_GUN3"}),
    # its body and its disguises as joints, one shown at a time (tools/overrides/ship/smt_mimic/smt_mimic.madstate)
    "smt_mimic": ("som_mimic", {}),
    # their four hull guns on Cataclysm's four gun points (any pairing: their positions differ from ours)
    "smt_processor": ("som_processor", {"Weapon_TopLeft": "Weapon_GUN0", "Weapon_TopRight": "Weapon_GUN2",
                                        "Weapon_BotLeft": "Weapon_GUN3", "Weapon_BotRight": "Weapon_GUN1"}),
    # (their ion beam's hardpoint isn't on ours: Cataclysm's has no gun)
    "smt_rammingfrigate": ("som_rammingfrigate", {}),
}


# Effects for ships whose own .events have none (their Acolyte's is empty: no muzzle flash): a stock HWRM ship's,
# its joint/animation names mapped to ours
HW1SHIPS = r"C:\Modding\Cataclysm-decomp\reference\hwrm\HW1Ships\ship"
OUR_EVENTS = {
    "smt_acolyte": (os.path.join(HW1SHIPS, "kus_interceptor", "kus_interceptor.events"),
                    {"Weapon_Gun0": "Weapon_GUN0", "Weapon_Gun1": "Weapon_GUN1"}),
    # theirs had no death events: no explosion (user)
    "smt_mimic": (os.path.join(HW1SHIPS, "kus_interceptor", "kus_interceptor.events"), {}),
}


# Files of theirs replaced by ours (tracked here; data/ copies are git-ignored as theirs): tools/overrides/<data path>
OVERRIDES = os.path.join(MOD, "tools", "overrides")


def use_our_events(ship, src, names):
    text = open(src, encoding="latin-1").read()
    for theirs, mine in names.items():
        text = text.replace(theirs, mine)
    with open(os.path.join(DATA, "ship", ship, ship + ".events"), "w", encoding="latin-1", newline="") as f:
        f.write(text)


# Speeds: Cataclysm's .shp maxvelocity converted the way Gearbox converted the matching HW1 class for HWRM (their
# HWRM mainEngineMaxSpeed / HW1 maxvelocity: kus_scout 490/1000, kus_interceptor 487/875, kus_resourcecollector
# 110/325). Their setups ran 1.3-1.9x Cataclysm's pace for some ships (user: distances felt shorter than the
# original). Thrusters keep their ratio to the main engine. Not the Kuun-Lan: it is more agile than HW1's
# Mothership (user), so it keeps their speed.
SPEED_CLASS = {"scout": 490 / 1000, "interceptor": 487 / 875, "collector": 110 / 325,
               "frigate": 206 / 325}   # (tai_assaultfrigate 206 / tStandardFrigate 325)
# The Worker on Gearbox's collector ratio (144) was a bit slow (user): the scout ratio (208); the original's Worker
# runs at 0.52x an Acolyte, the interceptor ratio would be 237.
SPEEDS = {"smt_scout": ("srecon", "scout"), "smt_acolyte": ("sacolyte", "interceptor"),
          "smt_worker": ("sworker", "scout"), "smt_acv": ("sacv", "interceptor"), "smt_mimic": ("smimic", "interceptor"),
          "smt_rammingfrigate": ("srammingfrigate", "frigate"), "smt_processor": ("sprocessor", "scout")}   # (the Workers' ratio, user)


# Build cost and time: Cataclysm's own (the .shp buildCost / buildTime, 1:1: RUs are Cataclysm's too, asteroids by
# mission2level.py ru_percent), not theirs (their Acolyte cost 130 to Cataclysm's 75). Every ship of theirs that
# tools/shipmap.tsv maps a Cataclysm Somtaaw / Beast ship to.
def cataclysm_costs():
    costs = {}
    for line in list(open(os.path.join(MOD, "tools", "shipmap.tsv"), encoding="utf-8"))[1:]:
        cols = line.rstrip("\n").split("\t")
        if len(cols) < 3 or cols[0] not in ("RACE_SECT", "RACE_BEAST") or not cols[2] or cols[2] in costs:
            continue
        shp = os.path.join(r"C:\Modding\Cataclysm-decomp\extracted\big", "race_" + cols[0][5:].lower(),
                           cols[1] + ".shp")
        if not os.path.exists(shp):
            continue
        vals = {}
        for l in open(shp, encoding="latin-1"):
            f = l.split()
            if len(f) >= 2 and f[0].lower() in ("buildcost", "buildtime"):
                vals[f[0].lower()] = f[1]
        if len(vals) == 2:
            costs[cols[2]] = (cols[1], vals["buildcost"], vals["buildtime"])
    return costs


def set_costs():
    n = 0
    for ship, (cat, cost, time) in sorted(cataclysm_costs().items()):
        path = os.path.join(DATA, "ship", ship, ship + ".ship")
        if not os.path.exists(path):
            continue
        text = open(path, encoding="latin-1").read()
        new = re.sub(r'(NewShipType(?:\.buildCost|\["buildCost"\])\s*=\s*)[\d.]+', r"\g<1>" + cost, text, count=1)
        new = re.sub(r'(NewShipType(?:\.buildTime|\["buildTime"\])\s*=\s*)[\d.]+', r"\g<1>" + time, new, count=1)
        if new != text:
            open(path, "w", encoding="latin-1", newline="").write(new)
            n += 1
    print(f"  Cataclysm build cost/time on {n} ships")


# Engine trails from another of our ships: Cataclysm's sacv.shp gives each of the ACV's two engines the Acolyte's
# trail (trailWidth 12, trailHeight 6, as sacolyte.shp); CR's ACV trails were tuned for their model (width 7.5,
# length 22: far too bright on ours, user)
TRAIL_FROM = {"smt_acv": "smt_acolyte"}


def set_trails():
    for ship, src in TRAIL_FROM.items():
        path = os.path.join(DATA, "ship", ship, ship + ".ship")
        spath = os.path.join(DATA, "ship", src, src + ".ship")
        if not (os.path.exists(path) and os.path.exists(spath)):
            continue
        m = re.search(r"^setEngineTrail\(NewShipType,\s*\d+\s*,(.*?)\)\s*;?\s*$", open(spath, encoding="latin-1").read(), re.M)
        if not m:
            raise SystemExit(f"{spath}: no setEngineTrail to copy")
        model = open(os.path.join(DATA, "ship", ship, ship + ".hod"), "rb").read()
        nozzles = len(set(re.findall(rb"EngineNozzle\d+", model)))
        text = open(path, encoding="latin-1").read()
        text = re.sub(r"^(setEngineTrail\()", r"-- Cataclysm-HWRM (set_trails): \1", text, flags=re.M)
        lines = "".join(f"setEngineTrail(NewShipType, {k},{m.group(1)});\n" for k in range(nozzles))
        text = text.rstrip("\n") + f"\n-- Cataclysm-HWRM: {src}'s trail on each of our {nozzles} nozzles (as Cataclysm)\n" + lines
        open(path, "w", encoding="latin-1", newline="").write(text)
        print(f"  {ship}: {src}'s engine trail on {nozzles} nozzles")


# CR's energy cannons, "Special Attack" weapons on their Acolyte / ACV: they never fire in normal combat (make_damage
# counted them, so the guns that do fire got about half of Cataclysm's damage: ACV ~25 of 58 DPS, user: "doesn't do
# enough damage"), and once UseSpecialWeaponsInNormalAttack is on (the Acolyte's missile upgrade) they fire as an
# extra gun Cataclysm only gives with its Energy upgrade (shelved). Cataclysm's ships fire their projectile guns only.
DROP_WEAPONS = {"smt_acolyte": ("Ksh_KineticAutoGun1",), "smt_acv": ("Smt_ACVAutoGun1",)}


def drop_weapons():
    for ship, weapons in DROP_WEAPONS.items():
        path = os.path.join(DATA, "ship", ship, ship + ".ship")
        if not os.path.exists(path):
            continue
        text = open(path, encoding="latin-1").read()
        n = 0
        for w in weapons:
            text, k = re.subn(r'^(StartShipWeaponConfig\(NewShipType,\s*"%s")' % re.escape(w),
                              r"-- Cataclysm-HWRM (drop_weapons): \1", text, flags=re.M | re.I)
            n += k
        open(path, "w", encoding="latin-1", newline="").write(text)
        print(f"  {ship}: {n} special-attack weapon configs dropped")


def set_speed(ship, cat, cls):
    shp = os.path.join(r"C:\Modding\Cataclysm-decomp\extracted\big\race_sect", cat + ".shp")
    v = next(float(l.split()[1]) for l in open(shp, encoding="latin-1") if l.lower().startswith("maxvelocity"))
    main = round(v * SPEED_CLASS[cls])
    path = os.path.join(DATA, "ship", ship, ship + ".ship")
    text = open(path, encoding="latin-1").read()
    # NewShipType.key = v or NewShipType["key"] = v (their Mimic), v e.g. 350*1.4
    field = lambda key: r'(NewShipType(?:\.%s|\["%s"\])\s*=\s*)([\d.*]+)' % (key, key)
    num = lambda key: eval(re.search(field(key), text).group(2))
    thr = round(main * num("thrusterMaxSpeed") / num("mainEngineMaxSpeed"))
    text = re.sub(field("mainEngineMaxSpeed"), r"\g<1>%d" % main, text, count=1)
    text = re.sub(field("thrusterMaxSpeed"), r"\g<1>%d" % thr, text, count=1)
    open(path, "w", encoding="latin-1", newline="").write(text)
    print(f"  {ship}: speed {main} (thrusters {thr}) from Cataclysm {cat} {v:g}")


def use_our_model(ship, ours, joints):
    folder = os.path.join(DATA, "ship", ship)
    shutil.copyfile(os.path.join(BUILD, ours, ours + ".hod"), os.path.join(folder, ship + ".hod"))
    mad = os.path.join(BUILD, ours, ours + ".mad")   # converted Cataclysm animation (tools/mad2hwrm.py)
    if os.path.exists(mad):
        shutil.copyfile(mad, os.path.join(folder, ship + ".mad"))
    else:
        # no animation of ours: their .mad animates their model's joints, and with ours its motion data was freed
        # twice at shutdown (heap corruption 0xc0000374 on every exit; ProcDump stack in MotionNode/MotionFollower)
        for ext in (".mad", ".madstate"):
            if os.path.exists(os.path.join(folder, ship + ext)):
                os.remove(os.path.join(folder, ship + ext))
                print(f"  {ship}: their {ext} removed (made for their model)")
    model = open(os.path.join(folder, ship + ".hod"), "rb").read()
    path = os.path.join(folder, ship + ".ship")
    text = open(path, encoding="latin-1").read()
    for theirs, mine in joints.items():
        text = re.sub(r'"%s"' % theirs, '"%s"' % mine, text)
    # our models have one level of detail: their LOD switches (made for theirs) left ours invisible past the first
    # (user: the Mimic vanished zooming out)
    text = re.sub(r'^\s*NewShipType(\.|\[")(upLOD|downLOD)\b.*\n', "", text, flags=re.M)
    text = re.sub(r'^(\s*NewShipType(?:\.|\[")minLOD(?:"\])?\s*=\s*)[\d.]+', r"\g<1>1", text, flags=re.M)

    def drop(m):
        joint = m.group(2)
        return m.group(0) if joint.encode() in model else "-- Cataclysm-HWRM (no joint in our model): " + m.group(0)
    text = re.sub(r'^(Start(?:Ship)?(?:HardPoint|Weapon)Config\(NewShipType,\s*"[^"]*",\s*"([^"]*)").*$', drop,
                  text, flags=re.M)

    # the weapon's 4th argument names its firing animation in the .events ("Fire", "Missile" on theirs, from their
    # .mad); stock names it after the weapon joint, as our OUR_EVENTS do
    def fire_joint(m):
        return m.group(0) if not m.group(3) or m.group(3).encode() in model else m.group(1) + m.group(2) + '"'
    text = re.sub(r'^(StartShipWeaponConfig\(NewShipType,\s*"[^"]*",\s*"([^"]*)",\s*")([^"]*)"', fire_joint,
                  text, flags=re.M)

    # engine trails on nozzles we lack go to our last nozzle (their Acolyte trails its 3rd, centre nozzle; ours
    # has one), once per nozzle
    nozzles = len(set(re.findall(rb"EngineNozzle\d+", model)))
    seen = set()

    def trail(m):
        idx = min(int(m.group(2)), nozzles - 1)
        if nozzles == 0 or idx in seen:
            return "-- Cataclysm-HWRM (no such nozzle): " + m.group(0)
        seen.add(idx)
        return m.group(1) + str(idx) + m.group(3)
    text = re.sub(r'^(setEngineTrail\(NewShipType,\s*)(\d+)(.*)$', trail, text, flags=re.M)

    # LOD switching: our models have LOD 0 only (their Worker vanished at distance, switching to a LOD 1)
    text = re.sub(r'^(NewShipType\.(?:up|down)LOD\s*=)', r'-- Cataclysm-HWRM (LOD 0 only): \1', text, flags=re.M)
    open(path, "w", encoding="latin-1", newline="").write(text)


SPEECH_SHIP_ARG = {"StatusSubsystem": 1, "CommandConstructionComplete": 1}   # handlers whose ship is not the 1st arg
SPEECH_EARLY_OUT = {   # Somtaaw ships: Cataclysm's per-ship-type Fleet Command line instead of the stock logic
    "CommandConstructionComplete": "if CatSpeech_IsSomtaaw({s}) ~= nil and CatSpeech_Built({s}) ~= nil then return end",
    "StatusShipDestroyed": "if CatSpeech_IsSomtaaw({s}) ~= nil and CatSpeech_Destroyed({s}) ~= nil then return end",
    "StatusBuildAvailable": "if CatSpeech_IsSomtaaw({s}) ~= nil and CatSpeech_Available({s}) ~= nil then return end",
    "CommandAttackGiven": "if CatSpeech_SilentAttack({s}) ~= nil then return end",   # the Mimic: its scream instead
}


def patch_speech_logic():
    """Cataclysm's Somtaaw voices (data/soundscripts/cataclysm/catspeech.lua, voices from tools/make_unitspeech.py):
    the speech logic environment refuses redefined global functions ("Cannot overwrite function") and lacks getn, so
    Players Patch's speechlogic files are edited from their pristine copy: catspeech.lua loaded first, every handler
    stores its ship in CatSpeech_Ship, playSpeechActor(Linked) calls go through CatSpeech_Play(Linked), and
    construction-complete / ship-destroyed first try Cataclysm's per-ship announcement."""
    for fn in ("commands.lua", "status.lua", "chatter.lua"):
        src = os.path.join(PP, "soundscripts", "speechlogic", fn)
        dst = os.path.join(DATA, "soundscripts", "speechlogic", fn)
        if not os.path.exists(src):
            continue
        text = open(src, encoding="latin-1").read()
        text = re.sub(r"\bplaySpeechActorLinked\s*\(", "CatSpeech_PlayLinked(", text)
        text = re.sub(r"\bplaySpeechActor\s*\(", "CatSpeech_Play(", text)

        def handler(m):
            name, params = m.group(1), [p.strip() for p in m.group(2).split(",") if p.strip()]
            if not re.match(r"(Command|Status|Chatter|BattleChat)", name) or name.endswith("_Init"):
                return m.group(0)
            k = SPEECH_SHIP_ARG.get(name, 0)
            ship = params[k] if k < len(params) and params[k] != "temp" and name != "StatusBattleMomentum" else '""'
            out = m.group(0) + f"\n\tCatSpeech_Ship = {ship} or \"\"   -- Cataclysm-HWRM (catspeech.lua)"
            if name in SPEECH_EARLY_OUT:
                out += "\n\t" + SPEECH_EARLY_OUT[name].format(s=ship)
            return out
        text = re.sub(r"^function\s+(\w+)\s*\(([^)]*)\)", handler, text, flags=re.M)
        # the race's own announcer, as theirs for the Vaygr / Taiidan (Cataclysm Remastered did the same for its
        # Kuun-Lan / Beast): Somtaaw -> "cat_fleet" (player:racelist.lua written at mission start, cataclysmkas.lua)
        taiidan = 'elseif (Race_ID[currentRace] == "Taiidan" or Race_ID[currentRace] == "2x_Taiidan") then\n\t\treturn NameEmperor'
        if fn == "commands.lua":
            if taiidan not in text:
                raise SystemExit(f"{src}: raceHelper changed; patch_speech_logic needs updating")
            text = text.replace(taiidan, taiidan + '\n\telseif (Race_ID[currentRace] == "Somtaaw") then\n\t\treturn "cat_fleet"', 1)
        open(dst, "w", encoding="latin-1", newline="").write(CATSPEECH_LINE + "\n" + text)


def fix_event_markers(path):
    """Events naming a marker joint their model lacks are fatal ("No valid markers for event", rendermodel);
    their mimics and Beast Swarmer do this. Drop those marker lines so the effect plays at the ship's root."""
    hod = path[:-len(".events")] + ".hod"
    if not os.path.exists(hod):
        return
    model = open(hod, "rb").read().lower()
    text = open(path, encoding="latin-1").read()
    if text.startswith("\x1bLua"):
        # compiled (smt_swarmer's is HW2's Hgn_Scout.events): no events rather than a missing marker
        if any(m.lower().encode() not in model for m in re.findall(r"marker_(\w+)", text)):
            open(path, "w", newline="\n").write("effects={\nanimations={},\nevents={}\n};\n")
            print("  emptied compiled events with missing markers:", os.path.relpath(path, DATA))
        return
    def keep(m):
        names = [n for n in m.group(2).split(",") if n.strip().lower().encode() in model]
        if not names:
            return ""
        return m.group(0) if len(names) == len(m.group(2).split(",")) else m.group(1) + ",".join(names) + m.group(3)

    # a marker entry may list several joints ("top_00,left_00,..."); only the ones the model has are kept
    fixed = re.sub(r'([ \t]*\{\s*"marker",\s*")([^"]+)("\s*,?\s*\},?[ \t]*\r?\n)', keep, text)
    if fixed != text:
        open(path, "w", encoding="latin-1", newline="").write(fixed)
        print("  dropped missing event markers:", os.path.relpath(path, DATA))


def main():
    copied = []
    # our own (git-tracked) files under data/ are never overwritten by either layer
    tracked = set(subprocess.run(["git", "ls-files", "data"], cwd=MOD, capture_output=True, text=True).stdout.split("\n"))
    ours = {t[len("data/"):].lower() for t in tracked if t.startswith("data/")}
    for root, _, files in os.walk(PP):   # the Players Patch first: theirs is copied over it
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), PP).replace("\\", "/")
            if rel.lower().startswith(PP_SKIP_PREFIX) or rel.lower() in ours:
                continue
            dst = os.path.join(DATA, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(root, fn), dst)
            copied.append(rel)
    for root, _, files in os.walk(SRC):
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), SRC).replace("\\", "/")
            low = rel.lower()
            if (low.startswith(SKIP_PREFIX) and not low.startswith(KEEP_PREFIX)) or low.endswith(SKIP_SUFFIX) \
                    or low in ours:
                continue
            dst = os.path.join(DATA, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(root, fn), dst)
            copied.append(rel)
    for rel, src in COPIES.items():
        os.makedirs(os.path.dirname(os.path.join(DATA, rel)), exist_ok=True)
        shutil.copyfile(os.path.join(SRC, src), os.path.join(DATA, rel))
        copied.append(rel)
    for rel, fn in PATCHES.items():
        p = os.path.join(DATA, rel)
        t = open(p, encoding="latin-1").read()
        open(p, "w", encoding="latin-1", newline="\n").write(fn(t))
    for rel in copied:
        if rel.endswith(".wepn"):
            p = os.path.join(DATA, rel)
            t = open(p, encoding="latin-1").read()
            open(p, "w", encoding="latin-1", newline="").write(patch_hw1_armour(t))
    for ship, (ours, joints) in OUR_MODELS.items():
        use_our_model(ship, ours, joints)
    for ship, (src, names) in OUR_EVENTS.items():
        use_our_events(ship, src, names)
    for ship, (cat, cls) in SPEEDS.items():
        set_speed(ship, cat, cls)
    set_costs()
    set_trails()
    drop_weapons()
    for root, _, files in os.walk(OVERRIDES):   # our own versions of their files (.events / .madstate)
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), OVERRIDES)
            shutil.copyfile(os.path.join(root, fn), os.path.join(DATA, rel))
    for rel in copied:
        if rel.endswith(".events"):
            fix_event_markers(os.path.join(DATA, rel))
    patch_speech_logic()
    # weapon-upgrade variants (tools/ship_variants.py), from their base ship as installed above
    for variant in ship_variants.VARIANTS:
        copied += ship_variants.build(variant)
    # the Mimic: their CustomCommand (a random one of three disguises) gives way to our Mimic menu
    mimic = os.path.join(DATA, "ship", "smt_mimic", "smt_mimic.ship")
    if os.path.exists(mimic):
        text = open(mimic, encoding="latin-1").read()
        text = re.sub(r'^(addAbility\(NewShipType,\s*"CustomCommand",\s*1,\s*"Mimic")',
                      r"-- Cataclysm-HWRM (our Mimic menu, shiprules.lua CatMimic_*): \1", text, flags=re.M)
        # it has no guns: its attack is a kamikaze (user), as stock HW1 resource collectors' (their CanAttack: the
        # kamikaze style on every family, the HW1 ones included: theirs left out Fighter_hw1, the Taiidan fighters)
        n = len(re.findall(r'^addAbility\(NewShipType,\s*"CanAttack".*$', text, flags=re.M))
        assert n == 1, f"smt_mimic: {n} CanAttack lines"
        text = re.sub(r'^addAbility\(NewShipType,\s*"CanAttack".*$', MIMIC_ATTACK.replace("\\", "\\\\"), text,
                      flags=re.M)
        open(mimic, "w", encoding="latin-1", newline="").write(text)
    ship_variants.write_lua()
    # the Mimic's transformation effects as events on the Mimic and its disguises (tools/make_mimicfx.py)
    import make_mimicfx
    make_mimicfx.patch_all_events()
    # Cataclysm's ship rules (experience, damage slowing ships, Acolyte link) on every ship the campaign uses
    copied += make_shipcode.install()
    # Cataclysm's health and weapon damage (user: all ships, Cataclysm's scale 1:1)
    copied += make_damage.apply(make_damage.plan())
    # every Somtaaw ship repairable (Cataclysm's repair beams take anything; HWRM repairs only ships with
    # CanBeRepaired: theirs left out the fighters, the ACV...: user, the Processor's ordered repair did nothing).
    # HWRM repairs only at RepCap latch points ("marked as repairable ... but has no repair points!"): our models
    # carry RepairPoint0 (geo2dae.py); ships with their own active RepCap list keep it.
    for d in sorted(os.listdir(os.path.join(DATA, "ship"))):
        path = os.path.join(DATA, "ship", d, d + ".ship")
        if not (d.startswith("smt_") and os.path.exists(path)):
            continue
        text = open(path, encoding="latin-1").read()
        if re.search(r'^\s*addAbility\(NewShipType,\s*"CanBeRepaired",\s*"RepCap"', text, re.M) and \
                re.search(r'^\s*loadLatchPointList\(NewShipType,\s*"RepCap"', text, re.M):
            continue
        hod = os.path.join(DATA, "ship", d, d + ".hod")
        points = os.path.exists(hod) and b"RepairPoint0" in open(hod, "rb").read()
        text = re.sub(r'^[ \t]*addAbility\(NewShipType,\s*"CanBeRepaired"[^\n]*\n?', "", text, flags=re.M)
        text = re.sub(r'^[ \t]*loadLatchPointList\(NewShipType,\s*"RepCap"[^\n]*\n?', "", text, flags=re.M)
        if points:
            add = ('addAbility(NewShipType, "CanBeRepaired", "RepCap");   -- Cataclysm-HWRM\n'
                   'loadLatchPointList(NewShipType, "RepCap", "RepairPoint0");   -- Cataclysm-HWRM\n')
        else:
            add = 'addAbility(NewShipType, "CanBeRepaired");   -- Cataclysm-HWRM\n'
        open(path, "w", encoding="latin-1", newline="").write(text.rstrip("\n") + "\n" + add)
    # the Mimic's kamikaze through HWRM's own: more health, more damage taken (tools/make_mimicarmour.py)
    import make_mimicarmour
    copied += [f"weapon/{w}" for w in make_mimicarmour.install()]
    # Cataclysm's mission backgrounds (tools/make_background.py; their light .hod is stock ez01's, 22 MB)
    for name, (btg, theta, phi) in make_background.BACKGROUNDS.items():
        copied += make_background.convert(os.path.join(make_background.BIG, btg + ".btg"), name, theta, phi)
    # stock skies relit with a Cataclysm mission's lights (make_background.RELIGHT; the light .hod is 17 MB of stock data)
    for sky, mission in make_background.RELIGHT.items():
        copied += make_background.relight(sky, mission)
    # both layers can list a file (theirs over the patch's): once, in the last spelling
    copied = sorted({rel.lower(): rel for rel in copied}.values())
    # files an earlier install put in data/ that are no longer installed (git-tracked files are ours: kept)
    manifest = os.path.join(DATA, "cr_files.txt")
    old = set(open(manifest).read().split("\n")) - {""} if os.path.exists(manifest) else set()
    removed = 0
    for rel in sorted(old - set(copied)):
        p = os.path.join(DATA, rel)
        if "data/" + rel not in tracked and os.path.isfile(p):
            os.remove(p)
            removed += 1
            d = os.path.dirname(p)
            while d != DATA and os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
                d = os.path.dirname(d)
    if removed:
        print(f"  removed {removed} Cataclysm Remastered files no longer installed")
    with open(manifest, "w", newline="\n") as f:
        f.write("\n".join(copied) + "\n")
    with open(os.path.join(DATA, ".gitignore"), "w", newline="\n") as f:
        f.write("# Generated by tools/install_cr.py: Cataclysm Remastered files (not committed)\n")
        f.write("\n".join("/" + re.sub(r"([\[\]*?])", r"\\\1", r) for r in copied) + "\n")
    print(f"installed {len(copied)} Cataclysm Remastered files into data/ ({len(PATCHES)} patched, {len(COPIES)} replaced, {len(OUR_MODELS)} on our models)")


if __name__ == "__main__":
    main()
