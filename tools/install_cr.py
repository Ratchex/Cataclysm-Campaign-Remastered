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
import make_shipcode  # noqa: E402

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
KEEP_PREFIX = ("ui/tacticalicons/",)
SKIP_SUFFIX = (".swp", ".bak")

RESEARCH_HP = ('StartShipHardPointConfig(NewShipType,"Research Module","Hardpoint_GravGenerator","System","Innate",'
               '"Damageable","HW1_ResearchModule","","","","","","","","");')


def patch_ms_sp(text):
    """Cataclysm researches without building a research module: innate HW1 research module on the unused
    Hardpoint_GravGenerator of their single-player Kuun-Lan (after LoadModel, as hardpoints must be; their
    multiplayer model, see COPIES, has no Hardpoint_Generic5-7)."""
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


def patch_worker(text):
    """Cataclysm's Worker repairs; their RepairCommand was disabled. (How far off it harvests is set by the
    model's LatchOrientation joint, not by the Harvest ability: tools/build_ship.sh --latch.)"""
    return re.sub(r'(addAbility\(NewShipType,\s*"RepairCommand",\s*)0,', r'\g<1>1,', text)


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
}


# Effects for ships whose own .events have none (their Acolyte's is empty: no muzzle flash): a stock HWRM ship's,
# its joint/animation names mapped to ours
HW1SHIPS = r"C:\Modding\Cataclysm-decomp\reference\hwrm\HW1Ships\ship"
OUR_EVENTS = {
    "smt_acolyte": (os.path.join(HW1SHIPS, "kus_interceptor", "kus_interceptor.events"),
                    {"Weapon_Gun0": "Weapon_GUN0", "Weapon_Gun1": "Weapon_GUN1"}),
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
SPEED_CLASS = {"scout": 490 / 1000, "interceptor": 487 / 875, "collector": 110 / 325}
# The Worker on Gearbox's collector ratio (144) was a bit slow (user): the scout ratio (208); the original's Worker
# runs at 0.52x an Acolyte, the interceptor ratio would be 237.
SPEEDS = {"smt_scout": ("srecon", "scout"), "smt_acolyte": ("sacolyte", "interceptor"),
          "smt_worker": ("sworker", "scout")}


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


def set_speed(ship, cat, cls):
    shp = os.path.join(r"C:\Modding\Cataclysm-decomp\extracted\big\race_sect", cat + ".shp")
    v = next(float(l.split()[1]) for l in open(shp, encoding="latin-1") if l.lower().startswith("maxvelocity"))
    main = round(v * SPEED_CLASS[cls])
    path = os.path.join(DATA, "ship", ship, ship + ".ship")
    text = open(path, encoding="latin-1").read()
    num = lambda key: eval(re.search(r"NewShipType\.%s\s*=\s*([\d.*]+)" % key, text).group(1))  # e.g. 350*1.4
    thr = round(main * num("thrusterMaxSpeed") / num("mainEngineMaxSpeed"))
    text = re.sub(r"(NewShipType\.mainEngineMaxSpeed\s*=\s*)[\d.*]+", r"\g<1>%d" % main, text, count=1)
    text = re.sub(r"(NewShipType\.thrusterMaxSpeed\s*=\s*)[\d.*]+", r"\g<1>%d" % thr, text, count=1)
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
    for root, _, files in os.walk(OVERRIDES):   # our own versions of their files (.events / .madstate)
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), OVERRIDES)
            shutil.copyfile(os.path.join(root, fn), os.path.join(DATA, rel))
    for rel in copied:
        if rel.endswith(".events"):
            fix_event_markers(os.path.join(DATA, rel))
    # Cataclysm's ship rules (experience, damage slowing ships, Acolyte link) on every ship the campaign uses
    copied += make_shipcode.install()
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
