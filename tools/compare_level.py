"""Check mission2level.py against a Gearbox-converted level: for every squadron, point and sphere present in both
(matched by name), report position/rotation/radius differences. Gearbox hand-edited some levels afterwards, so
names only in one file are listed but not counted as failures.

Usage: compare_level.py <ours.level> <gearbox.level> [tolerance]
"""
import re
import sys

NUM = r"-?[0-9.eE+-]+"
VEC = rf"\{{\s*({NUM})\s*,\s*({NUM})\s*,\s*({NUM})\s*,?\s*\}}"
SQ = re.compile(rf'addSquadron\("([^"]+)",\s*"([^"]+)",\s*{VEC},\s*(\d+),\s*{VEC}')
PT = re.compile(rf'addPoint\("([^"]+)",\s*{VEC},\s*{VEC}')
SP = re.compile(rf'addSphere\("([^"]+)",\s*{VEC},\s*({NUM})\)')


def yaw(x, y, z):
    """Heading of an {x, y, z} Euler triple; {180, t, 180} is the same orientation as {0, 180 - t, 0}."""
    if abs(abs(x) - 180) < 0.5 and abs(abs(z) - 180) < 0.5:
        return 180 - y
    return y


def parse(path):
    text = open(path, encoding="latin-1").read()
    out = {}
    for m in SQ.finditer(text):
        g = m.groups()
        out["sq:" + g[0]] = (tuple(map(float, g[2:5])) + (yaw(*map(float, g[6:9])),), g[1].lower(), int(g[5]))
    for m in PT.finditer(text):
        g = m.groups()
        out["pt:" + g[0]] = (tuple(map(float, g[1:4])) + (yaw(*map(float, g[4:7])),), None, None)
    for m in SP.finditer(text):
        g = m.groups()
        out["sp:" + g[0]] = (tuple(map(float, g[1:5])), None, None)
    return out


def yaw_equal(a, b):
    return abs(((a - b) + 180) % 360 - 180) < 0.5


def main():
    ours, theirs = parse(sys.argv[1]), parse(sys.argv[2])
    tol = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    common = sorted(set(ours) & set(theirs))
    bad = 0
    for k in common:
        (a, ta, pa), (b, tb, pb) = ours[k], theirs[k]
        posd = max(abs(x - y) for x, y in zip(a[:3], b[:3]))
        last_ok = yaw_equal(a[3], b[3]) if k[:2] in ("sq", "pt") else abs(a[3] - b[3]) <= tol
        type_ok = ta is None or ta == tb
        owner_ok = pa is None or pa == pb
        if posd > tol or not last_ok or not type_ok or not owner_ok:
            bad += 1
            print(f"DIFF {k}: ours {a} {ta} p{pa} | gearbox {b} {tb} p{pb}")
    print(f"matched {len(common)} names, {bad} differ (tolerance {tol}); "
          f"only ours {len(set(ours) - set(theirs))}, only gearbox {len(set(theirs) - set(ours))}")
    only_g = sorted(set(theirs) - set(ours))
    if only_g:
        print("only in gearbox:", ", ".join(only_g[:25]), "..." if len(only_g) > 25 else "")


if __name__ == "__main__":
    main()
