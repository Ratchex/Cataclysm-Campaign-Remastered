#!/usr/bin/env bash
# The Mimic's model (som_mimic): Cataclysm's smimic as joint MimicBody plus each disguise target's Cataclysm model as
# a hidden joint Disguise_<target> in its faction's colours (tools/make_mimic.py), then its .madstate and still .mad.
# Then tools/install_base.py. Run from Git Bash (HODOR).
set -e
cd "$(dirname "$0")/.."
PARTS=""
for p in $(python tools/make_mimic.py --list-parts); do PARTS="$PARTS --part $p"; done
GEO2DAE_ARGS="--body MimicBody$PARTS" bash tools/build_ship.sh race_sect/smimic som_mimic | tail -1
python tools/make_mimic.py
