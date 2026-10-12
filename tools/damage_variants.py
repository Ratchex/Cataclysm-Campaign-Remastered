"""Place damage-factor ship copies in a mission's level for the teams that start with a factor HWRM's multiplier can't
give (below 50 %: SobGroup_SetDamageMultiplier stops ion beams below ~0.5; tools/make_variants.py).

A team's starting state (Init_<Mission>: KASRule_AddFSM(team, ...) then F_<addr>(team)) that calls
kasfShipsSetDamageFactor (K_493980(TeamName, pct)) with pct < 50: its squadrons (the level's addToSOBGroup) get the
<type>_d<pct> copy where make_variants.py builds one (else they keep their type and the runtime floors the factor).
Factors set in later states change ships already placed: those stay on the floored multiplier.

Usage: damage_variants.py <mNN.level> <mNN_kas.lua>   (run by build_mission.py after kas2lua.py; edits the level)
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_variants import VARIANTS  # noqa: E402

LIMIT = 50


def team_factors(kas):
    funcs = {m.group(1): m.group(2) for m in re.finditer(r"^function (F_[0-9a-f]+)\(TeamName\)\n(.*?)^end", kas,
                                                          re.M | re.S)}
    out = {}
    for team, f in re.findall(r'iVar1 = "([A-Za-z0-9_]+)"\n[^\n]*\n\s*KASRule_AddFSM\(iVar1, "[^"]+", "[^"]+"\)\n'
                              r'\s*KAS_Push\(\)\n\s*(F_[0-9a-f]+)\(iVar1\)', kas):
        m = re.search(r"K_493980\(TeamName, (\d+)\)", funcs.get(f, ""))
        if m and int(m.group(1)) < LIMIT:
            out[team] = int(m.group(1))
    return out


def main():
    level, kas_path = sys.argv[1], sys.argv[2]
    kas = open(kas_path, encoding="latin-1").read()
    text = open(level, encoding="latin-1").read()
    have = {(s, p) for s, p in VARIANTS}
    factors = team_factors(kas)
    team_of = {sq: g for sq, g in re.findall(r'addToSOBGroup\("([^"]+)", "([^"]+)"\)', text)}
    swapped, missing = 0, set()

    def swap(m):
        nonlocal swapped
        name, t = m.group(2), m.group(3)
        pct = factors.get(team_of.get(name))
        if pct is None:
            return m.group(0)
        if (t.lower(), pct) not in have:
            missing.add(f"{t}_d{pct}")
            return m.group(0)
        swapped += 1
        return f'{m.group(1)}{name}", "{t.lower()}_d{pct}"{m.group(4)}'
    text = re.sub(r'(addSquadron\(")([^"]+)", "([^"]+)"(.*)', swap, text)
    open(level, "w", encoding="latin-1", newline="").write(text)
    print(f"{os.path.basename(level)}: {swapped} squadrons on damage copies ({len(factors)} teams under {LIMIT} %)"
          + (f"; no copy for {sorted(missing)} (add to make_variants.VARIANTS)" if missing else ""))


if __name__ == "__main__":
    main()
