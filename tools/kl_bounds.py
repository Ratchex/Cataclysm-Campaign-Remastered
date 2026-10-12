"""The box around every Kuun-Lan module (build/ships/smt_kl_<key>, as tools/build_kuunlan.sh builds them) in the
Kuun-Lan's frame: x0,y0,z0,x1,y1,z1 for geo2dae.py --col-box (the core's one collision box takes them in; the
modules have none of their own, --col-none). A module's mesh is about its hardpoint (origin.txt) where it has one;
Support's sits on its dock points on one side, mirrored for the other.

Usage: kl_bounds.py   (after the modules are built)
"""
import os
import re
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def main():
    specs = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "make_modules.py"), "--list-builds"],
                           capture_output=True, text=True, check=True).stdout.split()
    lo, hi = [1e9] * 3, [-1e9] * 3
    for spec in specs:
        key = spec.split("=")[0]
        d = os.path.join(ROOT, "build", "ships", f"smt_kl_{key}")
        dae = open(os.path.join(d, f"smt_kl_{key}.dae"), encoding="utf-8").read()
        o = os.path.join(d, "origin.txt")
        off = [float(c) for c in open(o).read().split(",")] if os.path.exists(o) else [0.0] * 3
        for g in re.finditer(r'<geometry id="MULT\[[^"]*".*?<float_array[^>]*>([^<]*)<', dae, re.S):
            v = [float(c) for c in g.group(1).split()]
            for p in zip(v[0::3], v[1::3], v[2::3]):
                q = [p[k] + off[k] for k in range(3)]
                for pt in ([q, [-q[0], q[1], q[2]]] if key == "support" else [q]):
                    lo = [min(lo[k], pt[k]) for k in range(3)]
                    hi = [max(hi[k], pt[k]) for k in range(3)]
    print(",".join(f"{c:.2f}" for c in lo + hi))


if __name__ == "__main__":
    main()
