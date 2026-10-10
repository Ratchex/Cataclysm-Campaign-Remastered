#!/usr/bin/env bash
# The Mimic's model (som_mimic): Cataclysm's smimic as joint MimicBody plus each disguise target's Cataclysm model as
# a hidden joint Disguise_<target>, shown one at a time by tools/overrides/ship/smt_mimic/smt_mimic.madstate; and a
# still .mad (tools/make_static_mad.py: the madstate never ran without one). Then tools/install_cr.py.
# TEST: one disguise (kus_attackbomber). Run from Git Bash (HODOR).
set -e
cd "$(dirname "$0")/.."
B=C:/Modding/Cataclysm-decomp/extracted/big
GEO2DAE_ARGS="--body MimicBody --part Disguise_kus_attackbomber@$B/race_kushan/kattackbomber/rl0/lod0/kattackbomber.geo" \
    bash tools/build_ship.sh race_sect/smimic som_mimic | tail -1
python tools/make_static_mad.py build/ships/som_mimic/som_mimic.mad MimicBody Disguise_kus_attackbomber
