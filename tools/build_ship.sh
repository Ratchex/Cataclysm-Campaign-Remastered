#!/usr/bin/env bash
# Build one Cataclysm ship model into the mod: geo2dae.py (DAE + textures in build/ships/<name>/), HODOR (.hod),
# kept in build/ships/<name>/ for tools/install_cr.py (OUR_MODELS). Run from Git Bash: HODOR spins forever when Python/PowerShell start it.
# HARDPOINTS=Hardpoint_Research adds a subsystem hardpoint joint set at the origin; GEO2DAE_ARGS go to geo2dae.py.
# Usage: tools/build_ship.sh <race_dir>/<cataclysm_ship> <hwrm_name> [<race_dir>/<module> ...]
#   e.g. race_sect/smothership som_mothership race_sect/smothershipcommand ...  (modules are baked into the mesh)
set -e
MOD="$(cd "$(dirname "$0")/.." && pwd -W)"
SRC="$1"; NAME="$2"; shift 2
geo() { echo "C:/Modding/Cataclysm-decomp/extracted/big/$1/rl0/lod0/$(basename "$1").geo"; }
MERGE=(); for m in "$@"; do MERGE+=("$(geo "$m")"); done
GEO="$(geo "$SRC")"
OUT="$MOD/build/ships/$NAME"
HODOR="C:/Program Files (x86)/Steam/steamapps/common/Homeworld 347380/GBXTools/HODOR"
rm -rf "$OUT"
python "$MOD/tools/geo2dae.py" "$GEO" "$OUT" "$NAME" $GEO2DAE_ARGS $(for h in $HARDPOINTS; do printf -- "--hardpoint %s " "$h"; done) ${MERGE:+--merge "${MERGE[@]}"} | grep -v '^HODOR hangs'
"$HODOR/HODOR.exe" -action=convert "-\$CONVERT_IN=$OUT/$NAME.dae" "-\$CONVERT_OUT=$OUT/$NAME.hod" \
    "-\$SHADER_MAP=$HODOR/SHADERS.MAP" < /dev/null > "$OUT/hodor.log" 2>&1 || true
grep -v -e '^X*$' -e 'Building LMIP' "$OUT/hodor.log" | sed 's/^/  /'
[ -s "$OUT/$NAME.hod" ] || { echo "HODOR did not write $OUT/$NAME.hod"; exit 1; }
echo "build/ships/$NAME/$NAME.hod: $(stat -c %s "$OUT/$NAME.hod") bytes"
