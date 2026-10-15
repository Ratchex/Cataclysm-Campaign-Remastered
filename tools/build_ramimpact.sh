#!/usr/bin/env bash
# The Ramming Frigate's impact bowl mesh (tools/make_ramimpact.py --dae, HODOR) and its effect files. Then
# tools/install_base.py. Run from Git Bash (HODOR).
set -e
cd "$(dirname "$0")/.."
OUT=build/ships/fx_ramimpact
HODOR="C:/Program Files (x86)/Steam/steamapps/common/Homeworld 347380/GBXTools/HODOR"
python tools/make_ramimpact.py --dae
"$HODOR/HODOR.exe" -action=convert "-\$CONVERT_IN=$(pwd -W)/$OUT/fx_ramimpact.dae" "-\$CONVERT_OUT=$(pwd -W)/$OUT/fx_ramimpact.hod" \
    "-\$SHADER_MAP=$HODOR/SHADERS.MAP" < /dev/null > "$OUT/hodor.log" 2>&1 || true
[ -s "$OUT/fx_ramimpact.hod" ] || { cat "$OUT/hodor.log"; echo "HODOR did not write $OUT/fx_ramimpact.hod"; exit 1; }
echo "$OUT/fx_ramimpact.hod: $(stat -c %s "$OUT/fx_ramimpact.hod") bytes"
python tools/make_ramimpact.py
