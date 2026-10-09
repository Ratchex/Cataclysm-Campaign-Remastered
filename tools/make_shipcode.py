"""Hook Cataclysm's ship rules (data/scripts/cataclysm/shiprules.lua: pilot experience, damage slowing ships, the
Acolyte -> ACV link) into every ship the campaign uses. Called by install_cr.py after their files are copied.

For each HWRM ship in tools/shipmap.tsv:
  - HW1 ships (kus_*/tai_*) get a copy of the Players Patch's .ship (else stock's) in data/ (returned, so install_cr git-ignores it);
  - the .ship gets our addCustomCode; a ship's own custom code (only one is allowed) is chained: ours calls it at
    its own interval;
  - abilities (Link, Unlink, ...) are command buttons of ours, not CustomCommands: tools/make_abilities.py.
Writes data/scripts/cataclysm/shipcode_gen.lua: per-type entry points, the chained scripts, and each type's
Cataclysm ship class (its .shp shipclass) and display name (english.script).
"""
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_abilities  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
DATA = os.path.join(MOD, "data")
BIG = r"C:\Modding\Cataclysm-decomp\extracted\big"
HW1SHIPS = r"C:\Modding\Cataclysm-decomp\reference\hwrm\HW1Ships\ship"
CR = r"C:\Modding\Cataclysm-decomp\reference\cr_beast"   # install_cr.py SRC
PP = r"C:\Modding\Cataclysm-decomp\reference\players_patch"   # install_cr.py PP
GEN = "data:scripts/cataclysm/shipcode_gen.lua"
MARK = "-- Cataclysm-HWRM ship rules (tools/make_shipcode.py)"
CHAINED = "-- (chained by Cataclysm-HWRM ship rules) "
TICK = 0.5   # shiprules.lua CAT_TICK

CLASSES = ["Mothership", "HeavyCruiser", "Carrier", "Destroyer", "Frigate", "Corvette", "Fighter", "Resource",
           "NonCombat", "MonsterShip", "Component", "Micro"]

CUSTOM = re.compile(r'^[ \t]*addCustomCode\(NewShipType,\s*"([^"]*)",\s*"([^"]*)",\s*"([^"]*)",\s*"([^"]*)",'
                    r'\s*"([^"]*)",\s*"([^"]*)",\s*([\d.]+)\s*\)\s*;?[ \t]*$', re.M)


def ship_info():
    """HWRM type -> (Cataclysm class index, display name), from the first shipmap row with a .shp."""
    names = {}
    for line in open(os.path.join(BIG, "english.script"), encoding="latin-1"):
        m = re.match(r"str(\w+)\s+(.+?)\s*$", line)
        if m:
            names.setdefault(m.group(1).lower(), m.group(2))
    info = {}
    for line in list(open(os.path.join(HERE, "shipmap.tsv"), encoding="utf-8"))[1:]:
        cols = line.rstrip("\n").split("\t")
        if len(cols) < 3 or not cols[2] or cols[2] in info or cols[2].endswith("_dummy"):
            continue
        race, ship, hwrm = cols[0], cols[1], cols[2]
        shp = os.path.join(BIG, "race_" + race.split("_", 1)[1].lower(), ship + ".shp")
        if not os.path.exists(shp):
            continue
        cls = next((l.split()[1] for l in open(shp, encoding="latin-1") if l.lower().startswith("shipclass")), "")
        cls = cls.replace("CLASS_", "")
        if cls in CLASSES:
            name = names.get(ship, ship)   # english.script's are upper case: "ACOLYTE", "ACV"
            info[hwrm] = (CLASSES.index(cls), name if len(name) <= 4 else name.title())
    return info


def lua_name(t):
    return re.sub(r"\W", "_", t)


def hook(ship):
    """Add our custom code to data/ship/<ship>/<ship>.ship; returns the chained custom code (or None)."""
    path = os.path.join(DATA, "ship", ship, ship + ".ship")
    text = open(path, encoding="latin-1").read()
    if MARK in text:
        text = text[:text.index(MARK)].rstrip("\n") + "\n"
    chain = None
    m = CUSTOM.search(text)
    if m:
        chain = m.groups()
        text = text[:m.start()] + CHAINED + m.group(0).lstrip() + text[m.end():]
    else:   # hooked by an earlier run
        m = re.search(re.escape(CHAINED) + r"(.*)$", text, re.M)
        chain = m and CUSTOM.search(m.group(1)).groups()
    interval = min(TICK, float(chain[6])) if chain else TICK
    n = lua_name(ship)
    lines = [MARK,
             f'addCustomCode(NewShipType,"{GEN}","{chain[1] if chain else ""}","CatCreate_{n}","CatUpdate_{n}",'
             f'"CatDestroy_{n}","{chain[5] if chain else ship}",{interval:g})']
    # Cataclysm abilities: one CustomCommand per ability (energy arguments as their Mimic's: an instant command)
    for name, cid, label in make_abilities.for_ship(ship):
        lines.append(f'addAbility(NewShipType,"CustomCommand",1,"{label}",1,0,1000,200,0.25,2,0,"{GEN}",'
                     f'"CatCmd_{name}_Start","CatCmd_{name}_Do","CatCmd_{name}_Finish","{ship}",1.15,{cid},1)')
    open(path, "w", encoding="latin-1", newline="").write(text.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n")
    return chain


def install():
    """Hook every mapped ship; returns the data/ paths of stock ships copied in (rel, '/' separated)."""
    info = ship_info()
    copied, chains = [], {}
    for ship in sorted(info):
        folder = os.path.join(DATA, "ship", ship)
        if not os.path.exists(os.path.join(CR, "ship", ship, ship + ".ship")):
            # not one of Cataclysm Remastered's: a fresh copy of the stock ship, reported every run so install_cr
            # keeps it in its manifest
            stock = os.path.join(PP, "ship", ship, ship + ".ship")   # the Players Patch's (install_cr.py PP)
            if not os.path.exists(stock):
                stock = os.path.join(HW1SHIPS, ship, ship + ".ship")
            if not os.path.exists(stock):
                print(f"  ship rules: no .ship for {ship}, skipped")
                continue
            os.makedirs(folder, exist_ok=True)
            shutil.copyfile(stock, os.path.join(folder, ship + ".ship"))
            copied.append(f"ship/{ship}/{ship}.ship")
        chains[ship] = hook(ship)
    out = ["-- Generated by tools/make_shipcode.py: entry points for data/scripts/cataclysm/shiprules.lua",
           'dofilepath("data:scripts/cataclysm/abilities_gen.lua")',
           'dofilepath("data:scripts/cataclysm/upgrades_gen.lua")',
           'dofilepath("data:scripts/cataclysm/shiprules.lua")', "",
           "CatClass = {"] + [f'    ["{s}"] = {info[s][0]},' for s in sorted(chains)] + ["}",
           "CatName = {"] + [f'    ["{s}"] = "{info[s][1]}",' for s in sorted(chains)] + ["}", ""]
    for name in make_abilities.ABILITIES:
        out.append(f'function CatCmd_{name}_Start(g, p, id) CatAbility_Run("{name}", g, p, id) end')
        out.append(f"function CatCmd_{name}_Do(g, p, id) end")
        out.append(f"function CatCmd_{name}_Finish(g, p, id) end")
    out.append("")
    for path in sorted({c[0] for c in chains.values() if c}):
        out.append(f'dofilepath("{path}")')
    for ship in sorted(chains):
        n, c = lua_name(ship), chains[ship]
        create, update, destroy = (c[2], c[3], c[4]) if c else ("", "", "")
        out.append("")
        out.append(f"function CatCreate_{n}(g, p, id)")
        if create:
            out.append(f"    if {create} then {create}(g, p, id) end")   # nil if their script failed to load
        out.append(f'    CatShip_Create(g, p, id, "{ship}")')
        out.append("end")
        out.append(f"function CatUpdate_{n}(g, p, id)")
        if update:
            # their update at their own interval
            out.append(f"    CatChainTick(g, p, id, {update}, {float(c[6]):g})")
        out.append("    CatShip_Update(g, p, id)")
        out.append("end")
        out.append(f"function CatDestroy_{n}(g, p, id)")
        if destroy:
            out.append(f"    if {destroy} then {destroy}(g, p, id) end")   # nil if their script failed to load
        out.append("    CatShip_Destroy(g, p, id)")
        out.append("end")
    gen = os.path.join(DATA, "scripts", "cataclysm", "shipcode_gen.lua")
    with open(gen, "w", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    print(f"  ship rules on {len(chains)} ships ({sum(1 for c in chains.values() if c)} chained, "
          f"{len(copied)} stock .ship copied)")
    return copied


if __name__ == "__main__":
    install()
