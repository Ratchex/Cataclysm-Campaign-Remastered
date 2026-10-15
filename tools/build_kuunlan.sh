#!/usr/bin/env bash
# Build the Kuun-Lan: its core (som_mothership: hull with the Command Center and Resource Processing merged in, guns, docking-bay and repair docks,
# collector paths on Cataclysm's RES points, engine nozzles from the engine modules, one hardpoint per module slot)
# and every module (smt_kl_<key>, no docks) into build/ships/. Then: tools/make_modules.py, tools/install_base.py.
# Run from Git Bash (HODOR).
set -e
cd "$(dirname "$0")/.."
SECT=C:/Modding/Cataclysm-decomp/extracted/big/race_sect
# (no glow maps: Cataclysm has none; engines geo2dae's own glow quad on the .mex nozzles)
for spec in $(python tools/make_modules.py --list-builds); do
    key=${spec%%=*}; cat=${spec#*=}
    MODARGS="--no-docks"
    # the lower engine's exhaust (spine texture, no glow) as the upper's glowing thruster (user: same glow as the upper)
    [ "$key" = engineslower ] && MODARGS="$MODARGS --retexture smo_lowspine_sides=race_sect/smothershipenginesupper:SMO_engup_thruster@0,0.53,0,0.709"
    # the lower spine's fake landing pads glow over their cyan areas (user: like the engineering module's real ones)
    [ "$key" = lowerspine ] && MODARGS="$MODARGS --glow-cyan ocl_new_sidetop"
    # on the Kuun-Lan: recentred, its hardpoint at its centre (HWRM draws a subsystem's health bar at its hardpoint:
    # at the shared origin every bar sat in the middle of the ship); Support already sits on its dock points
    ORIGIN=""; [ "$key" != support ] && ORIGIN="--origin auto"
    # on the Kuun-Lan no collision of its own (--col-none; the core's box takes it in, tools/kl_bounds.py): as a
    # subsystem its own stopped the guns mounted on it, the rear guns' shots burst at the muzzle (user)
    GEO2DAE_ARGS="$MODARGS $ORIGIN --col-none" bash tools/build_ship.sh "race_sect/$cat" "smt_kl_$key" | tail -1
    # loose (jettisoned modules, NIS dummies): in the Kuun-Lan's frame, placed where the Kuun-Lan is
    if [ -n "$ORIGIN" ]; then
        GEO2DAE_ARGS="$MODARGS" bash tools/build_ship.sh "race_sect/$cat" "smt_kl_${key}_dummy" | tail -1
    fi
done
# one collision box around the whole ship, modules included (Cataclysm's: a box per ship from its model's bounds)
COLBOX=$(python tools/kl_bounds.py)
HARDPOINTS="Hardpoint_Research $(python tools/make_modules.py --list-hardpoints)" \
GEO2DAE_ARGS="--points-from $SECT/smothershipengineslower/rl0/lod0/smothershipengineslower.geo \
--points-from $SECT/smothershipenginesupper/rl0/lod0/smothershipenginesupper.geo --col-box $COLBOX" \
    bash tools/build_ship.sh race_sect/smothership som_mothership $(python tools/make_modules.py --list-core) | tail -1
python tools/make_modules.py   # installs the module models (data/subsystem, data/ship/*_dummy)
