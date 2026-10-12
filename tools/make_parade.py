"""The Kuun-Lan's parade formation from Cataclysm's (parade_smothership.script), in place of Cataclysm Remastered's
smt_mothership_parade.lua (user: ships launched into a parade unlike Cataclysm's).

Cataclysm: SlotPositionInfo[SLOT_<type>] up, right, heading offsets, up, right, heading spacing, face direction.
HWRM: paradeSlot(type, offset, heading, direction of growth, size of growth). HW1 model space is X up, Y right,
Z forward, HWRM = 0.35 * (-y, x, z) (NOTES.md; the ship models' scale): offset = 0.35 * (-right, up, heading),
growth along the spacing the same way, its size the spacing's length x 0.35. Face direction 0 (all of the
Kuun-Lan's) is forward.

Every Somtaaw ship type (data/ship/smt_*) takes its Cataclysm slot (SLOTS; a type's variants <type>_<x> too); the
rest go to Cataclysm's SLOT_Misc ("all ships not covered above") as HWRM's required "misc" slot.

Writes tools/overrides/scripts/formations/smt_mothership_parade.lua (tools/install_cr.py installs it).
Usage: make_parade.py
"""
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
SCRIPT = r"C:\Modding\Cataclysm-decomp\extracted\big\parade_smothership.script"
OUT = os.path.join(HERE, "overrides", "scripts", "formations", "smt_mothership_parade.lua")
SCALE = 0.35

# Cataclysm slot -> our ship types (Cataclysm's SLOT_SCARRIER1 / 2 are the second and third carrier: HWRM grows
# the first slot instead; it has no Leech)
SLOTS = {
    "SLOT_SRECON": ["smt_scout"],
    "SLOT_SACOLYTE": ["smt_acolyte"],
    "SLOT_SACV": ["smt_acv"],
    "SLOT_SSENTINEL": ["smt_sentinel"],
    "SLOT_SWORKER": ["smt_worker"],
    "SLOT_SMIMIC": ["smt_mimic"],
    "SLOT_SMCV": ["smt_mcv_ioncannonfrigate", "smt_mcv_supportfrigate"],
    "SLOT_SRAMMINGFRIGATE": ["smt_rammingfrigate"],
    "SLOT_SMULTIBEAMFRIGATE": ["smt_multibeamfrigate"],
    "SLOT_SHIVEFRIGATE": ["smt_hivefrigate"],
    "SLOT_SDESTROYER": ["smt_destroyer"],
    "SLOT_SCARRIER0": ["smt_carrier"],
    "SLOT_SDREADNOUGHT": ["smt_dreadnought"],
    "SLOT_SPROCESSOR": ["smt_processor"],
}


def fmt(v):
    return "{" + ", ".join(f"{c:g}" for c in v) + "}"


def main():
    slots = {}
    for line in open(SCRIPT, encoding="latin-1"):
        m = re.match(r"\s*SlotPositionInfo\[(\w+)\]\s+(.*)", line)
        if m:
            slots[m.group(1)] = [float(t) for t in m.group(2).split(";")[0].replace(",", " ").split()[:7]]

    def hwrm(up, right, heading):
        return (-right * SCALE, up * SCALE, heading * SCALE)

    types = sorted(d for d in os.listdir(os.path.join(MOD, "data", "ship"))
                   if d.startswith("smt_") and os.path.exists(os.path.join(MOD, "data", "ship", d, d + ".ship")))
    lines = ["-- Cataclysm-HWRM: the Kuun-Lan's parade, Cataclysm's parade_smothership.script by tools/make_parade.py",
             "-- (generated): paradeSlot(type, offset, heading, direction of growth, size of growth); port: strike craft,",
             "-- starboard: frigates, aft: capital ships, nothing at the bow (Cataclysm: it interferes with crystal",
             "-- harvesting)", ""]
    placed = set()
    for slot, bases in SLOTS.items():
        up, right, heading, sup, sright, sheading, face = slots[slot]
        off = hwrm(up, right, heading)
        grow = hwrm(sup, sright, sheading)
        size = math.sqrt(sum(c * c for c in grow))
        gdir = tuple(round(c / size, 4) for c in grow) if size else (0, 0, 0)
        assert face == 0, slot
        for t in types:
            if any(t == b or t.startswith(b + "_") for b in bases):
                lines.append(f'paradeSlot("{t}", {fmt(off)}, {{0, 0, 1}}, {fmt(gdir)}, {size:g});   -- {slot}')
                placed.add(t)
    up, right, heading, sup, sright, sheading, face = slots["SLOT_Misc"]
    grow = hwrm(sup, sright, sheading)
    size = math.sqrt(sum(c * c for c in grow))
    lines += ["", "-- everything else (Cataclysm's SLOT_Misc: salvaged ships and the rest)",
              f'paradeSlot("misc", {fmt(hwrm(up, right, heading))}, {{0, 0, 1}}, '
              f'{fmt(tuple(round(c / size, 4) for c in grow))}, {size:g});', ""]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="latin-1", newline="\n").write("\n".join(lines))
    print(f"{OUT}: {len(placed)} ship types in Cataclysm slots, misc for {sorted(set(types) - placed)}")


if __name__ == "__main__":
    main()
