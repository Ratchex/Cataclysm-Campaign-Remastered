"""Build shipmap.tsv (Cataclysm race:ship -> HWRM ship type) for mission2level.py.

Kushan (kXxx) and Taiidan (tXxx) ships map onto HWRM's Kus_/Tai_ ships when the same type exists, otherwise via
the substitutions Gearbox used when converting HW1's campaign (seen in its Mission05/10 levels). Every other race
(Somtaaw, Beast, Turanic/P1, Traders, Derelicts) is left blank until Phase 1 builds those ships; the converter
then uses its --placeholder type.

Usage: make_shipmap.py <catalogue/ships.tsv> <hwrm shiplist.txt> <out shipmap.tsv>
"""
import csv
import sys

RACE_CODES = {"kushan": ("RACE_KUSHAN", "k", "kus_"), "taidan": ("RACE_TAIDAN", "t", "tai_"),
              "sect": ("RACE_SECT", "s", None), "beast": ("RACE_BEAST", "b", None), "p1": ("RACE_P1", "p1", None),
              "traders": ("RACE_TRADERS", "", None), "derelict": ("RACE_DERELICT", "", None)}
# HW1 types HWRM dropped, and what Gearbox substituted (from homeworldclassic Mission05/Mission10)
GEARBOX_SUBSTITUTES = {"heavyinterceptor": "interceptor", "lightinterceptor": "scout", "heavydefender": "defender",
                       "standardfrigate": "assaultfrigate", "standarddestroyer": "destroyer",
                       "advancesupportfrigate": "supportfrigate",
                       # HW1 names HWRM spells differently
                       "salcapcorvette": "salvagecorvette", "dfgfrigate": "fieldfrigate"}


def main():
    ships_tsv, shiplist, out = sys.argv[1:4]
    hwrm = {s.strip().lower(): s.strip() for s in open(shiplist) if s.strip()}
    rows, mapped = [], 0
    with open(ships_tsv, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            code, prefix, hw_prefix = RACE_CODES[r["race"]]
            base = r["ship"][len(prefix):] if prefix and r["ship"].lower().startswith(prefix) else r["ship"]
            target, note = "", "needs a new HWRM ship (Phase 1)"
            if hw_prefix:
                b = base.lower()
                for cand, why in ((b, "same HWRM type"), (GEARBOX_SUBSTITUTES.get(b, ""), "Gearbox substitute")):
                    if cand and hw_prefix + cand in hwrm:
                        target, note = hwrm[hw_prefix + cand], why
                        break
                else:
                    note = "no HWRM equivalent"
            mapped += bool(target)
            rows.append((code, r["ship"], target, note))
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("race\tship\thwrm\tnote\n")
        for row in rows:
            f.write("\t".join(row) + "\n")
    print(f"{out}: {len(rows)} ships, {mapped} mapped to existing HWRM types")


if __name__ == "__main__":
    main()
