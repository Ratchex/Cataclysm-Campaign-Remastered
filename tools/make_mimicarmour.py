"""The Mimic's kamikaze through HWRM's own (user: one hit, nothing changed for other ships).

HWRM's kamikaze deals about the rammer's health x 7.5 (a 40-health Mimic: 299 and 306 to frigates in game; the
tuning.lua armour factors go by the target's family). Cataclysm's Mimic deals kamikazeDamage 1000 (tactics.script)
with 40 health. So the Mimic gets health x K (K = 1000 / (7.5 x 40)) and takes K x the damage: its own armour family
MimicArmour, in every weapon's setPenetration at its Unarmoured multiplier (the Mimic's family before) x K, or its
default x K where Unarmoured isn't listed, and in tuning.lua's kamikaze armour factors at Unarmoured's x K (rammed by
others). It dies to the same fire as a 40-health ship; its health bar is a percentage.

Weapons: ours in data/weapon, plus the stock Homeworld 2 ones our ships use (copied in to carry the entry). A few
the ships name are in neither (tai_ioncruiser...): against the Mimic they keep their default.

install() for tools/install_cr.py (after tools/make_damage.py set the Mimic's Cataclysm health).
"""
import glob
import os
import re
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
DATA = os.path.join(MOD, "data")
BIG = r"C:\Modding\Cataclysm-decomp\extracted\big"
STOCK = r"C:\Modding\Cataclysm-decomp\reference\hwrm\Homeworld2\weapon"
CR = r"C:\Modding\Cataclysm-decomp\reference\cr_beast"   # install_cr.py SRC
PP = r"C:\Modding\Cataclysm-decomp\reference\players_patch"   # install_cr.py PP
FAMILY = "MimicArmour"
HWRM_PER_HEALTH = 7.5     # HWRM kamikaze damage per health point of the rammer (in game: 299, 306 from 40)


def cat_value(path, key):
    m = re.search(r"^%s\s+([\d.]+)" % re.escape(key), open(path, encoding="latin-1").read(), re.M | re.I)
    return float(m.group(1))


def factor():
    health = cat_value(os.path.join(BIG, "race_sect", "smimic.shp"), "maxhealth")
    tactics = open(os.path.join(BIG, "tactics.script"), encoding="latin-1").read()
    dmg = float(re.search(r"kamikazeDamage\[sMimic\]\s+([\d.]+)", tactics).group(1))
    return health, dmg / (HWRM_PER_HEALTH * health)


def calls(text, name):
    """(start, end) of each name( ... ) call, end at its closing parenthesis."""
    out = []
    for m in re.finditer(r"\b%s\s*\(" % name, text):
        depth, i = 0, m.end() - 1
        while i < len(text):
            depth += {"(": 1, ")": -1}.get(text[i], 0)
            if depth == 0:
                out.append((m.start(), i))
                break
            i += 1
    return out


def patch_weapon(text, k):
    if FAMILY in text:
        return text
    for start, end in reversed(calls(text, "setPenetration")):
        call = text[start:end]
        args = [a.strip() for a in call[call.index("(") + 1:].split(",")]
        default = float(args[2]) if len(args) > 2 and re.fullmatch(r"[\d.]+", args[2]) else 1.0
        m = re.search(r"(?<![\w])unarmoured\s*=\s*([\d.]+)", call, re.I)
        v = (float(m.group(1)) if m else default) * k
        text = text[:end] + ", { %s = %g }" % (FAMILY, round(v, 4)) + text[end:]
    return text


def used_weapons():
    used = set()
    for f in glob.glob(os.path.join(DATA, "ship", "*", "*.ship")) + glob.glob(os.path.join(DATA, "subsystem", "*", "*.subs")):
        used |= {m.lower() for m in re.findall(r'Start(?:Ship|SubSystem)?WeaponConfig\(\s*\w+\s*,\s*"([^"]+)"',
                                                 open(f, encoding="latin-1").read())}
    return used


def patch_tuning(text, k):
    if FAMILY in text:
        return text
    m = re.search(r'"Unarmoured",\s*([\d.]+)', text[text.index("kamikazeArmourFamilyDamageMultiplier"):])
    v = float(m.group(1)) * k
    return text.replace("kamikazeArmourFamilyDamageMultiplier = {\n",
                        'kamikazeArmourFamilyDamageMultiplier = {\n\t\t{\n\t\t\t"%s",\t-- the Mimic (make_mimicarmour.py)\n'
                        '\t\t\t%g,\n\t\t},\n' % (FAMILY, round(v, 4)), 1)


def patch_families(text):
    if '"%s"' % FAMILY in text:
        return text
    return text.replace("armourFamily =\n{\n", 'armourFamily =\n{\n\t{\n\t\tname = "%s",\n\t},\n' % FAMILY, 1)


def install():
    health, k = factor()
    # the stock weapons our ships use that neither Cataclysm Remastered, the Players Patch nor we provide: copied in every install (and
    # listed for data/.gitignore: game files, not ours to commit)
    theirs = {os.path.basename(d).lower() for src in (CR, PP) for d in glob.glob(os.path.join(src, "weapon", "*"))}
    tracked = set(subprocess.run(["git", "-C", MOD, "ls-files", "data/weapon"], capture_output=True, text=True)
                  .stdout.lower().split())
    ours = {p.split("/")[2] for p in tracked if p.count("/") >= 3}
    copied = []
    for name in sorted(used_weapons() - theirs - ours):
        src = os.path.join(STOCK, name)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(DATA, "weapon", name), dirs_exist_ok=True)
            copied.append(name)
    n = 0
    for f in glob.glob(os.path.join(DATA, "weapon", "*", "*.wepn")):
        t = open(f, encoding="latin-1").read()
        p = patch_weapon(t, k)
        if p != t:
            open(f, "w", encoding="latin-1", newline="").write(p)
            n += 1
    ship = os.path.join(DATA, "ship", "smt_mimic", "smt_mimic.ship")
    t = open(ship, encoding="latin-1").read()
    t = re.sub(r'(NewShipType\["ArmourFamily"\]\s*=\s*)"[^"]*"', r'\g<1>"%s"' % FAMILY, t, count=1)
    t = re.sub(r'(NewShipType(?:\.maxhealth|\["maxhealth"\])\s*=\s*)[\d.]+', r"\g<1>%g" % round(health * k), t, count=1)
    open(ship, "w", encoding="latin-1", newline="").write(t)
    for rel, fn in (("scripts/tuning.lua", lambda s: patch_tuning(s, k)), ("scripts/familylist.lua", patch_families)):
        path = os.path.join(DATA, rel)
        s = open(path, encoding="latin-1").read().replace("\r\n", "\n")
        open(path, "w", encoding="latin-1", newline="").write(fn(s))
    print(f"  Mimic: health {health:g} x {k:.3g} = {round(health * k)}, {FAMILY} in {n} weapons "
          f"({len(copied)} stock weapons copied in)")
    return copied


if __name__ == "__main__":
    install()
