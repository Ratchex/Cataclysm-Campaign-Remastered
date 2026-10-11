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
ANIM=""; TRIM=""; CLIPS=""; ANIM_SRC=""; PROCBEAM=""
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
    # its repair beam as a heal weapon from the tip (install_cr.py repair_order: ranged, no latching)
    GEO2DAE_ARGS="$GEO2DAE_ARGS --weapon Repair@$TIP@0,0,1"
    CLIPS="JackOut,JackSpin,JackClose,DockOpen,DockClose,BladesSpin"
    ;;
  som_processor)
    # its four lateral repair beams (dock points REPAIR0-3, two each side, facing out: shiprules.lua CAT_PROC_BEAMS)
    # as script-aimed turrets carrying the beam cone; their aim clips: tools/make_procbeam.py --mad (below)
    # (-90 faces -X, the REPAIR0/1 side; the cone mesh runs along +Z: make_procbeam.py write_dae)
    GEO2DAE_ARGS="$GEO2DAE_ARGS --turret Beam0@dok:REPAIR0@-90 --turret Beam1@dok:REPAIR1@-90"
    GEO2DAE_ARGS="$GEO2DAE_ARGS --turret Beam2@dok:REPAIR2@90 --turret Beam3@dok:REPAIR3@90"
    # glow (its landing pads lit like the Kuun-Lan's: user) from Cataclysm Remastered's Processor, the old-format
    # copy (its .hod is the compressed kind hodtex can't read); engines the Kuun-Lan's (user: same engine glow): CR's
    # Kuun-Lan engine shape, x0.909 (CR -> ours) x 0.30 (our Processor's length / our Kuun-Lan's, 340 / 1131)
    GEO2DAE_ARGS="$GEO2DAE_ARGS --glow-from C:/Modding/Cataclysm-decomp/reference/cr_main/ship/smt_processor/smt_processor.hod.bak"
    GEO2DAE_ARGS="$GEO2DAE_ARGS --engines-from C:/Modding/Cataclysm-decomp/reference/cr_main/ship/smt_ms_sp/smt_ms_sp.hod --engines-scale 0.273"
    # its landing pads (0pro20, which CR leaves unlit) are the Kuun-Lan engineering module's pad art (smo_eng_face_upr,
    # luminance correlation 0.99): its glow
    GEO2DAE_ARGS="$GEO2DAE_ARGS --glow-copy 0pro20=C:/Modding/Cataclysm-decomp/reference/cr_main/ship/smt_ms_sp/smt_ms_sp.hod:smo_eng_face_upr"
    PROCBEAM=1
    ;;
  som_mothership)
    # the command module's gravity generator spins (smothershipcommand.mad GravRotate: a full turn every 12 s, looped
    # by our smt_ms_sp.madstate); the module is merged into the core, so the animation comes from its .geo / .mad
    ANIM_SRC=race_sect/smothershipcommand
    ANIM="grav_generator"
    CLIPS="GravRotate"
    GEO2DAE_ARGS="$GEO2DAE_ARGS --anim-joints $ANIM --anim-geo $(geo $ANIM_SRC)"
    ;;
  som_rammingfrigate)
    # its ram: the nose collapses on impact and recovers (RamCollapse / RamRecover), the afterburner ignites and fires
    # on the charge (AftBurnIgnite / AftBurnFiring / CancelAftBurn): srammingfrigate.mad
    ANIM="RammingFrigate,RammingFrigateNose,GunHousing,Gun"
    GEO2DAE_ARGS="$GEO2DAE_ARGS --anim-joints $ANIM"
    # its ram is HWRM's salvage latch (shiprules.lua CatRam_Tick): LatchOrientation / SalvageOrientation (stock
    # salvage corvette's pair) at the ram plate's tip (user: on the very front, latched by its centre it collided),
    # with a collision mesh that follows the hull (--col-slices; with none, targets were held well off). In model
    # space the hull runs z -87.6..45.3 (it hangs 56.7 back on JNT[RammingFrigate]; measured raw, the latch and the
    # collision mesh first sat 56.7 ahead of the nose and the script snugged it 65 back in)
    # The latch joints stay 60 ahead of the nose (z 105): the engine latches at its own distance wherever they are,
    # but aligns the frigate by them, and at the nose tip (z 45) it latched tilted 40 off toward the target's stern
    # (user); at 105, straight (target centre 6 off its axis)
    GEO2DAE_ARGS="$GEO2DAE_ARGS --latch 0,0,105 --salvage-latch 0,0,105 --col-slices 10"
    # one engine nozzle, larger, centred on its rear face (y -20..32; user: one, not one per stacked nozzle; the .mex
    # put one there and two 33 ahead of the nose, user: two copies in front of the ram)
    GEO2DAE_ARGS="$GEO2DAE_ARGS --engines-at 0,6,-87.6"
    # engines the Kuun-Lan's (user): CR's Kuun-Lan engine shape, x0.909 (CR -> ours) x 0.121 (our frigate's length /
    # our Kuun-Lan's, 137 / 1131); its burn: install_cr.py kuunlan_engines
    GEO2DAE_ARGS="$GEO2DAE_ARGS --engines-from C:/Modding/Cataclysm-decomp/reference/cr_main/ship/smt_ms_sp/smt_ms_sp.hod --engines-scale 0.19"
    CLIPS="RamCollapse,RamRecover,AftBurnIgnite,AftBurnFiring,CancelAftBurn"
    ;;
  som_acolyte)
    # the whole body is a joint too: Link / Unlink slide it along its up axis (sacolyte.mad; NOTES.md "Link")
    ANIM="LightInterceptor,LightInterceptorWrist(1),LightInterceptorWrist(2),LightInterceptorGuns"
    ANIM="$ANIM,LightInterceptorThrustRight,LightInterceptorThrust"
    GEO2DAE_ARGS="$GEO2DAE_ARGS --anim-joints $ANIM"
    CLIPS="CombatIn,CombatOut,Link,Unlink"
    # Link starts with the body 50 above the ship (both ships on one spot in Cataclysm); in HWRM two ships on one
    # spot collide and shake, so the ship sits 50 up (shiprules.lua CatLink_Pose) and the clip starts at rest
    TRIM="--shift Link:LightInterceptor=-50,0,0"
    # the pair's lower Acolyte flies upright with its model shown upside down (a rolled ship jiggled: the engine levels
    # it); after Unlink it turns upright in place over a second
    TRIM="$TRIM --rolled LinkB=Link:LightInterceptor --rolled UnlinkB=Unlink:LightInterceptor:1"
    ;;
esac
rm -rf "$OUT"
python "$MOD/tools/geo2dae.py" "$GEO" "$OUT" "$NAME" $GEO2DAE_ARGS $(for h in $HARDPOINTS; do printf -- "--hardpoint %s " "$h"; done) ${MERGE:+--merge "${MERGE[@]}"} | grep -v '^HODOR hangs'
"$HODOR/HODOR.exe" -action=convert "-\$CONVERT_IN=$OUT/$NAME.dae" "-\$CONVERT_OUT=$OUT/$NAME.hod" \
    "-\$SHADER_MAP=$HODOR/SHADERS.MAP" < /dev/null > "$OUT/hodor.log" 2>&1 || true
grep -v -e '^X*$' -e 'Building LMIP' "$OUT/hodor.log" | sed 's/^/  /'
[ -s "$OUT/$NAME.hod" ] || { echo "HODOR did not write $OUT/$NAME.hod"; exit 1; }
echo "build/ships/$NAME/$NAME.hod: $(stat -c %s "$OUT/$NAME.hod") bytes"
if [ -n "$PROCBEAM" ]; then
  python "$MOD/tools/make_procbeam.py" --mad "$OUT/$NAME.mad"
fi
if [ -n "$ANIM" ]; then
  ASRC="${ANIM_SRC:-$SRC}"
  python "$MOD/tools/mad2hwrm.py" "C:/Modding/Cataclysm-decomp/extracted/big/$ASRC.mad" "$(geo "$ASRC")" "$OUT/$NAME.mad" \
      --joints "$ANIM" --clips "$CLIPS" $TRIM
fi
