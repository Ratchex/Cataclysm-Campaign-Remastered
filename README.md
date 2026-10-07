# Cataclysm-HWRM

Homeworld: Cataclysm ported to Homeworld Remastered as a custom campaign. **Stage A (local only):** built from
the original game's data; do not distribute. Plan and status: `C:\Modding\Cataclysm-decomp\PORT_PLAN.md`.
Source data and tools: `C:\Modding\Cataclysm-decomp` (extracted assets, decompiled missions, catalogue).

## Run
1. One time: `cmd /c mklink /J "<HomeworldRM>\DataCataclysm" "C:\Modding\Cataclysm-HWRM\data"`
2. `powershell -File launch.ps1`
3. Single Player Game > Extra Missions > Homeworld Cataclysm.

## Layout
- `data/` - loose mod files (what the game loads)
- `tools/` - build helpers (`make_dds.py`: BGRA8888 DDS with mips, for campaign tiles and thumbnails)
- `NOTES.md` - engine behaviour learned while porting (read before changing campaign/level plumbing)
