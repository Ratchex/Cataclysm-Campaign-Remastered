#!/usr/bin/env bash
# The Mimic's shell meshes: each disguise target's Cataclysm model as one plain mesh (geo2dae.py --fx-mesh) into
# build/ships/fx_<target>/, then tools/make_mimicfx.py (the effects). Run from Git Bash (HODOR).
set -e
cd "$(dirname "$0")/.."
for spec in $(python tools/make_mimicfx.py --list-builds); do
    target=${spec%%=*}; model=${spec#*=}
    GEO2DAE_ARGS="--fx-mesh --no-navlights --no-engines --no-docks" bash tools/build_ship.sh "$model" "fx_$target" | tail -1
done
python tools/make_mimicfx.py
