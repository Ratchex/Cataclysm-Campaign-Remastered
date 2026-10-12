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
# (ship, percent): TEST first, a Taiidan ion frigate at 10 % (do its beams still fire at low weapon damage?)
VARIANTS = [("tai_ioncannonfrigate", 10)]


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
    for w, via in make_damage.ship_weapons(ship):
        if via != "ship":
            print(f"  variants: {copy}: {w} is on subsystem {via}: not scaled (only ship weapons so far)")
            continue
        src = make_damage.find("weapon", w, ".wepn")
        if not src:
            continue
        name = f"cat_{copy}_{w}".lower()
        wt = open(src, encoding="latin-1").read()
        wt = make_damage.HIT.sub(lambda m: f"{m.group(1)}{float(m.group(2)) * pct / 100:.4g}{m.group(3)}"
                                           f"{float(m.group(4)) * pct / 100:.4g}", wt)
        written.append(make_damage.write_weapon(name, wt))
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
    return out


if __name__ == "__main__":
    install()
