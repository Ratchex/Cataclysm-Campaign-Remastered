"""Cutscene-only ship types (used by tools/nis2hwrm.py NIS_TYPES), built into data/ by tools/install_cr.py.

tai_missiledestroyer_nis: the Taiidan missile destroyer whose launchers fire tai_nismissile, a Taiidan missile
that turns and speeds up at once. HWRM's (a 0.75 s engine and 1 s turn ramp) left the fixed launchers' missiles
swinging out in a big loop before they came round to the target; in Cataclysm's nislet01 they fly straight in
(user). Gameplay's missile destroyers keep the stock missile.

install() returns the data/ paths written (install_cr.py's manifest: generated, not committed).
"""
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
DATA = os.path.join(MOD, "data")
STOCK_HW1 = r"C:\Modding\Cataclysm-decomp\reference\hwrm\HW1Ships\ship"

SHIP, BASE = "tai_missiledestroyer_nis", "tai_missiledestroyer"
LAUNCHERS = ("Tai_DestroyerLauncher",)   # (the volley tubes fire special attacks only)
WEAPON, MISSILE, BASE_WEAPON, BASE_MISSILE = "cat_nis_tailauncher", "tai_nismissile", "tai_destroyerlauncher", "tai_missile"
# the missile: straight at its target from launch
# (each brake time below its accel time, as HWRM requires of ships and missiles)
MISSILE_TUNING = {"rotationMaxSpeed": 1000, "rotationAccelTime": 0.1, "rotationBrakeTime": 0.05,
                  "mainEngineAccelTime": 0.15, "mainEngineBrakeTime": 0.1,
                  "thrusterAccelTime": 0.15, "thrusterBrakeTime": 0.1}


def write(rel, data):
    path = os.path.join(DATA, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(data)
    return rel.replace("\\", "/")


def install():
    written = []
    # the ship: ours (data/) or the stock HW1 one, its model and events from stock HW1
    for ext in (".ship", ".lua", ".hod", ".events", ".mad", ".madstate"):
        src = next((p for p in (os.path.join(DATA, "ship", BASE, BASE + ext), os.path.join(STOCK_HW1, BASE, BASE + ext))
                    if os.path.exists(p)), None)
        if src is None:
            continue
        data = open(src, "rb").read()
        if ext == ".ship":
            text = data.decode("latin-1")
            for w in LAUNCHERS:
                text, n = re.subn(r'(StartShipWeaponConfig\(NewShipType,\s*")' + re.escape(w) + '"', r"\g<1>" + WEAPON + '"',
                                  text)
                assert n, f"{BASE}: no {w}"
            data = text.encode("latin-1")
        elif ext == ".madstate":
            data = re.sub(r"\b" + BASE.upper() + "_", SHIP.upper() + "_", data.decode("latin-1")).encode("latin-1")
        written.append(write(f"ship/{SHIP}/{SHIP}{ext}", data))
    # its launcher: the stock one firing our missile
    text = open(os.path.join(DATA, "weapon", BASE_WEAPON, BASE_WEAPON + ".wepn"), encoding="latin-1").read()
    text, n = re.subn(r'"Missile","Tai_Missile"', f'"Missile","{MISSILE}"', text, count=1)
    assert n, f"{BASE_WEAPON}: no Tai_Missile"
    written.append(write(f"weapon/{WEAPON}/{WEAPON}.wepn", text.encode("latin-1")))
    # the missile: ours (data/) or the stock one; its model only in stock (without it its engine trail read a null
    # model: access violation in EngineTrailStatic::getTweaks)
    files = {}
    for d in (os.path.join(STOCK_HW2, "missile", BASE_MISSILE), os.path.join(DATA, "missile", BASE_MISSILE)):
        for fn in os.listdir(d) if os.path.isdir(d) else []:
            files[fn.lower()] = os.path.join(d, fn)            # data/'s copies over stock's
    assert BASE_MISSILE + ".hod" in files, f"{BASE_MISSILE}: no model"
    for fn, path in sorted(files.items()):
        data = open(path, "rb").read()
        if fn.endswith(".miss"):
            text = data.decode("latin-1")
            for k, v in MISSILE_TUNING.items():
                text, n = re.subn(r"(NewShipType\.%s\s*=\s*)[\d.]+" % k, r"\g<1>%g" % v, text)
                assert n, f"{BASE_MISSILE}: no {k}"
            text = re.sub(r'(NewShipType\.weaponName\s*=\s*)"[^"]*"', r'\1"%s"' % WEAPON, text)
            data = text.encode("latin-1")
        written.append(write(f"missile/{MISSILE}/{MISSILE}{os.path.splitext(fn)[1]}", data))
    # ...and its weapon fire (scripts/weaponfire/<name>.wf: hit effects and sounds): a weapon's fire name is looked up
    # there, not among the missiles (without it "Could not load weapon fire" and an access violation)
    wf = open(os.path.join(DATA, "scripts", "weaponfire", BASE_MISSILE, BASE_MISSILE + ".wf"), "rb").read()
    written.append(write(f"scripts/weaponfire/{MISSILE}/{MISSILE}.wf", wf))
    print(f"  cutscene ships: {SHIP} ({MISSILE}: turns at once)")
    return written


if __name__ == "__main__":
    install()
