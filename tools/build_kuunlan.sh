#!/usr/bin/env bash
# Build the Kuun-Lan: its core (som_mothership: hull with the Command Center and Resource Processing merged in, guns, docking-bay and repair docks, Cataclysm Remastered's
# collector paths on our nose RES points, engine nozzles from the engine modules, one hardpoint per module slot)
# and every module (smt_kl_<key>, no docks) into build/ships/. Then: tools/make_modules.py, tools/install_cr.py.
# Run from Git Bash (HODOR).
set -e
cd "$(dirname "$0")/.."
SECT=C:/Modding/Cataclysm-decomp/extracted/big/race_sect
# emissive maps: Cataclysm Remastered's Kuun-Lan GLOW textures (its textures are Cataclysm's, upscaled; same UVs)
GLOW=C:/Modding/Cataclysm-decomp/reference/cr_main/ship/smt_ms_sp/smt_ms_sp.hod
for spec in $(python tools/make_modules.py --list-builds); do
    key=${spec%%=*}; cat=${spec#*=}
    GEO2DAE_ARGS="--no-docks --glow-from $GLOW" bash tools/build_ship.sh "race_sect/$cat" "smt_kl_$key" | tail -1
done
HARDPOINTS="Hardpoint_Research $(python tools/make_modules.py --list-hardpoints)" \
GEO2DAE_ARGS="--glow-from $GLOW --dock-from C:/Modding/Cataclysm-decomp/reference/cr_beast/ship/smt_ms/smt_ms.hod --dock-scale 0.909 \
--points-from $SECT/smothershipengineslower/rl0/lod0/smothershipengineslower.geo \
--points-from $SECT/smothershipenginesupper/rl0/lod0/smothershipenginesupper.geo" \
    bash tools/build_ship.sh race_sect/smothership som_mothership $(python tools/make_modules.py --list-core) | tail -1
python tools/make_modules.py   # installs the module models (data/subsystem, data/ship/*_dummy)
