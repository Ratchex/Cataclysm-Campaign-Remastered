# Session handoff: Cataclysm → HWRM port

Last updated 2026-10-08. Read this first, then `C:\Modding\Cataclysm-decomp\PORT_PLAN.md` (plan and decisions),
`NOTES.md` (HWRM engine rules learned in game) and `C:\Modding\Cataclysm-decomp\MODLOG.md` (reverse-engineering
findings).

## RESUME HERE (session of 2026-10-08, last code commit f2231c8)
User's direction: set up each mission's units as we reach that mission. Current goal: the Kuun-Lan fully working
(side docks + every module as an HW2 subsystem, Cataclysm Remastered's Kuun-Lan as the template), then the
Worker's leg / resource-harvest animations and effects.

**Pipeline now** (all in `C:\Modding\Cataclysm-HWRM`; anything that runs HODOR from Git Bash):
1. `bash tools/build_kuunlan.sh` - core (`build/ships/som_mothership`, Command Center + Resource Processing merged in:
   make_modules.py CORE_PARTS) + 11 module models (`build/ships/smt_kl_<key>`).
   Other ships: `bash tools/build_ship.sh race_sect/<ship> som_<name>` (sworker, srecon, sacolyte).
2. `python tools/make_modules.py` - module table (MODULES, HARDPOINTS, TECH_MODULE) -> `data/subsystem/smt_kl_*`
   (.subs + .hod) and dummy ships `data/ship/smt_kl_*_dummy` (loose/jettisoned modules; Cataclysm's
   sMothership<Module> types map to them in `tools/shipmap.tsv`).
3. `python tools/install_cr.py` - Cataclysm Remastered base layer (git-ignored) + patches + our models under their
   setups (OUR_MODELS/OUR_EVENTS) + module slots appended to their `smt_ms_sp.ship`.
4. `python tools/make_race.py` - SP build/research lists (ships need the Hangar; techs need their module).
5. `python tools/build_mission.py 01 --intro n01` (writes `KAS_StartModules` from the .mission IncludeShips) and
   `python tools/nis2hwrm.py n01 --modules dockingbay,engineslower,enginesupper,lowerspine,orecanarmour`.
6. `powershell -File launch.ps1`; the user plays; read `HwRM.log` (strip NULs). Close the game before rebuilding music.

**Done this session:** fix 1 (64934fb, confirmed in game: all modules show; HwRM.log "7 modules", no create
errors): every module is in sp_build.lua (else SobGroup_CreateSubSystem refuses it), the structural ones are
restricted 1 s after the starting modules exist (KAS_StructuralModules). Then, by the user's decision (c2b2041,
not yet tested in game): Command Center and Resource Processing are part of the core model, not modules (on the
Kuun-Lan in every mission; their Cataclysm types map to nothing in shipmap.tsv); Lower Engines and Lower Spine
stay separate modules (the user chose not to merge them: Cataclysm loses the spine at Mission 4, the engines at 5).
Confirmed in game: the core shows them, Mission 1 starts with 5 modules (HwRM.log "5 modules", 4 restricted), Workers
unload at the core. Then (9dbac5c, confirmed in game: Acolytes dock / launch without passing through the Hangar,
Workers unaffected): the Hangar is a ~480-unit box under the core with the DB points inside, and the paths' first
waypoint (~315 out) was at its corner, so ships flew through it; fighter / corvette paths now start from an outer
waypoint (geo2dae.py OUTER_APPROACH: 2400 / 2800 HW1 units out) and launches leave all the way out.

Then the Worker (f2231c8, confirmed in game: "actually perfect"): Cataclysm's sworker.mad converted
(tools/mad2hwrm.py; animated objects are joints via geo2dae --anim-joints): clamps open docked / close on launch
and on n01's cues, boom out (5 deg less than Cataclysm's) before the stock HW1 harvest / repair beams, which start
at fixed markers; hovers 45 off the rock (LatchOrientation joint); RepairCommand enabled. Build: `bash
tools/build_ship.sh race_sect/sworker som_worker` (per-ship args in build_ship.sh), then install_cr.py; our
.events / .madstate live in tools/overrides/.

To fix next, in order:
1. Other animated Somtaaw ships the same way (sworker pattern: --anim-joints, mad2hwrm, tools/overrides madstate).
Open, lower priority: Support units (SU); Siege Cannon weapon; how many Support modules each mission starts with
(1 for now); losing engine modules should slow the Kuun-Lan; n01 `startMusic` cue; hyperspace exit (`K_497290`).

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

