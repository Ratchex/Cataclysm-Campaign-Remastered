"""Install Cataclysm Remastered (workshop 2195601016, "Beast Update" v2.1) as the mod's base data layer.

Copies Cataclysm-decomp/reference/cr_beast (extracted with Cataclysm-decomp/tools/hw2big.py) into data/, except their
campaign and junk, then applies PATCHES (small edits so their ships work for the Cataclysm campaign). The copied
files are listed in data/cr_files.txt and git-ignored through data/.gitignore (their assets are not ours to commit;
permission is needed before any public release).

Usage: install_cr.py
"""
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_modules  # noqa: E402

MOD =os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = r"C:\Modding\Cataclysm-decomp\reference\cr_beast"
DATA = os.path.join(MOD, "data")

SKIP_PREFIX = ("leveldata/campaign/beastwar", "config_old.txt", "keeper.txt")
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


def patch_families(text):
    """Their Kuun-Lan builds families that the Beast Update's familylist lacks (missing family = log error)."""
    text = text.replace("\r\n", "\n")
    add = "".join('\t{\n\t\tname = "%s",\n\t},\n' % f for f in MISSING_FAMILIES if '"%s"' % f not in text)
    return text.replace("buildFamily =\n{\n", "buildFamily =\n{\n" + add, 1)


def patch_race(text):
    """Single-player rules only pass races tagged race_gbx_hwrmc ("Unknown Race [Somtaaw]" otherwise)."""
    return re.sub(r'^(Tags = "(?:(?!race_gbx_hwrmc)[^"])*)"', r'\1,race_gbx_hwrmc"', text, count=1, flags=re.M)


PATCHES = {
    "ship/smt_ms_sp/smt_ms_sp.ship": patch_ms_sp,
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


def use_our_events(ship, src, names):
    text = open(src, encoding="latin-1").read()
    for theirs, mine in names.items():
        text = text.replace(theirs, mine)
    with open(os.path.join(DATA, "ship", ship, ship + ".events"), "w", encoding="latin-1", newline="") as f:
        f.write(text)


def use_our_model(ship, ours, joints):
    folder = os.path.join(DATA, "ship", ship)
    shutil.copyfile(os.path.join(BUILD, ours, ours + ".hod"), os.path.join(folder, ship + ".hod"))
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
    for root, _, files in os.walk(SRC):
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), SRC).replace("\\", "/")
            low = rel.lower()
            if low.startswith(SKIP_PREFIX) or low.endswith(SKIP_SUFFIX):
                continue
            dst = os.path.join(DATA, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(root, fn), dst)
            copied.append(rel)
    for rel, src in COPIES.items():
        shutil.copyfile(os.path.join(SRC, src), os.path.join(DATA, rel))
    for rel, fn in PATCHES.items():
        p = os.path.join(DATA, rel)
        t = open(p, encoding="latin-1").read()
        open(p, "w", encoding="latin-1", newline="\n").write(fn(t))
    for ship, (ours, joints) in OUR_MODELS.items():
        use_our_model(ship, ours, joints)
    for ship, (src, names) in OUR_EVENTS.items():
        use_our_events(ship, src, names)
    for rel in copied:
        if rel.endswith(".events"):
            fix_event_markers(os.path.join(DATA, rel))
    copied.sort()
    with open(os.path.join(DATA, "cr_files.txt"), "w", newline="\n") as f:
        f.write("\n".join(copied) + "\n")
    with open(os.path.join(DATA, ".gitignore"), "w", newline="\n") as f:
        f.write("# Generated by tools/install_cr.py: Cataclysm Remastered files (not committed)\n")
        f.write("\n".join("/" + re.sub(r"([\[\]*?])", r"\\\1", r) for r in copied) + "\n")
    print(f"installed {len(copied)} Cataclysm Remastered files into data/ ({len(PATCHES)} patched, {len(COPIES)} replaced, {len(OUR_MODELS)} on our models)")


if __name__ == "__main__":
    main()
