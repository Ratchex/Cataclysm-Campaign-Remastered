"""Place damage-factor ship copies in a mission's level for the teams that start with a factor HWRM's multiplier can't
give (below 50 %: SobGroup_SetDamageMultiplier stops ion beams below ~0.5; tools/make_variants.py).

A team's states (from Init_<Mission>'s KASRule_AddFSM(team, ...) + F_<addr>(team), following its direct calls and
KASRule_Add jumps; the Taiidan heavy cruiser's 10 % is set one call in, user: the Kushan were decimated) that call
kasfShipsSetDamageFactor (K_493980(TeamName, pct)): with any pct < 50 its squadrons (the level's addToSOBGroup) get
the <type>_d<lowest pct> copy where make_variants.py builds one (else they keep their type and the runtime floors the
factor). The ship rules take a copy's weapons as its base and apply the team's factor of the moment as a ratio
(shiprules.lua CatShip_KasDamage: the cruiser's later 50 % is x5 on its 10 % copy).

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

    def reach(f0):
        seen, todo = set(), [f0]
        while todo:
            f = todo.pop()
            if f in seen or f not in funcs:
                continue
            seen.add(f)
            body = funcs[f]
            todo += re.findall(r"\b(F_[0-9a-f]+)\(TeamName\)", body)
            todo += re.findall(r'KASRule_Add\(TeamName, "(F_[0-9a-f]+)"', body)
        return seen
    for team, f in re.findall(r'iVar1 = "([A-Za-z0-9_]+)"\n[^\n]*\n\s*KASRule_AddFSM\(iVar1, "[^"]+", "[^"]+"\)\n'
                              r'\s*KAS_Push\(\)\n\s*(F_[0-9a-f]+)\(iVar1\)', kas):
        pcts = [int(p) for g in reach(f) for p in re.findall(r"K_493980\(TeamName, (\d+)\)", funcs[g])]
        if pcts and min(pcts) < LIMIT:
            out[team] = min(pcts)
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
        name, t = m.group(2), re.sub(r"_d\d+$", "", m.group(3))   # (re-runnable: a copy back to its base first)
        pct = factors.get(team_of.get(name))
        if pct is None:
            return f'{m.group(1)}{name}", "{t}"{m.group(4)}'
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
