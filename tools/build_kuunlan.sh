#!/usr/bin/env bash
# Build the Kuun-Lan: its core (som_mothership: hull with the Command Center and Resource Processing merged in, guns, docking-bay and repair docks, Cataclysm Remastered's
# collector paths on our nose RES points, engine nozzles from the engine modules, one hardpoint per module slot)
# and every module (smt_kl_<key>, no docks) into build/ships/. Then: tools/make_modules.py, tools/install_cr.py.
# Run from Git Bash (HODOR).
set -e
cd "$(dirname "$0")/.."
SECT=C:/Modding/Cataclysm-decomp/extracted/big/race_sect
# emissive maps and engine look: Cataclysm Remastered's Kuun-Lan (GLOW textures: its textures are Cataclysm's, upscaled, same UVs;
# engines: its ETSH trail shape on our nozzles (plus our BURN flames for its setEngineBurn); x0.909 = CR's model -> ours, as the dock paths)
GLOW=C:/Modding/Cataclysm-decomp/reference/cr_main/ship/smt_ms_sp/smt_ms_sp.hod
for spec in $(python tools/make_modules.py --list-builds); do
    key=${spec%%=*}; cat=${spec#*=}
    MODARGS="--no-docks --glow-from $GLOW --engines-from $GLOW --engines-scale 0.909"
    # on the Kuun-Lan: recentred, its hardpoint at its centre (HWRM draws a subsystem's health bar at its hardpoint:
    # at the shared origin every bar sat in the middle of the ship); Support already sits on its dock points
    ORIGIN=""; [ "$key" != support ] && ORIGIN="--origin auto"
    GEO2DAE_ARGS="$MODARGS $ORIGIN" bash tools/build_ship.sh "race_sect/$cat" "smt_kl_$key" | tail -1
    # loose (jettisoned modules, NIS dummies): in the Kuun-Lan's frame, placed where the Kuun-Lan is
    if [ -n "$ORIGIN" ]; then
        GEO2DAE_ARGS="$MODARGS" bash tools/build_ship.sh "race_sect/$cat" "smt_kl_${key}_dummy" | tail -1
    fi
done
HARDPOINTS="Hardpoint_Research $(python tools/make_modules.py --list-hardpoints)" \
GEO2DAE_ARGS="--glow-from $GLOW --engines-from $GLOW --engines-scale 0.909 --dock-from C:/Modding/Cataclysm-decomp/reference/cr_beast/ship/smt_ms/smt_ms.hod --dock-scale 0.909 \
--points-from $SECT/smothershipengineslower/rl0/lod0/smothershipengineslower.geo \
--points-from $SECT/smothershipenginesupper/rl0/lod0/smothershipenginesupper.geo" \
    bash tools/build_ship.sh race_sect/smothership som_mothership $(python tools/make_modules.py --list-core) | tail -1
python tools/make_modules.py   # installs the module models (data/subsystem, data/ship/*_dummy)
