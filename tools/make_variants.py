"""Damage-factor ship copies: <ship>_d<pct>, whose weapons do pct % of the ship's damage (Cataclysm's
kasfShipsSetDamageFactor for factors HWRM's SobGroup_SetDamageMultiplier can't give: it compounds, and ion beams
stop firing below about 0.5, range test 2026-10-12; Mission01's main battle is fought at 10 %, user: weaker weapon
copies). A copy is its own ship type: the .ship (weapons renamed to cat_<copy>_<weapon>, scaled from data/'s already
converted file), its .hod / .events / .madstate / .lua from the first layer that has them. The ship rules treat it as
its base type (shiprules.lua CatShip_Base) and don't apply the mission's factor again.

Usage: python tools/make_variants.py   (run by install_cr.py after make_damage; VARIANTS below)
"""
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_damage  # noqa: E402

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(MOD, "data")
# (ship, percent): Mission01's 10 % teams at their start (its Kushan main guard and the Taiidan they fight; the level
# places these for them: mission2level.py DAMAGE_VARIANTS). The beams fire at 10 % weapon damage (range test).
VARIANTS = [("kus_interceptor", 10), ("kus_ioncannonfrigate", 10), ("kus_multiguncorvette", 10), ("kus_destroyer", 10),
            ("tai_interceptor", 10), ("tai_ioncannonfrigate", 10), ("tai_destroyer", 10), ("tai_defender", 10),
            ("tai_heavycruiser", 10)]


# the models and events of stock HW1 ships are in the HW1Ships layer (not one of make_damage's weapon sources)
MODEL_ROOTS = [os.path.join(make_damage.REF, "hwrm", "HW1Ships"), os.path.join(make_damage.REF, "hwrm", "Homeworld2")]


def find_file(ship, ext):
    for root in [DATA] + make_damage.SOURCES + MODEL_ROOTS:
        p = os.path.join(root, "ship", ship, ship + ext)
        if os.path.exists(p):
            return p
        folder = os.path.join(root, "ship")
        if os.path.isdir(folder):
            d = next((x for x in os.listdir(folder) if x.lower() == ship), None)
            if d:
                f = next((x for x in os.listdir(os.path.join(folder, d)) if x.lower() == ship + ext), None)
                if f:
                    return os.path.join(folder, d, f)
    return None


def scaled_weapon(copy, w, pct):
    """cat_<copy>_<weapon>: the weapon (data/'s converted file) at pct % damage; its name, or None"""
    src = make_damage.find("weapon", w, ".wepn")
    if not src:
        return None, None
    name = f"cat_{copy}_{w}".lower()
    wt = open(src, encoding="latin-1").read()
    wt = make_damage.HIT.sub(lambda m: f"{m.group(1)}{make_damage.num(m.group(2)) * pct / 100:.4g}{m.group(3)}"
                                       f"{make_damage.num(m.group(4)) * pct / 100:.4g}", wt)
    return name, make_damage.write_weapon(name, wt)


def subsystem_copy(sub, pct):
    """<sub>_d<pct>: the innate turret subsystem with its weapons at pct % (its .subs and its other files; some share
    another's model by name, LoadSharedModel, the rest carry their own .hod); its name and the files written"""
    src = make_damage.find("subsystem", sub, ".subs")
    if not src:
        return None, []
    copy = f"{sub}_d{pct}".lower()
    folder = os.path.join(DATA, "subsystem", copy)
    os.makedirs(folder, exist_ok=True)
    written = []
    st = open(src, encoding="latin-1").read()
    for w in sorted(set(re.findall(r'StartSubSystemWeaponConfig\(NewSubSystemType,\s*"([^"]+)"', st))):
        name, path = scaled_weapon(copy, w, pct)
        if name:
            written.append(path)
            st = re.sub(r'(StartSubSystemWeaponConfig\(NewSubSystemType,\s*")' + re.escape(w) + r'(")',
                        lambda m: m.group(1) + name + m.group(2), st)
    with open(os.path.join(folder, copy + ".subs"), "w", encoding="latin-1", newline="") as f:
        f.write(st)
    written.append(f"subsystem/{copy}/{copy}.subs")
    # its other files under the copy's name: .events, and its own model where it has one (.hod, .mad, .madstate;
    # without it the engine crashed loading the weapon config, access violation: the subsystem had no model)
    base = os.path.basename(src)[:-5]
    for ext in (".events", ".hod", ".mad", ".madstate"):
        f = os.path.join(os.path.dirname(src), base + ext)
        if os.path.exists(f):
            shutil.copyfile(f, os.path.join(folder, copy + ext))
            written.append(f"subsystem/{copy}/{copy}{ext}")
    return copy, written


def make(ship, pct):
    copy = f"{ship}_d{pct}"
    folder = os.path.join(DATA, "ship", copy)
    os.makedirs(folder, exist_ok=True)
    written = []
    for ext in (".hod", ".events", ".madstate", ".lua"):
        src = find_file(ship, ext)
        if src:
            shutil.copyfile(src, os.path.join(folder, copy + ext))
            written.append(f"ship/{copy}/{copy}{ext}")
    text = open(os.path.join(DATA, "ship", ship, ship + ".ship"), encoding="latin-1").read()
    done = set()
    for w, via in make_damage.ship_weapons(ship):
        if (w, via) in done:
            continue
        done.add((w, via))
        if via != "ship":                         # an innate turret subsystem: a copy of it with scaled weapons
            sub, files = subsystem_copy(via, pct)
            if sub:
                written += files
                text = re.sub(r'(StartShipHardPointConfig\(NewShipType,[^\n]*?"Innate",\s*"[^"]*",\s*")'
                              + re.escape(via) + r'(")', lambda m: m.group(1) + sub + m.group(2), text, flags=re.I)
            continue
        name, path = scaled_weapon(copy, w, pct)
        if not name:
            continue
        written.append(path)
        text = re.sub(r'(StartShipWeaponConfig\(NewShipType,\s*")' + re.escape(w) + r'(")',
                      lambda m: m.group(1) + name + m.group(2), text, flags=re.I)
    with open(os.path.join(folder, copy + ".ship"), "w", encoding="latin-1", newline="") as f:
        f.write(text)
    written.append(f"ship/{copy}/{copy}.ship")
    print(f"  variants: {copy} ({pct} % damage)")
    return written


def install():
    out = []
    for ship, pct in VARIANTS:
        out += make(ship, pct)
    # their names for the scripts: cataclysmkas.lua (no multiplier on them) and shiprules.lua
    lua = os.path.join(DATA, "scripts", "cataclysm", "variants_damage_gen.lua")
    with open(lua, "w", newline="\n") as f:
        f.write("-- Generated by tools/make_variants.py: damage-factor ship copies, copy -> { base, percent }\n"
                "CatDamageVariants = {\n" + "".join(f'    ["{s}_d{p}"] = {{ "{s}", {p} }},\n' for s, p in VARIANTS)
                + "}\n")
    return out


if __name__ == "__main__":
    install()
