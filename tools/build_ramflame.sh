#!/usr/bin/env bash
# The Ramming Frigate's push flame mesh (tools/make_ramflame.py --dae, HODOR) and its effect files. Then
# tools/install_cr.py. Run from Git Bash (HODOR).
set -e
cd "$(dirname "$0")/.."
OUT=build/ships/fx_ramflame
HODOR="C:/Program Files (x86)/Steam/steamapps/common/Homeworld 347380/GBXTools/HODOR"
python tools/make_ramflame.py --dae
"$HODOR/HODOR.exe" -action=convert "-\$CONVERT_IN=$(pwd -W)/$OUT/fx_ramflame.dae" "-\$CONVERT_OUT=$(pwd -W)/$OUT/fx_ramflame.hod" \
    "-\$SHADER_MAP=$HODOR/SHADERS.MAP" < /dev/null > "$OUT/hodor.log" 2>&1 || true
[ -s "$OUT/fx_ramflame.hod" ] || { cat "$OUT/hodor.log"; echo "HODOR did not write $OUT/fx_ramflame.hod"; exit 1; }
echo "$OUT/fx_ramflame.hod: $(stat -c %s "$OUT/fx_ramflame.hod") bytes"
python tools/make_ramflame.py
