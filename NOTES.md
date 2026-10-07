# HWRM engine notes

Learned in Phase 0.1 (2026-10-07). Each was confirmed in game.

## Launching a loose-file mod
- `-moddatapath DataCataclysm -overrideBigFile` (path relative to `HomeworldRM\`). The mod root **must contain
  `keeper.txt`** (copied from Homeworld2.big) or the folder is not used as a data root.
- Launch with `-dlccampaign HW1Campaign.big -moviepath DataHW1Campaign` as the HW1 launcher button does.
  Launching the exe with no campaign arguments gives a front end that crashes (`luaconfig/799 CreateRef`).
  `-campaign <name>` restricts Single Player to that one campaign; omit it to see Extra Missions.
- `-windowed` gives an offset UI on this machine; leave it off. `-w/-h/-LogFile` are not engine options.
- Log: `Bin\Release\HwRM.log` (UTF-8 with NUL bytes). `print()` from mission Lua appears in it.

## Campaign file
- Mod campaigns are Extra content: `contentType = 2`, with `contentThumbName`/`contentThumbDesc`, no
  `ExtFilter`/`contentRules` (pattern from stock `rr_oem.campaign` and the Taiidan Republic mod).
- **Every `.campaign` file needs `leveldata/campaign/<contentName>.dds` beside it** (1024x512 BGRA8888 with
  mips). Without it the Single Player screen crashes with `CreateRef FATAL EXIT` - even when another campaign
  is selected, because all campaign files are parsed.
- Mission thumbnails: `ui/mapthumbnails/campaign/<contentName>/<directory>.dds`.
- `contentOrdered = 1` locks missions until the previous one is won.

## Levels
- **`createSOBGroup(name)` before `addToSOBGroup(..., name)`.** Adding to a missing group is an access
  violation (native crash), not a Lua error.
- `raceName = "Kushan"` / `"Taiidan"` works for HW1 races in a mod campaign (with the HW1 DLC loaded).

## Scripts
- `dofilepath("data:scripts/SCAR/KASUtil.lua")` and the other four HW1 emulation files load fine from a mod
  mission; `OnStartOrLoad`, `OnInit`, `Rule_AddInterval`, `Objective_Add`/`Objective_SetState` all work.

## Localized strings and speech (Phase 0.4, confirmed in game)
- Loose `locale/english/...dat` files listed in the mission's `datfiles.lua` work. The `.dat` **must end with
  `rangeend`**, otherwise HwRM.log says "LOCALIZER -- Missing final range end" and every `$ID` shows raw.
  IDs must lie inside a `filerange`; 4200000 was out of range ("Requested string range doesn't exists").
- Speech: `Sound_SpeechSubtitlePath("speech:missions/<folder>/")` in OnStartOrLoad, then
  `Subtitle_AddSkippable(actor, "$<id>", secs)` plays `data/sound/speech/missions/<folder>/<id>.wav` and shows
  string `<id>` as the subtitle. WAVs must be 44.1 kHz: 22050 Hz files play chipmunked (no resampling).
- The actor sets the portrait shown above the subtitle; the subtitle text is shown without a speaker prefix
  being added, so Cataclysm's own "Tactical Officer: ..." text appears once.
- Cataclysm actor bits in speech events: 0x1000 Fleet Command, 0x2000 Tactical Officer, 0x8000 other fleets.

## Level conversion (Phase 0.2, `tools/mission2level.py`)
- HW1/Cataclysm → HWRM: position `{-0.35x, 0.35z, 0.35y}`, yaw `rot - 90`, sphere radius `× 0.175`, inner bounds
  `0.35 × (sizeX, sizeZ, sizeY)`, outer `1.2 × inner`. `.missphere` positions are absolute.
- Verified with `tools/compare_level.py` against Gearbox's converted HW1 Mission01/05/10: every common squadron,
  point and sphere matches (tolerance 1 unit), except Gearbox's hand edits (Mission01 `SalvageTrialPING`, extra
  `PlayerStartPoint*` and `ExtraRes`) and its type substitutions for HW1 ships HWRM dropped
  (now in `make_shipmap.py`). Gearbox writes some yaws as `{180, 90 - rot, 180}`; same orientation.
- Ownership: labelled teams → player 1, CryoTray → player 0, others → the MissionSphere's player.
- `tools/shipmap.tsv`: 32 of Cataclysm's 36 Kushan/Taiidan types map to existing `Kus_`/`Tai_` ships; Somtaaw,
  Beast, Turanic, Traders and derelicts need new ships (Phase 1); `--placeholder` fills them meanwhile.
- Not converted yet: `Resources` (asteroid/dust fields from `.dist` files), `AIBox`, `Derelict`, `Mine`.
- **Cataclysm missions do not place the player's fleet.** Their only RACE_SECT entries are empty KAS teams
  (FleetIntel, Objectives, Music). `sMothership` is referenced only by mission code from Mission05 on, so the
  starting fleet comes from game code or persistence; HWRM's equivalent is `startingplayerfleet.lua` +
  `usedefaultpersist`. To find in the decompile (Phase 0.6/0.7).

## HWRM Lua (learned in Phase 0.7)
- HWRM refuses to redefine a global function ("Cannot overwrite function X"); the later definition is ignored.
  So generated stubs must not define what `cataclysmkas.lua` implements (`make_kas_stubs.py` skips them).
- Lua 4 has no block comments: `--[[note]]` comments out the rest of the line. Generated code puts notes only at
  line ends; `luacheck.py` rejects `--[[`. A syntax error makes `dofilepath` fail silently except in the log, and
  the mission then dies with "could not find OnInit" / FATAL EXIT.
- SobGroups drop ships that change owner unless `SobGroup_SetSwitchOwnerFlag(group, 0)` (Gearbox does this in
  KASSobGroup_Create). Without it a KAS team emptied itself after kasfTeamSwitchPlayerOwner.
- **A `.dat` string table must end with a `rangeend` line** (after `filerange A B` / `rangestart A B` / `ID<TAB>text`).
  Without it the log says "Missing final range end" and every `$ID` stays raw. Loose `locale/english/...dat` files
  in the mod folder work once this is fixed; IDs 2100000+ are fine.
- Speech: `Sound_SpeechSubtitlePath("speech:missions/<folder>/")` + `Subtitle_AddSkippable(actor, "$<id>", secs)`
  plays `data/sound/speech/missions/<folder>/<id>.wav` (44.1 kHz mono 16-bit, as stock) and shows string <id> as the
  subtitle; it returns the line's real duration. Actors are engine globals (Actor_HW1_FleetIntel, ...).
