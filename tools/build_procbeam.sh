#!/usr/bin/env bash
# The Processor's repair beam cone mesh (tools/make_procbeam.py --dae, HODOR) and its effect files. Then
# tools/install_cr.py. Run from Git Bash (HODOR).
set -e
cd "$(dirname "$0")/.."
OUT=build/ships/fx_procbeam
HODOR="C:/Program Files (x86)/Steam/steamapps/common/Homeworld 347380/GBXTools/HODOR"
python tools/make_procbeam.py --dae
"$HODOR/HODOR.exe" -action=convert "-\$CONVERT_IN=$(pwd -W)/$OUT/fx_procbeam.dae" "-\$CONVERT_OUT=$(pwd -W)/$OUT/fx_procbeam.hod" \
    "-\$SHADER_MAP=$HODOR/SHADERS.MAP" < /dev/null > "$OUT/hodor.log" 2>&1 || true
[ -s "$OUT/fx_procbeam.hod" ] || { cat "$OUT/hodor.log"; echo "HODOR did not write $OUT/fx_procbeam.hod"; exit 1; }
echo "$OUT/fx_procbeam.hod: $(stat -c %s "$OUT/fx_procbeam.hod") bytes"
python tools/make_procbeam.py
