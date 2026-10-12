"""Extra ships for a mission's teams, where HWRM's combat lands a fight differently from Cataclysm's.

Mission01: its Kushan main guard should hold the battle (the dialogue: the Taiidan are being pushed back), but with
the damage factors right (tools/make_variants.py copies) it still just lost (user): two more ion frigates, which go
first and tip it the Kushan's way (user).

Each extra is a copy of the team's first squadron (same type, place, owner, heading), named on from its last, and
joins the team's group. Re-runnable: extras already there are left alone.

Usage: level_extras.py <NN> <mNN.level>   (run by build_mission.py after damage_variants.py)
"""
import re
import sys

EXTRAS = {"01": [("KushanMainGuardFrigates", 2)]}


def main():
    nn, level = sys.argv[1].zfill(2), sys.argv[2]
    text = open(level, encoding="latin-1").read()
    added = 0
    for team, n in EXTRAS.get(nn, []):
        members = re.findall(r'addToSOBGroup\("([^"]+)", "' + re.escape(team) + r'"\)', text)
        if not members:
            print(f"  level extras: no team {team}")
            continue
        first = re.search(r'^(\s*addSquadron\(")' + re.escape(members[0]) + r'(".*)$', text, re.M)
        want = [f"{team}Extra{k}" for k in range(n)]
        for name in want:
            if f'"{name}"' in text:
                continue
            sq = f'{first.group(1)}{name}{first.group(2)}   -- extra (tools/level_extras.py)'
            text = text.replace(first.group(0), first.group(0) + "\n" + sq, 1)
            last = re.findall(r'^\s*addToSOBGroup\("[^"]+", "' + re.escape(team) + r'"\)$', text, re.M)[-1]
            text = text.replace(last, last + f'\n    addToSOBGroup("{name}", "{team}")', 1)
            added += 1
    open(level, "w", encoding="latin-1", newline="").write(text)
    print(f"  level extras: {added} ships added")


if __name__ == "__main__":
    main()
