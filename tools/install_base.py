"""Install the mod's base data layer: the Players Patch (below, PP), then our Somtaaw and Beast races and ships
generated from stock HWRM (Gearbox's HW1 ships as templates), then Cataclysm's data over them (costs, speeds,
health and damage, abilities, ship rules, events, voices). No file from Cataclysm Remastered / HWU (REBUILD.md).

Ships: each smt_* / bst_* type is a copy of a stock HW1 ship (TEMPLATES: its .ship, model, .events, .mad), renamed;
our converted models (tools/build_ship.sh, OUR_MODELS) replace the template's model, and every other ship keeps its
template's model as a stand-in until converted (user, 2026-10-14). Races: stock Kushan (Somtaaw) and Taiidan (Beast)
race folders under our names, with our build / research lists (tools/make_race.py).
Installed files are listed in data/cr_files.txt and git-ignored through data/.gitignore (stock and PP files are not
ours to commit); a file an earlier install put there and this one doesn't is removed.

Usage: install_base.py
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

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(MOD, "data")
REF = r"C:\Modding\Cataclysm-decomp\reference"
# stock HWRM, in load order (the HW1 campaign's files over the base game's)
STOCK = [os.path.join(REF, "hwrm", "Homeworld2"), os.path.join(REF, "hwrm", "HW1Ships"),
         os.path.join(REF, "hwrm", "HW1Campaign")]

# The Homeworld Remastered 2.3 Players Patch (workshop 1190476337, extracted with hw2big.py; kept, user 2026-10-14):
# the community's fixes (formations / strike groups, cross-race docking, SCAR library fixes) and its HW1 ships, which
# our Kushan and Taiidan use (tools/make_shipcode.py copies its .ship over stock's). Not its campaign / multiplayer
# levels. Its HW1 rebalance comes along for now; the target is Cataclysm's balance (user).
PP = os.path.join(REF, "players_patch")
PP_SKIP_PREFIX = ("leveldata/", "keeper.txt")
CATSPEECH_LINE = 'dofilepath("data:soundscripts/cataclysm/catspeech.lua")   -- Cataclysm-HWRM: Somtaaw voices'
MARK = "-- Cataclysm-HWRM base: "   # first line of a generated .ship (make_shipcode.py looks for it)

# Our ship types -> the stock HW1 ship each is made from: the Somtaaw from the Kushan, the Beast from the Taiidan (so
# the two read differently while on stand-in models), by Cataclysm class and role
TEMPLATES = {
    # our models (OUR_MODELS)
    "smt_ms_sp": "kus_mothership", "smt_ms": "kus_mothership", "smt_worker": "kus_resourcecollector",
    "smt_scout": "kus_scout", "smt_acolyte": "kus_interceptor", "smt_acv": "kus_heavycorvette",
    "smt_mimic": "kus_interceptor", "smt_processor": "kus_resourcecontroller", "smt_rammingfrigate": "kus_assaultfrigate",
    # stand-ins (the template's model)
    "smt_carrier": "kus_carrier", "smt_destroyer": "kus_destroyer", "smt_dreadnought": "kus_heavycruiser",
    "smt_hivefrigate": "kus_supportfrigate", "smt_multibeamfrigate": "kus_ioncannonfrigate",
    "smt_sentinel": "kus_defender", "smt_swarmer": "kus_interceptor",
    "bst_acolyte": "tai_interceptor", "bst_acv": "tai_heavycorvette", "bst_attackbomber": "tai_attackbomber",
    "bst_carrier": "tai_carrier", "bst_cloakedfighter": "kus_cloakedfighter", "bst_cruisemissile": "tai_lightcorvette",
    "bst_heavycorvette": "tai_heavycorvette", "bst_heavycruiser": "tai_heavycruiser",
    "bst_hivefrigate": "tai_supportfrigate", "bst_ionarrayfrigate": "tai_ioncannonfrigate",
    "bst_missilecorvette": "tai_multiguncorvette", "bst_mothership": "tai_mothership",
    "bst_multibeamfrigate": "tai_ioncannonfrigate", "bst_multiguncorvette": "tai_multiguncorvette",
    "bst_rammingfrigate": "tai_assaultfrigate", "bst_swarmer": "tai_interceptor",
    # derelicts: Mission02's message pod (dMessagePod), towed home by a Worker's capture latch (HW1's salvage):
    # Gearbox's salvageable cryo tray (HW1 Mission03's, SalCap on SalvagePoint1), on our model
    "cat_messagepod": "kus_cryotray_m03",
}

# Our races: (stock race it is made from, display name, ship prefix, strike group tags)
RACES = {"somtaaw": ("kushan", "Somtaaw", "SMT_", "sgf_common,sgf_kus"),
         "beast": ("taiidan", "The Beast", "BST_", "sgf_common,sgf_tai")}
RACE_FILE = '''Path_Name = "{name}"
Symbolic_Name = "{name}"
Display_Name = "{display}"
Prefix = "{prefix}"

ExtFilter = "races_gbx,races_hw1,races_hwrm,races_dm,races_dm_hw1,races_gbx_hwrmc"
Tags = "race_gbx,race_hw1,race_hwrm,race_dm,race_dm_hw1,race_gbx_hwrmc"

SG_Pass_Tags = "{sg}"
'''
OURS = set()   # git-tracked data/ paths (lower case, below data/): never overwritten
# Build families: the templates' <family>_Kus / _Tai become our races' (familylist.lua gets them: patch_families)
BUILD_FAMILIES = ["Fighter", "Corvette", "Frigate", "SuperCap", "Battlecruiser", "Flagship", "Resource", "NonCombat",
                  "SubSystem", "Mover", "Utility", "Probe", "Research", "Shipyard"]
FAMILY_SUFFIX = {"smt_": "Smt", "bst_": "Bst"}


def patch_families(text):
    """The stock / Players Patch familylist plus our races' build families (BUILD_FAMILIES x FAMILY_SUFFIX)."""
    text = text.replace("\r\n", "\n")
    add = "".join('\t{\n\t\tname = "%s_%s",\n\t},\n' % (f, s) for s in FAMILY_SUFFIX.values() for f in BUILD_FAMILIES
                  if '"%s_%s"' % (f, s) not in text)
    new = text.replace("buildFamily =\n{\n", "buildFamily =\n{\n" + add, 1)
    assert new != text or not add, "familylist.lua: no buildFamily section"
    if '"SupportUnits"' not in new:   # Support Units as a native unit cap (set_support_units)
        text = new
        new = new.replace("unitcapsFamily =\n{\n", "unitcapsFamily =\n{\n" + SU_FAMILY, 1)
        assert new != text, "familylist.lua: no unitcapsFamily section"
    return new


def stock_tree(rel):
    """{path below rel: source file} of a stock folder, later layers over earlier ones."""
    files = {}
    for root in STOCK:
        base = os.path.join(root, rel)
        for d, _, fns in os.walk(base):
            for fn in fns:
                files[os.path.relpath(os.path.join(d, fn), base).replace("\\", "/")] = os.path.join(d, fn)
    return files


def gen_ship(ship, template):
    """data/ship/<ship>/ from the stock template's folder, renamed: its .lua build script and the custom code that
    loads it are left out (the Kushan research ships; our ship rules are make_shipcode.py's)."""
    folder = os.path.join(DATA, "ship", ship)
    out = []
    pp = os.path.join(PP, "ship", template, template + ".ship")   # the Players Patch's fixes to the HW1 ships
    for rel, src in sorted(stock_tree(os.path.join("ship", template)).items()):
        if rel.lower().endswith(".lua") and "/" not in rel:
            continue
        dst_rel = re.sub(re.escape(template), ship, rel, flags=re.I)
        out.append(f"ship/{ship}/{dst_rel}")
        if out[-1].lower() in OURS:
            continue
        dst = os.path.join(folder, dst_rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if rel.lower() == template + ".ship" and os.path.exists(pp):
            src = pp
        if rel.lower().endswith((".ship", ".madstate", ".events")):
            text = open(src, encoding="latin-1").read()
            # (the madstate's functions are <TYPE>_<state>_OnSet: the engine calls them by the ship type's name)
            text = re.sub(r"\b%s(?=_|\b)" % re.escape(template), ship.upper(), text, flags=re.I) \
                if rel.lower().endswith(".madstate") else re.sub(r"\b%s\b" % re.escape(template.upper()), ship.upper(), text)
            text = re.sub(r"ship/%s/%s" % (re.escape(template), re.escape(template)), f"ship/{ship}/{ship}", text,
                          flags=re.I)
            if rel.lower().endswith(".ship"):
                text = re.sub(r'^[ \t]*addCustomCode\(NewShipType,\s*"data:ship/%s/[^\n]*\n?' % re.escape(ship), "",
                              text, flags=re.M | re.I)
                # and its custom commands that run from that .lua (the HW1 Scout's Speed Burst: not Cataclysm's, user)
                # kept but off from the start (addAbility's enable flag 0, as Cataclysm Remastered's Recon has its
                # SensorPing / EMP): commented out, HWRM's custom-code loader crashed loading any mission (access
                # violation in CustomCodeManagerStatic::onLoad, bisected 2026-10-17)
                text = re.sub(r'^([ \t]*addAbility\(NewShipType,\s*"CustomCommand",\s*)1(\s*,[^\n]*"data:ship/%s/)'
                              % re.escape(ship), r"\g<1>0\2", text, flags=re.M | re.I)
                # the template's abilities Cataclysm's ship lacks (upgrades_gen.lua CatUpgradeType, the .shp guns):
                # the Heavy Corvette's burst attack on the ACV, the Support Frigate's repair on the Hive Frigate (user,
                # 2026-10-17: only abilities that should be visible)
                # (the whole statement, every line of it: the Support Frigate's repair runs over 20 lines, and only its
                # first commented left the rest a parse error, a crash on loading Mission02)
                for ability in TEMPLATE_DROP.get(ship, []):
                    text = re.sub(r'^[ \t]*addAbility\((?:NewShipType,\s*)?"%s".*?\)[ \t]*;?[ \t]*$' % ability,
                                  lambda m: "-- Cataclysm-HWRM (the template's ability):\n" +
                                  "\n".join("-- " + line for line in m.group(0).split("\n")),
                                  text, flags=re.M | re.S)
                # our race's own build families (FAMILY_SUFFIX): built by our builders, not the Kushan / Taiidan ones
                text = re.sub(r"\b(%s)_(Kus|Tai)\b" % "|".join(BUILD_FAMILIES), r"\1_" + FAMILY_SUFFIX.get(ship[:4], r"\2"),
                              text)
                text = f"{MARK}{template} (tools/install_base.py)\n" + text
            open(dst, "w", encoding="latin-1", newline="").write(text)
        else:
            shutil.copyfile(src, dst)
    return out


# template abilities (addAbility names) a ship doesn't keep, not being Cataclysm's (gen_ship)
TEMPLATE_DROP = {"smt_acv": ["SpecialAttack"], "smt_hivefrigate": ["RepairCommand"]}


ENGLISH = r"C:\Modding\Cataclysm-decomp\extracted\big\english.script"


def set_names():
    """Each generated ship's name and description: Cataclysm's (english.script str<ship> / str<ship>Info, the
    Cataclysm type from tools/shipmap.tsv), in place of the stock template's ("$10002", Interceptor...). Names in title
    case as our build lists show them (short ones, ACV, as they are); descriptions Cataclysm's build manager text."""
    strings = {}
    for line in open(ENGLISH, encoding="latin-1"):
        m = re.match(r"str(\w+)\s+(.+?)\s*$", line)
        if m:
            strings.setdefault(m.group(1).lower(), m.group(2))
    cat = {}
    for line in list(open(os.path.join(MOD, "tools", "shipmap.tsv"), encoding="utf-8"))[1:]:
        cols = line.rstrip("\n").split("\t")
        if len(cols) >= 3 and cols[2]:
            cat.setdefault(cols[2].lower(), cols[1].lower())
    cat.setdefault("smt_ms", "smothership")   # (the other Kuun-Lan type: no shipmap row)
    lua = lambda s: s.replace("\\", "\\\\").replace('"', '\\"').replace("\\\\n", "\\n")
    n = 0
    for ship in TEMPLATES:
        c = cat.get(ship)
        if not c or c not in strings:
            continue
        name = strings[c]
        name = name if len(name) <= 4 else name.title()
        info = strings.get(c + "info", "")
        if info.startswith(("09###", "11###")) or "NEVER APPEARS" in info:
            info = ""
        path = os.path.join(DATA, "ship", ship, ship + ".ship")
        text = open(path, encoding="latin-1").read()
        text = re.sub(r'^(\s*NewShipType(?:\.displayedName|\["displayedName"\])\s*=\s*)"[^"]*"', lambda m: m.group(1)
                      + f'"{lua(name)}"', text, count=1, flags=re.M)
        text = re.sub(r'^(\s*NewShipType(?:\.sobDescription|\["sobDescription"\])\s*=\s*)"[^"]*"', lambda m: m.group(1)
                      + f'"{lua(info or name)}"', text, count=1, flags=re.M)
        open(path, "w", encoding="latin-1", newline="").write(text)
        n += 1
    print(f"  Cataclysm names on {n} ships")


def gen_race(race, src, display, prefix, sg):
    """scripts/races/<race>/ from the stock race's folder, and scripts/races/<race>.lua; our own files there (git
    tracked: sp_build / sp_research) are kept."""
    out = []
    for rel, path in sorted(stock_tree(os.path.join("scripts", "races", src)).items()):
        dst_rel = f"scripts/races/{race}/{rel}"
        out.append(dst_rel)
        if dst_rel.lower() in OURS:
            continue
        dst = os.path.join(DATA, dst_rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(path, dst)
    with open(os.path.join(DATA, "scripts", "races", race + ".lua"), "w", encoding="latin-1", newline="\n") as f:
        f.write(RACE_FILE.format(name=race.capitalize(), display=display, prefix=prefix, sg=sg))
    return out + [f"scripts/races/{race}.lua"]


RESEARCH_HP = ('StartShipHardPointConfig(NewShipType,"Research Module","Hardpoint_Research","System","Innate",'
               '"Damageable","HW1_ResearchModule","","","","","","","","");')


TO_MOTHERSHIP = "\n".join(f"NewShipType.{k}={v}" for k, v in (
    ("TODistanceFade0", 14000), ("TODistanceDisappear0", 12000), ("TODistanceFade1", 5500),
    ("TODistanceDisappear1", 5000), ("TODistanceFade2", 12000), ("TODistanceDisappear2", 35000)))


def after_load_model(text, add):
    """add after the .ship's LoadModel line (hardpoints and weapons must come after it)."""
    new, n = re.subn(r"^([ \t]*LoadModel\(NewShipType,\s*1\);[^\n]*\n)", lambda m: m.group(1) + add.rstrip("\n") + "\n",
                     text, count=1, flags=re.M)
    assert n == 1, "no LoadModel line"
    return new


def patch_ms_sp(text):
    """Cataclysm researches without building a research module: innate HW1 research module on the Kuun-Lan's
    Hardpoint_Research (our model's), its module slots
    (tools/make_modules.py) and Cataclysm's guns (user): smothership.shp GUN1-6, six large hidden gimbals (GUN0 is the
    siege cannon, its module's); data/weapon/cat_kuunlan_gun*. Its tactical overlay icon fades as stock HW1
    kus_mothership's (engine defaults: it vanished zooming out before the Workers' did, user)."""
    if "TODistanceFade0" not in text:
        text = text.rstrip("\n") + "\n" + TO_MOTHERSHIP + "\n"
    # it builds its modules (subsystems, tools/make_modules.py: SubSystem_Smt) in a Modules tab
    if "SubSystem_Smt" not in text:
        text, n = re.subn(r'(addAbility\(NewShipType,\s*"CanBuildShips",\s*1,\s*"[^"]*)("\s*,\s*"[^"]*)"',
                          r'\1, SubSystem_Smt\2, SubSystemModule"', text, count=1)
        assert n == 1, "Kuun-Lan: no CanBuildShips"
    # its parade: Cataclysm's layout (tools/make_parade.py), not the stock Kushan Mothership's (user: it reset)
    text = re.sub(r'(NewShipType(?:\.paradeData|\["paradeData"\])\s*=\s*)"[^"]*"', r'\1"smt_mothership_parade"', text)
    for key, v in KUUNLAN_MOVE.items():
        text, n = re.subn(r'^([ \t]*NewShipType(?:\.%s|\["%s"\])\s*=\s*)[^;\n]*' % (key, key), r"\g<1>%g" % v, text,
                          count=1, flags=re.M)
        if not n:
            text = text.rstrip("\n") + f"\nNewShipType.{key}={v:g}\n"
    if "cat_kuunlan_gun" in text:
        return text
    guns = "\n".join(f'StartShipWeaponConfig(NewShipType,"cat_kuunlan_gun{"" if k <= 4 else "60"}",'
                     f'"Weapon_GUN{k}","Weapon_GUN{k}");' for k in range(1, 7))
    return after_load_model(text, "-- Cataclysm-HWRM: Cataclysm's Kuun-Lan guns (GUN1-4 85 deg, GUN5-6 60 deg)\n" + guns +
                            "\n-- Cataclysm-HWRM: innate research module\n" + RESEARCH_HP +
                            "\n-- Cataclysm-HWRM: Kuun-Lan module slots (tools/make_modules.py)\n" +
                            "\n".join(make_modules.hardpoint_lines()))


def patch_sp_props(text):
    """Single-player build/research lists: ours (tools/make_race.py: Cataclysm's tech tree), in place of the stock
    race's (the HW1 campaign's props point at the Kushan lists)."""
    text = re.sub(r"^[ \t]*path_(?:build|research)\s*=[^\n]*\n", "", text, flags=re.M)
    return text.replace("String_Properties = {", "String_Properties = {\n"
                        "\tpath_build = [[data:scripts/races/somtaaw/scripts/sp_build.lua]],\n"
                        "\tpath_research = [[data:scripts/races/somtaaw/scripts/sp_research.lua]],", 1)


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
    "processor": (1400, "Broadside_CatRepair"),
}
# The Worker: HWRM's own latching repair (4th argument 0, as the HW2 collectors; the engine heals at 30 / s), in the
# stock approach styles (user: back to regular healing; latching onto fighters to be solved later)
WORKER_REPAIR_STYLES = {"Fighter": "Frontal_SupportFrigate", "Fighter_hw1": "Frontal_SupportFrigate",
                        "Corvette": "Frontal_SupportFrigate", "Corvette_hw1": "Frontal_SupportFrigate",
                        "Utility": "Frontal_SupportFrigate", "Resource": "Frontal_SupportFrigate",
                        "ResourceLarge": "Frontal_RepairFrigate_SmallCap", "NonCombat": "Frontal_SupportFrigate",
                        "Frigate": "Frontal_RepairFrigate_Frigate", "SmallCapitalShip": "Frontal_RepairFrigate_SmallCap",
                        "BigCapitalShip": "Frontal_RepairFrigate_BigCap",
                        "Mothership": "Frontal_RepairFrigate_Mothership"}


def repair_order(text, kind):
    """Their RepairCommand (or a new one after RetireAbility) replaced by ours."""
    if kind == "worker":
        order = ('addAbility(NewShipType,"RepairCommand",1,500,30,0,"Frontal_SupportFrigate",{EndRepairRates=0},'
                 + ",".join('{%s="%s"}' % kv for kv in WORKER_REPAIR_STYLES.items()) + ");   -- Cataclysm-HWRM")
    else:
        rng, style = REPAIR_BEAMS[kind]
        order = (f'addAbility(NewShipType,"RepairCommand",1,{rng},30,1,"{style}",{{EndRepairRates=0}},'
                 + ",".join('{%s="%s"}' % (f, style) for f in REPAIR_FAMILIES) + ");   -- Cataclysm-HWRM")
    new, n = re.subn(r'^\s*addAbility\(NewShipType,\s*"RepairCommand".*?\);[^\n]*$', order, text,
                     count=1, flags=re.M | re.S)
    if not n:
        new = text.rstrip("\n") + "\n" + order + "\n"
    return new


def kuunlan_engines(text, size):
    """The Kuun-Lan's engine burn (their smt_ms_sp.ship setEngineBurn 9, 0.2, 0.5, 300, 1.02, 0.1, 0.25, 380) beside a
    ship's setEngineGlow (theirs is the Kuun-Lan's already on the Processor and Ramming Frigate; user: the same
    engines as the Kuun-Lan's), its lengths (300, 380: stock HW1 frigates 60, 120, the Worker 4, 15) times size (both
    1: the Ramming Frigate's normal engines are the Processor's exactly, user)."""
    if "setEngineBurn" in text:
        return text
    assert text.count("setEngineGlow(NewShipType") == 1
    return text.replace("setEngineGlow(NewShipType", f"setEngineBurn(NewShipType, 9, 0.2, 0.5, {300 * size:.4g}, 1.02, "
                        f"0.1, 0.25, {380 * size:.4g});   -- Cataclysm-HWRM: the Kuun-Lan's, x{size}\n"
                        "setEngineGlow(NewShipType", 1)


def patch_processor(text):
    """An ordered repair (user: Cataclysm's Processor only repaired what drifted into its beams; here also on order:
    shiprules.lua CatProcessor_* runs the automatic beams): the Worker's RepairCommand at Cataclysm's repair rate
    (tweak.script twRepairRate 30 / s). Both only once it has the Repair upgrade (shiprules.lua CatGated). Engines: the
    Kuun-Lan's burn (their smt_ms_sp.ship setEngineBurn; its setEngineGlow is the Kuun-Lan's already; user: same
    engine glow as the Kuun-Lan's)."""
    return repair_order(kuunlan_engines(text, 1), "processor")   # as the Kuun-Lan's (user: leave it as it was)


def patch_worker(text):
    """Cataclysm's Worker repairs; their RepairCommand was disabled. (How far off it harvests is set by the
    model's LatchOrientation joint, not by the Harvest ability: tools/build_ship.sh --latch.) No NLIPS (its icon
    and selection box scaled up with distance: user)."""
    text = re.sub(r"^(\s*NewShipType\.nlips(?:Range|Far|FarRange)?\s*=\s*)[\d.]+", r"\g<1>0", text, flags=re.M)
    # Its dock family stays the collector's (Utility), so it latches on the Processor's RU pads. After a salvage
    # capture latches, SalCap needs a carrier with a plain path for the salvager's family and no latch path for it
    # (FUN_004b14d7 / FUN_004b0a9e mode 5): as Utility the Kuun-Lan's nose RU latch paths made it let go every time,
    # so the Kuun-Lan has none for now (build_kuunlan.sh --no-res: Workers unload in its hangar, "Corvette, Utility";
    # the Processor's Utility latch paths rule it out as a carrier). (As Corvette, 2026-10-17, salvage worked but the
    # Worker nosed into the Processor's pads, or with plain paths vanished inside: user, the Processor is a release
    # blocker; 2026-10-18)
    # and salvages as HW1 did (its SALVAGE upgrade; Cataclysm's capturing is HW1's): stock kus_salvagecorvette's
    # capture latch, SalCapCommand, latched by its LatchOrientation (tools/build_ship.sh cat_messagepod), declared
    # off (enable flag 0: switched off from script only, it salvaged before the upgrade, user) and switched on by the
    # upgrade (shiprules.lua CatGated_Tick, AB_SalCap). Not the HW2 salvage-object order its template has
    # (SalvageCommand: it harvested containers like rocks, never towed them, user)
    text = re.sub(r'^[ \t]*addAbility\(NewShipType,\s*"(?:SalvageCommand|SalCapCommand)"[^\n]*\n?', "", text, flags=re.M)
    text = text.rstrip("\n") + '\naddAbility(NewShipType,"SalCapCommand",0,500,0,0);   -- Cataclysm-HWRM: salvage\n'
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
# an active CanAttack statement, all its lines (stock HW1 ships list one attack style per line)
CAN_ATTACK = re.compile(r'^addAbility\(NewShipType,\s*"CanAttack".*?\);[^\n]*', re.M | re.S)


def comment_out(stmt, why):
    """every line of a statement commented out"""
    lines = stmt.split("\n")
    return "\n".join([f"-- Cataclysm-HWRM ({why}): " + lines[0]] + ["-- " + l for l in lines[1:]])


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


def patch_rammingfrigate(text):
    """Cataclysm's ram grapples onto a target's salvage points (user: the points resourcers dock to when salvaging;
    Cataclysm lines up far more loosely than HWRM could from script): HWRM's own salvage-capture latch (stock
    kus_salvagecorvette's SalCapCommand), which shiprules.lua CatRam_Tick turns into the hit, push and cutting beam.
    No attack (no guns): a right-click on an enemy is the latch
    (SobGroup_SalvageSobGroup from script did nothing)."""
    # the Processor's engines (user), but the stock HW1 frigates' burn (kus_assaultfrigate & co.): the Kuun-Lan's
    # drew a white ball as big as the frigate over its rear (user: pics/engine-normal.jpg)...
    if "setEngineBurn" not in text:
        assert text.count("setEngineGlow(NewShipType") == 1
        # ...and its glow a little dimmer (user)
        text, n = re.subn(r"\{\s*0\.27,\s*0\.47,\s*0\.69,\s*0\.25\s*\}", "{0.216, 0.376, 0.552, 0.25}", text, count=1)
        assert n == 1
        text = text.replace("setEngineGlow(NewShipType", "setEngineBurn(NewShipType,6,1.7,2.55,102,1.1,0.1,0.2,204);   "
                            "-- Cataclysm-HWRM: stock HW1 frigates' x1.7 (one nozzle for its three), a little dimmer\n"
                            "setEngineGlow(NewShipType", 1)
    if '"SalCapCommand"' in text:
        return text
    text = re.sub(CAN_ATTACK, lambda m: comment_out(m.group(0), "the ram is its salvage latch"), text, count=1)
    return (text.rstrip("\n") +
            '\naddAbility(NewShipType,"SalCapCommand",1,500,0,0);   -- Cataclysm-HWRM: the ram\'s latch\n')


SU_FRAME = """
				-- Cataclysm-HWRM: Support Units, used / limit (Cataclysm's build manager "SU:"; set by cataclysmkas.lua
				-- KAS_SUTick)
				{
					type = "Frame",
					Layout = {
						size_WH = {	w = 1, h = 1.0, wr = "par", hr = "px" },
					},
					autosize = 1,
					;
					{
						type = "TextLabel",
						name = "lblSUHeading",
						autosize=1,
						ignored = 1,
						Layout = {
							size_WH = {w = .70, h = STD_LABEL_HEIGHT, wr = "par", hr = "scr",},
						},
						dropShadow = 1,
						Text = {
							text = "Support Units",
							textStyle = "IGHeading2",
							minShrink = 0.25,
						},
					},
					{
						type = "TextLabel",
						name = "lblSUCount",
						ignored = 1,
						Layout = {
							size_WH = {w = .25, h = STD_LABEL_HEIGHT, wr = "par", hr = "scr",},
							pos_XY = { x = 1.0, xr = "par" },
							pivot_XY = { 1,  0 },
						},
						autosize = 1,
						dropShadow = 1,
						Text = {
							textStyle = "IGHeading2",
							hAlign = "Right",
							minShrink = 0.25,
						},
					},
				},
"""


def patch_build_menu(text):
    """The build menu's subsystem lines (Production / Module / Sensors slots) get Cataclysm's Support Units line
    (SU_FRAME, filled by the runtime's KAS_SUTick)."""
    if "lblSUCount" in text:
        return text
    text, n = re.subn(r"(\n\t\t\t\},\n\t\t\t-+ END Subsystem stat labels)", lambda m: SU_FRAME.rstrip("\n") + m.group(1),
                      text, count=1)
    assert n == 1
    return text


def patch_sp_unitcaps(text):
    """Cataclysm's unit caps (unitlimitcaps.script, cataclysm.exe FUN_0053ece0): only the types not left to Support
    Units (cap -1): CapsCarrier 2 (the Kuun-Lan's modules are one per hardpoint, 12 Support Modules). Theirs called
    UC_FamilyOverride, which HWRM lacks (the file failed at its first line). Support Units: set_support_units.
    Cataclysm's ShipTotalCaps 297 is left out: Support Units stop a fleet well short of it."""
    return ("-- Cataclysm-HWRM (install_base.py patch_sp_unitcaps): Cataclysm's unit caps, and Support Units as one\n"
            "supplyLimit(\"Carrier\", 2)   -- unitlimitcaps.script CapsCarrier\n"
            f"supplyLimit(\"SupportUnits\", {SU_CAP})   -- Support Units: filler ships hold what's above the limit "
            "(set_support_units)\n"
            "supplyShow(\"SupportUnits\", \"Never\")   -- (the fillers are in it: the build menu's own SU line shows "
            "used / limit)\n")


# Support Units as a native unit cap (Complex EVO's filler ships, workshop 398406822): every type the Somtaaw build
# list has takes its SU from the "SupportUnits" cap (HWRM counts queues at the click, as Cataclysm did), capped at
# SU_CAP; the runtime (cataclysmkas.lua KAS_SUTick) holds what's above the mission's SU limit with filler ships.
# Learned in game (2026-10-14): a type counts only if the race's build list has it (make_race.py lists the fillers,
# gated by a research that doesn't exist); a despawned ship doesn't count, one in the world does.
SU_CAP = 250         # the engine held a limit of 400 at ~250 (in game 2026-10-17); Cataclysm's most is 300 (Kuun-Lan 70 + Hangar 30 + 12 Support Modules 120 + 2 Carriers 80)
SU_FILLERS = [("cat_sufiller25", 25), ("cat_sufiller5", 5), ("cat_sufiller1", 1)]   # largest first (make_race.py)
SU_FAMILY = ('\t{\n\t\tname = "SupportUnits",\n\t\tnumParam = 95,\n\t\tstringParam = "Support Units",\n\t},\n')
SU_FILLER_SHIP = """NewShipType = StartShipConfig()
-- Generated by tools/install_base.py set_support_units: a Support Units filler (hidden, far below the map)
NewShipType.displayedName = "Support Units"
NewShipType.maxhealth = 1000000
NewShipType.mass = 0
NewShipType.AttackFamily = "UnAttackable"
NewShipType.AvoidanceFamily = "None"
NewShipType.CollisionFamily = "Unmoveable"
NewShipType.DisplayFamily = "Utility"
NewShipType.visualRange = 0
NewShipType.prmSensorRange = 0
NewShipType.secSensorRange = 0
NewShipType.mouseOverMinFadeSize = 0
NewShipType.mouseOverMaxFadeSize = 0
NewShipType.meshRenderLimit = 0
NewShipType.visibleInSecondary = 0
NewShipType.selectionLimit = 0
NewShipType.preciseSelectionLimit = 0
NewShipType.preciseATILimit = 0
NewShipType.selectionPriority = 0
NewShipType.militaryUnit = 0
setSupplyValue(NewShipType, "SupportUnits", {su})
LoadSharedModel(NewShipType, "kus_probe")
"""


def set_support_units():
    """Each Somtaaw build-list ship's SU (tools/make_supportunits.py's CatSU_Cost) as its "SupportUnits" supply
    value, the filler ships, and data/scripts/cataclysm/sunative_gen.lua for the runtime (the cap, the fillers, the
    types the engine counts: the script adds the others' SU to the fillers). Returns the files it made."""
    gen = open(os.path.join(DATA, "scripts", "cataclysm", "supportunits_gen.lua"), encoding="latin-1").read()
    costs = dict(re.findall(r'\["(\w+)"\]\s*=\s*(\d+)', gen.split("CatSU_Cost", 1)[1].split("}", 1)[0]))
    listed = set(re.findall(r'ThingToBuild\s*=\s*"(\w+)"', open(
        os.path.join(DATA, "scripts", "races", "somtaaw", "scripts", "sp_build.lua"), encoding="latin-1").read()))
    native = []
    for ship, su in sorted(costs.items()):
        path = os.path.join(DATA, "ship", ship, ship + ".ship")
        if not (ship in listed and os.path.exists(path)):
            continue
        text = open(path, encoding="latin-1").read()
        text = re.sub(r'^setSupplyValue\(NewShipType, "SupportUnits"[^\n]*\n?', "", text, flags=re.M)
        text = text.rstrip("\n") + f'\nsetSupplyValue(NewShipType, "SupportUnits", {su})   -- Cataclysm-HWRM: Support Units\n'
        open(path, "w", encoding="latin-1", newline="").write(text)
        native.append(ship)
    made = []
    for name, su in SU_FILLERS:
        assert name in listed, f"{name} not in sp_build.lua (rerun tools/make_race.py): it wouldn't count"
        os.makedirs(os.path.join(DATA, "ship", name), exist_ok=True)
        open(os.path.join(DATA, "ship", name, name + ".ship"), "w", encoding="latin-1", newline="\n").write(
            SU_FILLER_SHIP.replace("{su}", str(su)))
        made.append(f"ship/{name}/{name}.ship")
    lua = ["-- Generated by tools/install_base.py set_support_units: Support Units as the engine's unit cap",
           f"CatSU_Cap = {SU_CAP}",
           "CatSU_Fillers = { " + ", ".join(f'{{ "{n}", {s} }}' for n, s in SU_FILLERS) + " }",
           "CatSU_Native = { " + ", ".join(f'["{s}"] = 1' for s in native) + " }", ""]
    rel = "scripts/cataclysm/sunative_gen.lua"
    open(os.path.join(DATA, rel), "w", encoding="latin-1", newline="\n").write("\n".join(lua))
    print(f"  Support Units supply values on {len(native)} ships; fillers {', '.join(n for n, _ in SU_FILLERS)}")
    return made + [rel]


def patch_messagepod(text):
    """Cataclysm's dmessagepod.shp maxhealth 8000 (tools/make_damage.py covers the races' ships, not derelicts). Its
    dock family Utility, docked into the Kuun-Lan's medium bay (geo2dae.py PATH_FAMILIES). After the latch SalCap looks
    for a carrier for the docking ship (FUN_004b14d7: one with a plain path for its family and no latch path,
    FUN_004b0a9e mode 5) and lets go when there is none: a Worker (Utility, the Kuun-Lan's RU latch paths) was let go
    every time; made Corvette it latched, towed and docked this pod (user, 2026-10-17; tools/install_base.py
    patch_worker). (Pod Corvette or Controller with a Utility Worker: let go, user. The cryo tray's SuperCap has no
    path on the Kuun-Lan: towed home, never docked, user.)"""
    text = re.sub(r'^(\s*NewShipType\.DockFamily\s*=\s*)"[^"]*"', r'\g<1>"Utility"', text, count=1, flags=re.M)
    return re.sub(r'^(\s*NewShipType\.maxhealth\s*=\s*)[^\n]*', r'\g<1>8000   -- Cataclysm-HWRM: dmessagepod.shp', text,
                  count=1, flags=re.M)


PATCHES = {
    "ship/cat_messagepod/cat_messagepod.ship": patch_messagepod,
    "scripts/races/somtaaw/singleplayer/unitcaps/singleplayer.lua": patch_sp_unitcaps,
    "ui/newui/build/finalbuild.lua": patch_build_menu,
    "ship/smt_rammingfrigate/smt_rammingfrigate.ship": patch_rammingfrigate,
    "ship/smt_ms_sp/smt_ms_sp.ship": patch_ms_sp,
    "ship/smt_ms/smt_ms.ship": patch_ms_sp,
    "ship/smt_worker/smt_worker.ship": patch_worker,
    "ship/smt_processor/smt_processor.ship": patch_processor,
    "ship/smt_acolyte/smt_acolyte.ship": patch_acolyte,
    "scripts/races/somtaaw/singleplayer/props/gbx.lua": patch_sp_props,
    "scripts/familylist.lua": patch_families,
}

# Our models (tools/build_ship.sh: Cataclysm's geometry at Gearbox's scale, matching the converted NIS and levels)
# under the template's setup: (our model, template joint -> ours). The template's weapons give way to OUR_WEAPONS;
# its hardpoint configs on joints our model lacks are commented out.
BUILD = os.path.join(MOD, "build", "ships")
OUR_MODELS = {
    "smt_ms_sp": ("som_mothership", {}),
    "smt_ms": ("som_mothership", {}),
    "smt_worker": ("som_worker", {}),
    "smt_scout": ("som_recon", {}),
    "smt_acolyte": ("som_acolyte", {}),
    "smt_acv": ("som_acv", {}),
    # its body and its disguises as joints, one shown at a time (tools/overrides/ship/smt_mimic/smt_mimic.madstate)
    "smt_mimic": ("som_mimic", {}),
    "smt_processor": ("som_processor", {}),
    "smt_rammingfrigate": ("som_rammingfrigate", {}),
    # its salvage point is Cataclysm's Tow0 (geo2dae.py: the .shp's DPT_SalvageLatch points)
    "cat_messagepod": ("cat_messagepod", {}),
}
# Weapons on our models' gun joints (Cataclysm's guns, GUN<n> in the .shp's order; tools/build_ship.sh): stock HWRM
# weapons, their damage set to Cataclysm's by tools/make_damage.py. The Kuun-Lan's are patch_ms_sp's, the Acolyte's
# missile launchers patch_acolyte's; the Worker, Mimic and Ramming Frigate have no guns in Cataclysm.
OUR_WEAPONS = {
    "smt_scout": [("HW1_Scout", "Weapon_GUN0"), ("Hgn_SmallEMP", "Weapon_GUN0")],
    "smt_acolyte": [("HW1_Interceptor", "Weapon_GUN0"), ("HW1_Interceptor", "Weapon_GUN1")],
    "smt_acv": [("HW1_Interceptor", f"Weapon_GUN{k}") for k in range(4)] + [("Hgn_SmallEMP", "Weapon_GUN0")],
    "smt_processor": [("Hgn_MSHullDefenseGun", f"Weapon_GUN{k}") for k in range(4)],
}
# The Kuun-Lan moves as it did before the rebuild (user: more agile than HW1's Mothership)
KUUNLAN_MOVE = {"mass": 2000, "thrusterMaxSpeed": 60, "mainEngineMaxSpeed": 60, "rotationMaxSpeed": 8,
                "thrusterAccelTime": 6, "thrusterBrakeTime": 2, "mainEngineAccelTime": 6, "mainEngineBrakeTime": 2,
                "rotationAccelTime": 0.5, "rotationBrakeTime": 0.3, "accelerationAngle": 30, "maxBankingAmount": 10,
                "descendPitch": 10, "slideMoveRange": 350}

# Our own versions of installed files (tracked here; the data/ copies are git-ignored): tools/overrides/<data path>.
# Only for ships on our models: a stand-in keeps its template's files.
OVERRIDES = os.path.join(MOD, "tools", "overrides")


# Speeds: Cataclysm's .shp maxvelocity converted the way Gearbox converted the matching HW1 class for HWRM (their
# HWRM mainEngineMaxSpeed / HW1 maxvelocity: kus_scout 490/1000, kus_interceptor 487/875, kus_resourcecollector
# 110/325). Their setups ran 1.3-1.9x Cataclysm's pace for some ships (user: distances felt shorter than the
# original). Thrusters keep their ratio to the main engine. Not the Kuun-Lan: it is more agile than HW1's
# Mothership (user), so it keeps their speed.
SPEED_CLASS = {"scout": 490 / 1000, "interceptor": 487 / 875, "collector": 110 / 325,
               "frigate": 206 / 325}   # (tai_assaultfrigate 206 / tStandardFrigate 325)
# The Worker on Gearbox's collector ratio (144); the scout ratio (208, user: 144 was a bit slow) had it outpace the
# Processor (user, Mission01), so back to 144. (The original's Worker runs at 0.52x an Acolyte, 1.7x the Processor.)
SPEEDS = {"smt_scout": ("srecon", "scout"), "smt_acolyte": ("sacolyte", "interceptor"),
          "smt_worker": ("sworker", "collector"), "smt_acv": ("sacv", "interceptor"), "smt_mimic": ("smimic", "interceptor"),
          "smt_rammingfrigate": ("srammingfrigate", "frigate"), "smt_processor": ("sprocessor", "scout")}   # (the Workers' ratio, user)


# Harvesting: Cataclysm's .shp harvestRate (an asteroid eaten every n + 1 frames, 16 frames a second) x harvestAmount
# RUs, and resourcesAtOneTime per trip, into HWRM's Harvest ability (enabled, capacity, RUs a second, distance).
# Gearbox's HW1 collectors take 10 RUs a second, 20x Cataclysm's 0.5: Mission01's Taiidan resourcers stripped their
# field early and went into parade with their carrier (user: their field should last).
HARVEST = {"tai_resourcecollector": "race_taidan/tresourcecollector"}   # (Cataclysm has no Kushan collector)


def harvest_rate(ship, cat):
    path = os.path.join(DATA, "ship", ship, ship + ".ship")
    shp = os.path.join(r"C:\Modding\Cataclysm-decomp\extracted\big", *cat.split("/")) + ".shp"
    if not os.path.exists(path) or not os.path.exists(shp):
        return
    v = {}
    for line in open(shp, encoding="latin-1"):
        m = re.match(r"\s*(harvestRate|harvestAmount|resourcesAtOneTime)\s+([\d.]+)", line)
        if m:
            v[m.group(1)] = float(m.group(2))
    rate = 16 / (v.get("harvestRate", 31) + 1) * v.get("harvestAmount", 1)
    cap = v.get("resourcesAtOneTime", 250)
    text = open(path, encoding="latin-1").read()
    text, n = re.subn(r'addAbility\(NewShipType,\s*"Harvest",\s*1,\s*[\d.]+,\s*[\d.]+,\s*([\d.]+)\);',
                      lambda m: f'addAbility(NewShipType,"Harvest",1,{cap:g},{rate:g},{m.group(1)});   '
                                f'-- Cataclysm-HWRM: Cataclysm\'s pace ({cat})', text, count=1)
    if n:
        open(path, "w", encoding="latin-1", newline="").write(text)
        print(f"  {ship}: harvests {rate:g} RU/s, {cap:g} a trip (Cataclysm's)")


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


# A resource ship's cargo as a dust cloud where it dies (Cataclysm FUN_00548e00: class Resource with RU aboard ->
# dust cloud 0 worth its RU x 1.0). HWRM's collectors already do it (NOTES.md "Resource ships' cargo on death":
# SpawnDustCloudOnDeath's held RU weight), but with type DustCloud_0, selectionPriority 0 and no blobRadius: it
# could not be clicked, so not harvested (user). HW1's dust cloud 0 (stock Homeworld2 DustCloud0_hw1: priority 35,
# blob 100, HW1's soft dots) is the one Cataclysm drops.
CARGO_CLOUD_TYPE = "cat_cargocloud"
# DustCloud0_hw1 is harvestable (resourceValue) but a soft dot past 7000 (user: invisible); DustCloud_0 is drawn as a
# mesh to 25000 but worth nothing. Ours: DustCloud0_hw1's model and resource fields, DustCloud_0's drawing.
CLOUD_SRC = r"C:\Modding\Cataclysm-decomp\reference\hwrm\Homeworld2\resource\dustcloud"


def make_cargo_cloud():
    out = os.path.join(DATA, "resource", "dustcloud", CARGO_CLOUD_TYPE)
    os.makedirs(out, exist_ok=True)
    # DustCloud0_hw1's model: DustCloud_0's mesh plus the Latch1 joints a Worker harvests at (without them: not
    # harvestable, user)
    shutil.copyfile(os.path.join(CLOUD_SRC, "dustcloud0_hw1", "dustcloud0_hw1.hod"),
                    os.path.join(out, CARGO_CLOUD_TYPE + ".hod"))
    text = open(os.path.join(CLOUD_SRC, "dustcloud_0", "dustcloud_0.resource"), encoding="latin-1").read().rstrip()
    extra = [l for l in open(os.path.join(CLOUD_SRC, "dustcloud0_hw1", "dustcloud0_hw1.resource"), encoding="latin-1")
             if re.match(r"NewResourceType\.(resourceValue|blobRadius)\s*=", l)]
    text += "\n-- Cataclysm-HWRM: resourcers' cargo (install_base.py make_cargo_cloud): DustCloud0_hw1's resource fields\n"
    open(os.path.join(out, CARGO_CLOUD_TYPE + ".resource"), "w", encoding="latin-1", newline="\n").write(
        text + "".join(extra))
    # and a .dustcloud like DustCloud_0's, which has one (user: HWRM's look, not the HW1 cloud's)
    dc = open(os.path.join(CLOUD_SRC, "dustcloud_0", "dustcloud_0.dustcloud"), encoding="latin-1").read().rstrip()
    open(os.path.join(out, CARGO_CLOUD_TYPE + ".dustcloud"), "w", encoding="latin-1", newline="\n").write(
        dc + "\n-- Cataclysm-HWRM: resourcers' cargo (install_base.py make_cargo_cloud)\n" + "".join(extra))


# Turret turn speeds from Cataclysm's .shp (maxanglespeed / maxdeclinationspeed, degrees/s) for the weapons whose
# directory names contain the key (their per-ship copies too: cat_<ship>_<weapon>). HWRM's HW1 heavy cruiser guns turn
# at 33 / 20, Cataclysm's tHeavyCruiser's all ten at 360 / 360: on a moving cruiser HWRM's lagged and snapped (user;
# range test: any moving cruiser, sound or crippled). StartWeaponConfig arguments 19 and 20 (after NewWeaponType).
TURRET_SPEEDS = {"tai_cruisergun": (360, 360), "tai_cruiserion": (360, 360)}
# and HWRM's slow-down once on target (argument 21: speed x this when pointing at it; 0.1 kept them snapping, user):
# HW1 has none (Gun.c: the turn speed is the aim error x angletracking, capped at the maximum)
TURRET_ON_TARGET = 1


def patch_turret_speeds():
    done = []
    for w in sorted(os.listdir(os.path.join(DATA, "weapon"))):
        speeds = next((v for k, v in TURRET_SPEEDS.items() if k in w.lower()), None)
        path = os.path.join(DATA, "weapon", w, w + ".wepn")
        if speeds is None or not os.path.exists(path):
            continue
        text = open(path, encoding="latin-1").read()
        m = re.search(r"StartWeaponConfig\(([^)]*)\)", text)
        if not m:
            continue
        args = [a.strip() for a in m.group(1).split(",")]
        if len(args) < 21:
            continue
        args[19], args[20], args[21] = str(speeds[0]), str(speeds[1]), str(TURRET_ON_TARGET)
        new = text[:m.start(1)] + ",".join(args) + text[m.end(1):]
        if new != text:
            open(path, "w", encoding="latin-1", newline="").write(new)
            done.append(w)
    print(f"  Cataclysm turret speeds on {len(done)} weapons: {', '.join(done)}")


def patch_cargo_clouds():
    make_cargo_cloud()
    done = []
    for ship in sorted(os.listdir(os.path.join(DATA, "ship"))):
        path = os.path.join(DATA, "ship", ship, ship + ".ship")
        if not os.path.exists(path):
            continue
        text = open(path, encoding="latin-1").read()
        new = re.sub(r'^([ \t]*SpawnDustCloudOnDeath\(NewShipType,\s*)"(?:DustCloud_0|DustCloud0_hw1)"', rf'\1"{CARGO_CLOUD_TYPE}"', text,
                     flags=re.M)
        if new != text:
            open(path, "w", encoding="latin-1", newline="").write(new)
            done.append(ship)
    print(f"  cargo dust clouds ({CARGO_CLOUD_TYPE}) on {len(done)} ships: {', '.join(done)}")


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
    # the template's .madstate drives the template's animations, which our model doesn't have (ours, where there
    # is one: tools/overrides)
    if os.path.exists(os.path.join(folder, ship + ".madstate")) and f"ship/{ship}/{ship}.madstate" not in OURS:
        os.remove(os.path.join(folder, ship + ".madstate"))
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
    # a template that loads another type's model (LoadSharedModel: the salvageable cryo tray uses Kus_CryoTray's) loads
    # its own, ours (user: the message pod still showed the cryo tray)
    text = re.sub(r'^([ \t]*)LoadSharedModel\(NewShipType,\s*"[^"]*"\);', r"\1LoadModel(NewShipType,1);", text,
                  flags=re.M)
    # our models have one level of detail: their LOD switches (made for theirs) left ours invisible past the first
    # (user: the Mimic vanished zooming out)
    text = re.sub(r'^\s*NewShipType(\.|\[")(upLOD|downLOD)\b.*\n', "", text, flags=re.M)
    text = re.sub(r'^(\s*NewShipType(?:\.|\[")minLOD(?:"\])?\s*=\s*)[\d.]+', r"\g<1>1", text, flags=re.M)

    # the template's guns give way to ours (its weapon joints and turrets aren't on our model)
    text = re.sub(r'^(StartShipWeaponConfig\(|StartShipHardPointConfig\(NewShipType,\s*"[^"]*",\s*"[^"]*",\s*"Weapon")',
                  r"-- Cataclysm-HWRM (the template's gun): \1", text, flags=re.M)
    if OUR_WEAPONS.get(ship):
        text = after_load_model(text, "-- Cataclysm-HWRM: Cataclysm's guns on our model (OUR_WEAPONS)\n" + "\n".join(
            f'StartShipWeaponConfig(NewShipType,"{w}","{j}","{j}");' for w, j in OUR_WEAPONS[ship]))

    def drop(m):
        joint = m.group(2)
        return m.group(0) if joint.encode() in model else "-- Cataclysm-HWRM (no joint in our model): " + m.group(0)
    text = re.sub(r'^(Start(?:Ship)?(?:HardPoint|Weapon)Config\(NewShipType,\s*"[^"]*",\s*"([^"]*)").*$', drop,
                  text, flags=re.M)
    # the template's effects on our joints (stock names its guns Weapon_Gun<n>, ours Weapon_GUN<n>)
    ev = os.path.join(folder, ship + ".events")
    if os.path.exists(ev):
        etext = open(ev, encoding="latin-1").read()
        open(ev, "w", encoding="latin-1", newline="").write(re.sub(r"\bWeapon_Gun(\d+)", r"Weapon_GUN\1", etext))

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
    # ...and every nozzle of ours gets one: the template's (its HW1 Scout trails one nozzle, our Recon has two: user)
    m = re.search(r'^setEngineTrail\(NewShipType,\s*\d+(.*)$', text, flags=re.M)
    if m:
        extra = [f"setEngineTrail(NewShipType,{k}{m.group(1)}" for k in range(nozzles) if k not in seen]
        if extra:
            text = text.rstrip("\n") + "\n-- Cataclysm-HWRM: the template's trail on our other nozzles\n" + "\n".join(extra) + "\n"

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
        # the race's own announcer, as theirs for the Vaygr / Taiidan: Somtaaw -> "cat_fleet" (player:racelist.lua written at mission start, cataclysmkas.lua)
        taiidan = 'elseif (Race_ID[currentRace] == "Taiidan" or Race_ID[currentRace] == "2x_Taiidan") then\n\t\treturn NameEmperor'
        if fn == "commands.lua":
            if taiidan not in text:
                raise SystemExit(f"{src}: raceHelper changed; patch_speech_logic needs updating")
            text = text.replace(taiidan, taiidan + '\n\telseif (Race_ID[currentRace] == "Somtaaw") then\n\t\treturn "cat_fleet"', 1)
        if fn == "chatter.lua":
            # the repair order's line was a speechFile entry, which the engine plays itself in the stock support pilot
            # voice (user: the repair lines were still HW2's): now a handler routed like the others (catspeech.lua
            # CatSpeech_CommandRepair; Cataclysm's "Repairs underway.", 146)
            old = ('speechFile = "COMMAND_STARTEDREPAIRS",\n\t\tactor = { NameSupportPilot, NumSupportPilots }')
            text = text.replace("\r\n", "\n")
            if old not in text:
                raise SystemExit(f"{src}: CE_CMD_REPAIR changed; patch_speech_logic needs updating")
            text = text.replace(old, 'customFnc = {"CatSpeech_CommandRepair", F_SS}', 1)
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
    OURS.update(ours)
    # our races (stock Kushan / Taiidan race folders) and ships (stock HW1 templates)
    for race, args in RACES.items():
        copied += gen_race(race, *args)
    for ship, template in TEMPLATES.items():
        copied += gen_ship(ship, template)
    set_names()
    for ship, (model, joints) in OUR_MODELS.items():
        use_our_model(ship, model, joints)
        copied += [f"ship/{ship}/{ship}{ext}" for ext in (".hod", ".mad")
                   if os.path.exists(os.path.join(DATA, "ship", ship, ship + ext))]
    for rel, fn in PATCHES.items():
        p = os.path.join(DATA, rel)
        t = open(p, encoding="latin-1").read()
        open(p, "w", encoding="latin-1", newline="\n").write(fn(t))
    for rel in copied:
        if rel.endswith(".wepn"):
            p = os.path.join(DATA, rel)
            t = open(p, encoding="latin-1").read()
            open(p, "w", encoding="latin-1", newline="").write(patch_hw1_armour(t))
    for ship, (cat, cls) in SPEEDS.items():
        set_speed(ship, cat, cls)
    set_costs()
    copied += set_support_units()
    patch_cargo_clouds()
    set_trails()
    for root, _, files in os.walk(OVERRIDES):   # our own versions of installed files (.events / .madstate)
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), OVERRIDES)
            parts = rel.replace("\\", "/").split("/")
            if parts[0] == "ship" and parts[1] not in OUR_MODELS:
                continue   # (a stand-in keeps its template's)
            shutil.copyfile(os.path.join(root, fn), os.path.join(DATA, rel))
            if "/".join(parts).lower() not in OURS:
                copied.append("/".join(parts))
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
        n = len(CAN_ATTACK.findall(text))
        assert n == 1, f"smt_mimic: {n} CanAttack statements"
        text = CAN_ATTACK.sub(lambda m: MIMIC_ATTACK, text)
        open(mimic, "w", encoding="latin-1", newline="").write(text)
    ship_variants.write_lua()
    # the Mimic's transformation effects as events on the Mimic and its disguises (tools/make_mimicfx.py)
    import make_mimicfx
    make_mimicfx.patch_all_events()
    # the Processor's repair beam cones as events on its beam turret joints (tools/make_procbeam.py)
    import make_procbeam
    make_procbeam.patch_events()
    # Cataclysm's ship rules (experience, damage slowing ships, Acolyte link) on every ship the campaign uses
    copied += make_shipcode.install()
    # Cataclysm's health and weapon damage (user: all ships, Cataclysm's scale 1:1)
    copied += make_damage.apply(make_damage.plan())
    # damage-factor ship copies (<ship>_d<pct>: Cataclysm's low kasfShipsSetDamageFactor; tools/make_variants.py)
    import make_variants
    copied += make_variants.install()
    # patch_turret_speeds()   # (off: no change on moving ships, user; HWRM's stock tracking is the same on all of them)
    # ships on stock HW1 death effects (tools/make_events.py) last as long as the stock ship (sobDieTime): theirs took
    # the Ramming Frigate at 1 s, before its death blasts at ~1.3 s (user: no proper explosion), the fighters at 0.1
    import make_events
    for ship, src in make_events.SHIPS.items():
        stock = open(os.path.join(make_events.STOCK, src, src + ".ship"), encoding="latin-1").read()
        want = float(re.search(r"sobDieTime\s*=\s*([\d.]+)", stock).group(1))
        path = os.path.join(DATA, "ship", ship, ship + ".ship")
        if not os.path.exists(path):
            continue
        text = open(path, encoding="latin-1").read()
        m = re.search(r'(NewShipType(?:\["sobDieTime"\]|\.sobDieTime)\s*=\s*)([\d.]+)', text)
        if m and float(m.group(2)) < want:
            text = text[:m.start(2)] + f"{want:g}" + text[m.end(2):]
            open(path, "w", encoding="latin-1", newline="").write(text)
            print(f"  {ship}: sobDieTime {m.group(2)} -> {want:g} (stock {src}'s, for its death effects)")
    # and any Somtaaw ship outlives its own last death blast (+0.5 s): theirs took the Processor at 1 s (its blasts
    # to 3.4 s, user: no second explosion), the Mimic at 0.1
    for d in sorted(os.listdir(os.path.join(DATA, "ship"))):
        ev, path = (os.path.join(DATA, "ship", d, d + x) for x in (".events", ".ship"))
        if not (d.startswith("smt_") and os.path.exists(ev) and os.path.exists(path)):
            continue
        anims, events = make_events.sections(open(ev, encoding="latin-1").read())
        length = next((float(re.search(r"length\s*=\s*([\d.]+)", e).group(1)) for _, e in anims
                       if (make_events.anim_name(e) or "").lower() == "death"), None)
        times = [float(make_events.field(e, "animtime")) for _, e in events
                 if (make_events.field(e, "anim") or "").lower() == "death" and make_events.field(e, "animtime")]
        text = open(path, encoding="latin-1").read()
        m = re.search(r'(NewShipType(?:\["sobDieTime"\]|\.sobDieTime)\s*=\s*)([\d.]+)', text)
        if not (length and times and m):
            continue
        want = round(max(times) * length + 0.5, 1)
        if float(m.group(2)) < max(times) * length:
            text = text[:m.start(2)] + f"{want:g}" + text[m.end(2):]
            open(path, "w", encoding="latin-1", newline="").write(text)
            print(f"  {d}: sobDieTime {m.group(2)} -> {want:g} (its last death blast {max(times) * length:.2f} s in)")
    # the HW1 resource collectors' harvesting at Cataclysm's pace (after make_shipcode copies their .ship)
    for ship, cat in HARVEST.items():
        harvest_rate(ship, cat)
    # every Somtaaw ship repairable (Cataclysm's repair beams take anything; HWRM repairs only ships with
    # CanBeRepaired: theirs left out the fighters, the ACV...: user, the Processor's ordered repair did nothing).
    # HWRM repairs only at RepCap latch points ("marked as repairable ... but has no repair points!"): our models
    # carry RepairPoint0-3 (geo2dae.py; one repairer per point); every RepairPointN in a ship's model is declared.
    # Ships with their own (not ours) active RepCap list keep it.
    for d in sorted(os.listdir(os.path.join(DATA, "ship"))):
        path = os.path.join(DATA, "ship", d, d + ".ship")
        if not (d.startswith("smt_") and os.path.exists(path)):
            continue
        text = open(path, encoding="latin-1").read()
        if re.search(r'^\s*addAbility\(NewShipType,\s*"CanBeRepaired",\s*"RepCap"\);\s*$', text, re.M) and \
                re.search(r'^\s*loadLatchPointList\(NewShipType,\s*"RepCap"(?![^\n]*Cataclysm-HWRM)', text, re.M):
            continue
        hod = os.path.join(DATA, "ship", d, d + ".hod")
        data = open(hod, "rb").read() if os.path.exists(hod) else b""
        points = sorted({int(n) for n in re.findall(rb"RepairPoint(\d+)(?![A-Za-z\d])", data)})
        text = re.sub(r'^[ \t]*addAbility\(NewShipType,\s*"CanBeRepaired"[^\n]*\n?', "", text, flags=re.M)
        text = re.sub(r'^[ \t]*loadLatchPointList\(NewShipType,\s*"RepCap"[^\n]*\n?', "", text, flags=re.M)
        if points:
            add = ('addAbility(NewShipType, "CanBeRepaired", "RepCap");   -- Cataclysm-HWRM\n'
                   'loadLatchPointList(NewShipType, "RepCap", '
                   + ", ".join(f'"RepairPoint{n}"' for n in points) + ');   -- Cataclysm-HWRM\n')
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
        print(f"  removed {removed} files no longer installed")
    with open(manifest, "w", newline="\n") as f:
        f.write("\n".join(copied) + "\n")
    with open(os.path.join(DATA, ".gitignore"), "w", newline="\n") as f:
        f.write("# Generated by tools/install_base.py: installed stock, Players Patch and generated files (not committed)\n")
        f.write("\n".join("/" + re.sub(r"([\[\]*?])", r"\\\1", r) for r in copied) + "\n")
    print(f"installed {len(copied)} files into data/ ({len(TEMPLATES)} ships from stock templates, {len(OUR_MODELS)} on our models)")


if __name__ == "__main__":
    main()
