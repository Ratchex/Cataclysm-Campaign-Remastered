"""Nebula wisps along the asteroid fields: HW1's Nebula0 resource (the white wispy smoke HWRM draws in the Gardens of
Kadesh, HW1 mission07 / 08: addNebulaWithResources on a strand's points, addTendrils along them) that no ship harvests.

Cataclysm lays its asteroid fields out as chains of cylinders that read as tendrils in its sensors view; our sensors
look and distance scale lose that, so the levels put wisps along each field's axis (tools/mission2level.py, user
2026-10-18). Range tests (user, 2026-10-18):
  - addTendrils draws the smoke between a strand's Nebula0 resources; alone it draws nothing; the resources alone are
    small separate clouds, each worth the RU its call gives.
  - Only the type named Nebula0 gets the smoke: copies under other names (resourceValue 0 / 1, other families) were
    plain white balls or nothing, and Gearbox's no-resource nebula (m05_nebualdustcloud_nores, by addNebula) tan
    clouds, with or without tendrils.
  - So stock Nebula0 itself is overridden (our file is read: resourceValue 50 showed 100 RU). DockFamily CantDock and
    AttackFamily UnAttackable still let Workers harvest it; no stock resource key says "harvestable", and Gearbox's
    non-harvestable nebula simply has no resourceValue: without the line it is no longer harvestable, the smoke kept
    (user). Still selectable: unselectable as stock HW2's decorative asteroids (asteroid_1 / 2 / 6) and our meteors
    are, selectionLimit 0 etc. (TEST). Only our levels place Nebula0.
Writes data/resource/nebula/nebula0/ (.resource ours, .hod stock HW1's, git-ignored).
Usage: python tools/make_wisps.py
"""
import os
import re
import shutil
import struct

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(r"C:\Modding\Cataclysm-decomp\reference\hwrm", "HW1Campaign", "resource", "nebula", "nebula0")
NAME = "nebula0"
DROP = ["resourceValue"]
SET = {"selectionSizeMax": "0", "selectionPriority": "0"}
ADD = {"selectionLimit": "0", "preciseSelectionLimit": "0"}
TINT, TINT_GAIN = (1.0, 0.55, 0.25), 1.3      # the wisps' orange (Cataclysm's haze; user: "the same kind of orange")


def tint(path):
    """The model's one texture (dustringMono3, 8888, its mips inline: no POOL) recoloured TINT x each pixel's
    luminance, alpha kept: addNebulaWithResources' colour argument doesn't tint the wisps (range test, user wanted
    them orange)."""
    import numpy as np
    d = bytearray(open(path, "rb").read())
    i = d.index(b"LMIP")
    n = struct.unpack_from("<I", d, i + 8)[0]
    assert d[i + 12 + n:i + 16 + n] == b"8888", "nebula0.hod: texture not 8888"
    o = i + 20 + n
    for _ in range(struct.unpack_from("<I", d, i + 16 + n)[0]):
        w, h = struct.unpack_from("<II", d, o)
        o += 8
        img = np.frombuffer(bytes(d[o:o + w * h * 4]), np.uint8).reshape(h, w, 4).astype(np.float32)
        lum = img[:, :, 0] * 0.299 + img[:, :, 1] * 0.587 + img[:, :, 2] * 0.114
        img[:, :, :3] = lum[:, :, None] * np.array(TINT, np.float32) * TINT_GAIN
        d[o:o + w * h * 4] = img.clip(0, 255).astype(np.uint8).tobytes()
        o += w * h * 4
    open(path, "wb").write(bytes(d))


def main():
    text = open(os.path.join(REF, NAME + ".resource"), encoding="latin-1").read()
    for key in DROP:
        text, n = re.subn(r"^NewResourceType\.%s\s*=[^\n]*\n" % key, "", text, flags=re.M)
        assert n == 1, f"{NAME}.resource: no {key}"
    for key, value in SET.items():
        text, n = re.subn(r"^(NewResourceType\.%s\s*=\s*)[^\n]*" % key, lambda m: m.group(1) + value, text,
                          flags=re.M)
        assert n == 1, f"{NAME}.resource: no {key}"
    text = text.rstrip("\n") + "\n" + "".join(f"NewResourceType.{k}={v}\n" for k, v in ADD.items())
    out = os.path.join(MOD, "data", "resource", "nebula", NAME)
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, NAME + ".resource"), "w", encoding="latin-1", newline="\n").write(
        "-- Cataclysm-HWRM: stock HW1 nebula0, never harvested (tools/make_wisps.py)\n" + text)
    hod = os.path.join(out, NAME + ".hod")
    shutil.copyfile(os.path.join(REF, NAME + ".hod"), hod)
    tint(hod)
    print(f"{NAME}: without {', '.join(DROP)}; " + ", ".join(f"{k} {v}" for k, v in {**SET, **ADD}.items()))


if __name__ == "__main__":
    main()
