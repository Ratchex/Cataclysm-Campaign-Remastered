"""Effects (.events) for Somtaaw ships whose Cataclysm Remastered file is empty (no death explosion, user: the Recon),
from the nearest stock HW1 ship's, written to tools/overrides/ship/<ship>/<ship>.events (tools/install_base.py installs
them over theirs).

The stock file's death / damage / power-off / radiation effects as they are, except:
- markers: the stock damage markers (top_00, left_01, ...) are on none of these models; each such marker (or list) is
  the ship's own joints spread over its hull (RepairPoint* / CapturePoint*, else Hardpoint_*_Position, else Root),
  one picked at random by the engine as with the stock lists
- weapons: the stock Weapon_Gun<n> muzzle flashes become ones on our mounts (the .ship's StartShipWeaponConfig
  hardpoints, at <mount>_Muzzle, else <mount>_Position), with the stock's first flash's fx / sound / scale; ships whose
  stock file has none (capital ships: the flash is the weapon's) get none
- SpeedBurst (an HW1 Scout ability none of these have) is dropped
- entries already in our override whose names start with "Ram" (the Ramming Frigate's ram effects) are kept

Usage: make_events.py   (then tools/install_base.py)
"""
import os
import re

MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
STOCK = r"C:/Modding/Cataclysm-decomp/reference/hwrm/HW1Ships/ship"
OVR = os.path.join(MOD, "tools", "overrides", "ship")

# our ship: stock HW1 ship (Clee-San: none, user: it will be a recoloured HWRM destroyer)
SHIPS = {
    "smt_scout": "kus_scout",                    # Recon
    "smt_sentinel": "kus_scout",                 # a fighter-class platform (mass 10)
    "smt_swarmer": "kus_interceptor",
    "smt_superacolyte": "kus_defender",
    "smt_rammingfrigate": "kus_assaultfrigate",
    "smt_destroyer": "kus_destroyer",
    "smt_carrier": "kus_carrier",
    "smt_dreadnought": "kus_heavycruiser",
}
DMG_MARKER = re.compile(r"\b(top|left|right|front|back|bottom)_\d\d\b")


def entries(block):
    """[(key, text)] of a Lua table body: key = { ... },"""
    out, i = [], 0
    while True:
        m = re.compile(r"(\w+)\s*=\s*\{").search(block, i)
        if not m:
            return out
        depth, j = 0, m.end() - 1
        while True:
            c = block[j]
            depth += (c == "{") - (c == "}")
            j += 1
            if depth == 0:
                break
        out.append((m.group(1), block[m.start():j]))
        i = j


def sections(text):
    """(animations entries, events entries) of an .events file"""
    text = re.sub(r"--[^\n]*", "", text)
    res = []
    for name in ("animations", "events"):
        m = re.search(name + r"\s*=\s*\{", text)
        if not m:
            res.append([])
            continue
        depth, j = 0, m.end() - 1
        while True:
            depth += (text[j] == "{") - (text[j] == "}")
            j += 1
            if depth == 0:
                break
        res.append(entries(text[m.end():j - 1]))
    return res


def field(entry, key):
    m = re.search(r'\{\s*"' + key + r'",\s*"([^"]*)"', entry)
    return m and m.group(1)


def anim_name(entry):
    m = re.search(r'name\s*=\s*"([^"]*)"', entry)
    return m and m.group(1)


def main():
    for ship, src in SHIPS.items():
        stock = open(os.path.join(STOCK, src, src + ".events"), encoding="latin-1").read()
        anims, events = sections(stock)
        hod = open(os.path.join(MOD, "data", "ship", ship, ship + ".hod"), "rb").read()
        joints = set(re.findall(rb"[A-Za-z][A-Za-z0-9_]{2,63}", hod))
        joints = {j.decode() for j in joints}
        spread = sorted(j for j in joints if re.fullmatch(r"(RepairPoint|CapturePoint)\d+", j))
        spread = spread or sorted(j for j in joints if re.fullmatch(r"Hardpoint_\w+_Position", j)) or ["Root"]
        shiptext = open(os.path.join(MOD, "data", "ship", ship, ship + ".ship"), encoding="latin-1").read()
        mounts = []
        for hp in re.findall(r'^\s*StartShipWeaponConfig\(NewShipType,\s*"[^"]+",\s*"([^"]+)"', shiptext, re.M):
            if hp not in mounts:
                mounts.append(hp)

        flash = next((e for _, e in events if (field(e, "anim") or "").lower().startswith("weapon_")), None)
        anims = [(k, e) for k, e in anims if not re.match(r"(weapon_|speedburst)", anim_name(e) or "", re.I)]
        events = [(k, e) for k, e in events
                  if not re.match(r"(weapon_|speedburst)", field(e, "anim") or "", re.I)]
        out_a = [e for _, e in anims]
        out_e = []
        for k, e in events:
            mk = field(e, "marker")
            if mk is not None:
                if DMG_MARKER.search(mk):
                    e = e.replace(f'"{mk}"', '"' + ",".join(spread) + '"', 1)
                elif mk == "root":
                    e = e.replace('"root"', '"Root"', 1)
            out_e.append(e)
        if flash:
            for n, hp in enumerate(mounts):
                marker = next((m for m in (hp + "_Muzzle", hp + "_Position") if m in joints), None)
                if not marker:
                    continue
                out_a.append(f'{hp} = {{ name = "{hp}", length = 1, loop = 0, parent = "", minimum = 0, maximum = 0, '
                             f'markers = {{ "" }} }}')
                fx = [f'{{ "anim", "{hp}" }}', '{ "animtime", "0" }', f'{{ "marker", "{marker}" }}']
                for key in ("fx", "sound", "fx_scale"):
                    if field(flash, key):
                        fx.append(f'{{ "{key}", "{field(flash, key)}" }}')
                out_e.append(f"wpn{n} = {{ " + ", ".join(fx) + " }")

        path = os.path.join(OVR, ship, ship + ".events")
        if os.path.exists(path):        # our own entries (the ram) kept
            oa, oe = sections(open(path, encoding="latin-1").read())
            out_a += [e for k, e in oa if k.startswith("Ram")]
            out_e += [e for k, e in oe if k.startswith("Ram")]
        head = (f"-- Cataclysm-HWRM: {ship}'s effects (Cataclysm Remastered's file is empty: no death explosion), from\n"
                f"-- stock HW1 {src}.events by tools/make_events.py (generated; its markers and mounts are this ship's)\n")
        if ship == "smt_rammingfrigate":
            head += ("-- RamImpact: Cataclysm's impact shock bowl on its nose tip (tools/make_ramimpact.py), at the impact.\n"
                     "-- RamThrust: its push burn on its engine nozzle (tools/make_ramburn.py), while shiprules.lua\n"
                     "-- CatRam_Tick pushes (started / ended by smt_rammingfrigate.madstate)\n")
        body = ("effects =\n{\n    animations =\n    {\n" + "".join(f"        {e},\n" for e in out_a)
                + "    },\n    events =\n    {\n" + "".join(f"        {e},\n" for e in out_e) + "    },\n}\n")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w", encoding="latin-1", newline="\n").write(head + body)
        print(f"  {ship}: from {src}, {len(out_e)} events, damage markers -> {len(spread)} joints, "
              f"muzzle flashes on {[hp for hp in mounts if flash and (hp + '_Muzzle' in joints or hp + '_Position' in joints)]}")


if __name__ == "__main__":
    main()
