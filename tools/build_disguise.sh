#!/usr/bin/env bash
# The pirate corvette with Cataclysm's script disguises (tur_standardcorvette_disguise): tools/make_disguise.py --dae
# (Remastered models through tools/hod2dae.py), HODOR, then make_disguise.py --install. Run from Git Bash (HODOR).
set -e
cd "$(dirname "$0")/.."
MOD="$(pwd)"
NAME=tur_standardcorvette_disguise
OUT="$MOD/build/ships/$NAME"
HODOR="C:/Program Files (x86)/Steam/steamapps/common/Homeworld 347380/GBXTools/HODOR"
rm -rf "$OUT"
python tools/make_disguise.py --dae
"$HODOR/HODOR.exe" -action=convert "-\$CONVERT_IN=$OUT/$NAME.dae" "-\$CONVERT_OUT=$OUT/$NAME.hod" \
    "-\$SHADER_MAP=$HODOR/SHADERS.MAP" < /dev/null > "$OUT/hodor.log" 2>&1 || true
grep -v -e '^X*$' -e 'Building LMIP' "$OUT/hodor.log" | tail -5 | sed 's/^/  /'
[ -s "$OUT/$NAME.hod" ] || { echo "HODOR did not write $OUT/$NAME.hod"; exit 1; }
echo "build/ships/$NAME/$NAME.hod: $(stat -c %s "$OUT/$NAME.hod") bytes"
python tools/make_disguise.py --install
