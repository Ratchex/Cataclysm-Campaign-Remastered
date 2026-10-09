# Session handoff: Cataclysm → HWRM port

Last updated 2026-10-08 (evening). Read this first, then `C:\Modding\Cataclysm-decomp\PORT_PLAN.md` (plan and decisions),
`NOTES.md` (HWRM engine rules learned in game) and `C:\Modding\Cataclysm-decomp\MODLOG.md` (reverse-engineering
findings).

## RESUME HERE (updated 2026-10-08, last commit 0839211)
**Console start:** run `claude` from `C:\Modding\Homeworld` (that loads the project memory), then say "resume from
Cataclysm-HWRM/HANDOFF.md". Shells: Git Bash for anything that runs HODOR; `powershell -File launch.ps1` to launch.
The user plays every test; Claude launches the game, reads logs and never sends input. After each test the user
says "game closed": check with `Get-Process HomeworldRM` only for processes newer than the launch (about 18 stale
HomeworldRM processes from crashed exits refuse to be killed until a reboot).

User's direction: set up each mission's units as we reach that mission, and play each part against the original
(user compares in game; one constant per tweak; offer to drop fiddly cosmetics). Done: the Kuun-Lan (core + module
subsystems), the Worker (animations, harvest / repair), Mission 1's opening (both cutscenes, the fleet's arrival)
and, this session, Mission 1's battle behaviour (below). Current goal: the rest of Mission 1, as the user finds
differences; then the hyperspace exit so Mission 1 can be finished.

**Pipeline** (all in `C:\Modding\Cataclysm-HWRM`):
1. `bash tools/build_kuunlan.sh` - core (`build/ships/som_mothership`, Command Center + Resource Processing merged in:
   make_modules.py CORE_PARTS) + 11 module models (`build/ships/smt_kl_<key>`).
   Other ships: `bash tools/build_ship.sh race_sect/<ship> som_<name>` (sworker, srecon, sacolyte).
2. `python tools/make_modules.py` - module table -> `data/subsystem/smt_kl_*` and dummy ships `data/ship/smt_kl_*_dummy`.
3. `python tools/install_cr.py` - Cataclysm Remastered layer (git-ignored; only what their ships need: SKIP_PREFIX /
   KEEP_PREFIX, stale files removed) + patches + our models under their setups + Gearbox-style speeds (SPEEDS) +
   module slots on `smt_ms_sp.ship`. No CR .mad/.madstate on ships with our models unless we converted one.
4. `python tools/make_race.py` - SP build/research lists.
5. `python tools/build_mission.py 01 --intro n01` (level, `m01_kas.lua`, wrapper, `m01_paths.lua`) and the cutscenes:
   `python tools/nis2hwrm.py n01 --modules dockingbay,engineslower,enginesupper,lowerspine,orecanarmour`,
   `python tools/nis2hwrm.py nislet01`. Speech: `python tools/build_speech.py`. Music: `python tools/build_music.py`
   (gain 0.5, confirmed; the game locks a playing track, close it first).
6. `powershell -File launch.ps1`; read `Bin\Release\HwRM.log` (strip NULs). `python tools/luacheck.py` needs the user
   site packages (no `-I`). Don't pipe luacheck into `head` before `&& launch`.
Heredocs mangle backslashes and `\n` in Python edits: use the Edit tool or write a script file.

**This session (all confirmed in game unless marked):**
- **HWRM's skirmish AI was running the Taiidan and the Kushan** alongside the mission (unscripted attack-moves):
  now `CPU_Enable(p, 0)` for every computer player in KAS_StartEngine (Gearbox's KAS_CPUPlayerInit). Root cause of
  the wandering picket wings and the flank fight drifting into the main battle.
- Allies: Cataclysm's kasfTeamSwitchPlayerOwner hands the Kushan teams to the human; here they stay on allied player 2
  (not player-controlled, blue in the UI: `data/ui/ati/ati.lua`, stock with AlliedColour blue). 0x497ed0 =
  kasfShipsDeleteAfterHyperspace (no-op here). Allies fight the Taiidan.
- 0x495560 / 0x495620 = kasfShipsSelectEnemy / Friendly (human side = players 0+2 / computer), not capital/non-capital.
- kasfUniversePause/Unpause freeze every ship (speed 0, no attacks) during Fleet Intel's briefings;
  kasfOtherKASPause/Unpause pause other teams' rules and timers (HW1 Timer.c semantics).
- kasfPatrolPath = plain moves point to point (`SobGroup_FollowPath` is an attack-move, COMMAND_AttackMove 20).
- Still in place, possibly no longer needed now that the AI is off: non-player proximity sensors lose AB_Move
  (KAS_FreezeSensorArrays); every non-player ship on defensive ROE every 5 s (KAS_TeamsDefensive).
- Somtaaw speeds = Cataclysm maxvelocity x Gearbox's HW1 class ratio (Recon 514, Acolyte 459, Worker 144); the
  Kuun-Lan keeps CR's (user: more agile than HW1's Mothership). User: "immediately feels correct".
- Exit crash (heap corruption 0xc0000374 on every exit to the menu since the module dummies): NIS objects shared
  animation channels (n01 module dummies, nislet01 beam-kill effects) -> double free. nis2hwrm gives each object its
  own (own_channels). Found with ProcDump (`C:\Modding\tools\procdump`, NOTES.md "Debugging crashes").
- Positions are faithful (Cataclysm x 0.35, checked against the user's screenshot of the original); perceived
  "shorter distances" were the battles not freezing during briefings and the skirmish AI.

**Next, in order:**
1. Continue Mission 1 against the original (user's choice), then the hyperspace exit (`K_497290` is a stub) so it
   can be completed and Mission 2 started.
2. Then Missions 02-17 with `build_mission.py`, setting up each mission's ships as they appear.
Open, lower priority: whether the sensor freeze / blanket defensive ROE can go; Support units (SU); Siege Cannon
weapon; Support modules per mission (1 for now); losing engine modules should slow the Kuun-Lan; the Kuun-Lan
arrives unrotated (HyperspaceTo ignores StartPointPlayer's -241 degree heading); uncommented API name comments in
generated m01_kas.lua still say SelectCapital/NonCapital (kas2lua reads names from kas_api.tsv, cosmetic).

**Facts from this session** (details in NOTES.md): Cataclysm's Kuun-Lan has only two Worker docks (Res0/Res1, the
nose pads; RES2-10 in its .mex are unused). Module functions come from english.script `str*ModuleInfo` (Hangar =
drives/linking + ship production, Armour, Weapons, Engineering = sMothershipMicro, Adv. Engineering =
sMothershipSpecial, Resource Processing = sMothershipEngineering). All modules attach at the Kuun-Lan origin;
Support modules at SUPPORT1-12 (pairs share a point, one turned 180 degrees about Y). Worker docking needed CR's
path shapes (straight oriented paths never docked). `StartShipWeaponConfig` arg 4 = firing animation in .events.

## Repositories
| Path | What |
|---|---|
| `C:\Modding\Cataclysm-decomp` | Ghidra project, decompile exports (`out/`), extractors (`tools/`), catalogue, plan. `extracted/` and `reference/` are git-ignored. |
| `C:\Modding\Cataclysm-HWRM` | The mod. `data/` is junctioned into the game as `HomeworldRM\DataCataclysm`. `tools/` builds it. |
| `C:\Modding\Homeworld\gardens-of-kadesh-1.2.2` | HW1 source (KAS, kas2c, audio codec); referenced, not modified. |

## Decisions (user)
- Stage A: faithful local port as a custom campaign. Stage B later: Workshop compliance.
- Where Cataclysm and HWRM behaviour conflict, use HWRM's. Original models for Stage A; art later. Tutorial: undecided.
- The user drives the game during tests (Claude launches it and reads `HwRM.log`, never sends input).

## How to run
- `powershell -File C:\Modding\Cataclysm-HWRM\launch.ps1`, then Single Player Game → Extra Missions → Homeworld Cataclysm.
- Log: `...\HomeworldRM\Bin\Release\HwRM.log` (strip NUL bytes before grepping). Mission `print()`s appear there.
- Rebuild a mission: `python tools/build_mission.py 01 --intro n01` (default fleet: their Kuun-Lan, 3 Recon, 2 Workers).

## Phase 0 status
| # | Item | Status |
|---|---|---|
| 0.1 | Campaign skeleton | Done. Rules in `NOTES.md` (keeper.txt, `<campaign>.dds`, createSOBGroup before addToSOBGroup, launch args). |
| 0.2 | Level converter `mission2level.py` | Done; matches Gearbox's HW1 conversions; Mission01 layout checked in game. Resources/AIBox/derelicts/mines not converted yet. |
| 0.3 | One Somtaaw ship end to end | **Done** (confirmed in game: look, size vs Kus_Carrier, no loose parts). Kuun-Lan is now core + module subsystems: `bash tools/build_kuunlan.sh` (see RESUME HERE). |
| 0.4 | Speech/subtitles; localized `$IDs` | **Done.** `build_speech.py` makes one 44.1 kHz WAV + speech.dat string per phrase; runtime plays them via Subtitle_AddSkippable. Confirmed in game (lines, subtitles, objective text). |
| 0.5 | NIS cutscenes | **Done** (n01 confirmed in game: cameras, cuts, zoom, speech, choreography). `tools/nis2hwrm.py <name>`; Mission01 plays n01 first (`build_mission.py --intro n01`). Open items in NOTES.md. |
| 0.6 | KAS API naming | Partial. `out/kas_usage.tsv`: 302 functions used; confident names only for the first third of the API. Verified names in `out/kas_api_overrides.tsv`. Tools: `kasalign.py`, `kasverify.py <Mission>`. |
| 0.7 | C → Lua translator | **Done.** Mission01 runs from translated code: no Lua errors, teams start, objectives appear with real text after ~30s. 38/108 KAS functions implemented; others are logged stubs. |

## Key technical facts
- KAS name hashes: ELF hash on uppercased bytes; bit 31 set = global variable/timer, else scoped to mission/team.
- kas2c compiles message handling into a loop that pops each queued message (FUN_00417ec0) and binary-searches
  its hash; kasExecute runs mission watch, then each team's FSM watch, then its state watch.
- Translated code calls `K_<addr>(...)` (KAS API by exe address; name in a comment). Implement in
  `data/scripts/scar/cataclysmkas.lua`; stubs are generated in `cataclysmkas_stubs.lua` by `make_kas_stubs.py`.
- Lua 4 in HWRM: no goto/booleans/bit ops/`%`; 0 is true. The translator emits explicit `~= 0` tests and a `_pc`
  dispatcher for goto-heavy functions.
- Mission01 starting fleet (observed in the original): Kuun-Lan + 3 Recon + 2 Worker. Cataclysm mission files do not
  place the player's fleet; still to find how the game does it for later missions.
- Allied Kushan teams are probably moved to the player's side with kasfTeamSwitchPlayerOwner (Mission01 calls it 5x).
- Gotcha: don't pass regexes with backslashes through bash heredocs into Python edits; write a script file.

## Lessons from getting Mission01 to run (all fixed; details in NOTES.md / MODLOG.md)
- Translate KAS calls by address only (Ghidra names them K_<addr>); names drift as they are verified.
- The SP engine talks to missions via G_ variables (G_PlayNislet / G_Nislet%dComplete / G_ShipsHaveArrived);
  the runtime emulates them, giving cutscenes 5 s so teams don't start before the level's groups are filled.
- SobGroups need SobGroup_SetSwitchOwnerFlag(group, 0) or ships leave them on owner change.
- Timers follow HW1 Timer.c: an existing timer that isn't running counts as expired.
- Runtime traces (`CKAS msg/got/jump/speech`) in HwRM.log show the mission flow; set KAS_TraceMsgs = 0 to silence.

## Next steps
1. Mission01: implement the stubs the run hits (orders: Guard/Patrol/MoveTo/Stop/Launch/Dock; pings; sensors;
   tutorial pointers; purchase/tech; ~15 unnamed ones) and check objectives complete as the original does.
2. Then build Missions 02-17 with `build_mission.py` and fix what each one hits.
3. Then the remaining level conversions, more Somtaaw/Beast ships, and the other cutscenes (nislet01 next).

## Cataclysm Remastered (HWU-based workshop mod) as an asset source (user's idea, 2026-10-08)
- Workshop 2195601016 "Homeworld: Cataclysm (Beast Update)" v2.1 (HWRM 2.0/2.1), extracted with
  `Cataclysm-decomp/tools/hw2big.py` to `Cataclysm-decomp/reference/cr_beast` (not tracked). Older 2.0 beta: 416844570.
- 33 Somtaaw ships (smt_*: ms/ms_sp Kuun-Lan, worker, scout=recon, acolyte, acv, mcv, mimic, rammingfrigate,
  processor, hive/multibeam frigates, destroyer, carrier, dreadnought, sentinel, swarmer, drones...), 42 Beast (bst_*),
  Kuun-Lan modules as subsystems (ksh_sec_ms_*), a started "beastwar" campaign (2 missions, Somtaaw build/research).
- Models mostly from HWU (HW2 mod). Permission needed before any Workshop release (HWU in indefinite maintenance);
  keep a list of every file used. Plan: their models/effects, our Cataclysm stats; our converter as fallback.

## Cataclysm Remastered setup on our models (confirmed in game)
- `tools/install_cr.py` installs CR's files, then puts our models (`build/ships/som_*`, from `tools/build_ship.sh`)
  under their `smt_ms_sp`, `smt_worker`, `smt_scout`, `smt_acolyte` (OUR_MODELS joint maps, OUR_EVENTS). Rebuild a
  model, then rerun `install_cr.py`. Worker docking/unloading, Acolyte guns + effects, trails, Recon glow confirmed.
- Music: `tools/build_music.py` (Cataclysm's 62 streams, gain 0.5 confirmed); `kasfMusicPlay(n)` = stream n.
- Next: Kuun-Lan side docks (9 Cataclysm RES points unused), real Kuun-Lan modules, the n01 `startMusic` cue.

