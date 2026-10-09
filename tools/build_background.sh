#!/usr/bin/env bash
# Build a Cataclysm mission background's sky model (tools/make_background.py --sky: texture + sphere DAE, HODOR,
# then --splice: the stock lights) into build/backgrounds/<name>/, for tools/install_cr.py. Git Bash only: HODOR
# spins forever when Python/PowerShell start it.
# Usage: tools/build_background.sh <name>   (name, .btg and offsets from make_background.py BACKGROUNDS)
set -e
MOD="$(cd "$(dirname "$0")/.." && pwd -W)"
NAME="$1"
read -r BTG THETA PHI < <(python -c "import sys; sys.path.insert(0, '$MOD/tools'); import make_background as m; b, t, p = m.BACKGROUNDS['$NAME']; print(m.BIG + '/' + b + '.btg', t, p)")
python "$MOD/tools/make_background.py" "$BTG" "$NAME" --theta "$THETA" --phi "$PHI" --sky
OUT="$MOD/build/backgrounds/$NAME"
HODOR="C:/Program Files (x86)/Steam/steamapps/common/Homeworld 347380/GBXTools/HODOR"
"$HODOR/HODOR.exe" -action=convert "-\$CONVERT_IN=$OUT/${NAME}_light.dae" "-\$CONVERT_OUT=$OUT/${NAME}_light.hod" \
    "-\$SHADER_MAP=$HODOR/SHADERS.MAP" < /dev/null > "$OUT/hodor.log" 2>&1 || true
grep -v -e '^X*$' -e 'Building LMIP' "$OUT/hodor.log" | sed 's/^/  /'
[ -s "$OUT/${NAME}_light.hod" ] || { echo "HODOR did not write $OUT/${NAME}_light.hod"; exit 1; }
python "$MOD/tools/make_background.py" - "$NAME" --splice
