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
# Animated ships: their Cataclysm .mad objects become joints (geo2dae --anim-joints) driven by a converted .mad
# (tools/mad2hwrm.py -> build/ships/<name>/<name>.mad, installed by install_cr.py), plus effect marker joints.
ANIM=""; TRIM=""
case "$NAME" in
  som_worker)
    ANIM="Jackbase,Jackhamr,Blade(1),Blade(2),Blade(3),DockClmp(1),DockClmp(2),DockClmp(3),DockClmp(4)"
    # harvest and repair beams (stock HWRM effects, smt_worker.events) start where Cataclysm's extended jackhammer
    # tip is, pointing straight ahead (Cataclysm aims both beams at the target, which the Worker faces). Fixed
    # markers: the beams only play once the boom is out (smt_worker.madstate), and the boom now swings 5 degrees
    # less than Cataclysm's (TRIM: its tip sat slightly above the beam in game), the beams staying put.
    TIP="-0.081,28.486,-0.223"
    GEO2DAE_ARGS="$GEO2DAE_ARGS --anim-joints $ANIM --marker marker_beam@$TIP --marker marker_repair@$TIP"
    TRIM="--trim Jackbase=5"
    # asteroid surface 45 ahead of the beam start (35 was a little close in game): the stock harvest cone is ~35 long
    # at scale 1 (stock kus_resourcecollector's beam marker to its LatchOrientation plane), scaled 1.3 in
    # smt_worker.events. Cataclysm held 400 HW1 units (140) off, far beyond the stock cone.
    GEO2DAE_ARGS="$GEO2DAE_ARGS --latch 0,28.5,44.8"
    ;;
esac
rm -rf "$OUT"
python "$MOD/tools/geo2dae.py" "$GEO" "$OUT" "$NAME" $GEO2DAE_ARGS $(for h in $HARDPOINTS; do printf -- "--hardpoint %s " "$h"; done) ${MERGE:+--merge "${MERGE[@]}"} | grep -v '^HODOR hangs'
"$HODOR/HODOR.exe" -action=convert "-\$CONVERT_IN=$OUT/$NAME.dae" "-\$CONVERT_OUT=$OUT/$NAME.hod" \
    "-\$SHADER_MAP=$HODOR/SHADERS.MAP" < /dev/null > "$OUT/hodor.log" 2>&1 || true
grep -v -e '^X*$' -e 'Building LMIP' "$OUT/hodor.log" | sed 's/^/  /'
[ -s "$OUT/$NAME.hod" ] || { echo "HODOR did not write $OUT/$NAME.hod"; exit 1; }
echo "build/ships/$NAME/$NAME.hod: $(stat -c %s "$OUT/$NAME.hod") bytes"
if [ -n "$ANIM" ]; then
  python "$MOD/tools/mad2hwrm.py" "C:/Modding/Cataclysm-decomp/extracted/big/$SRC.mad" "$GEO" "$OUT/$NAME.mad" \
      --joints "$ANIM" --clips JackOut,JackSpin,JackClose,DockOpen,DockClose,BladesSpin $TRIM
fi
