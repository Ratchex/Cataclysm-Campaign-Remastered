# Session handoff: Cataclysm → HWRM port

Last updated 2026-10-09 (late). Read this first, then `C:\Modding\Cataclysm-decomp\PORT_PLAN.md` (plan and decisions),
`NOTES.md` (HWRM engine rules learned in game) and `C:\Modding\Cataclysm-decomp\MODLOG.md` (reverse-engineering
findings).

## Kuun-Lan effects, lighting, voices: DONE (2026-10-09, confirmed in game)
- Kuun-Lan: running lights (NAVL from Cataclysm's .mex Nav + .shp, all our models), emissive maps (CR's GLOW maps,
  boosted x1.35 except engines), CR's engine trail shape + our burn flames, the command module's spinning gravity
  generator (geo2dae --anim-geo, smt_ms_sp.madstate). NOTES.md "Ships and HODOR".
- Mission 1 lighting: ez14 relit with Cataclysm's mission01.hsf (make_background.RELIGHT, at install). Fog (step 2)
  not needed so far.
- Voices: Cataclysm's Somtaaw unit barks per ship type and Fleet Command as the Somtaaw race announcer, module
  online, Link/Unlink and tech-available lines (NOTES.md "Unit barks and the announcer"). Rebuild:
  tools/build_speech.py + tools/make_unitspeech.py (audio, git-ignored) then install_cr.py. Range: RANGE_GRANT_ALL 0
  now (research testing); set 1 for upgraded test ships.

## Mission 1 cosmetics detour: DONE (2026-10-09, confirmed in game)
- Team colours per faction (tools/make_colours.py, teamcolour.lua, KAS_ApplyColourSchemes; m01_paths.lua loads
  again: Lua 4 constructors need `;` between named and list items). Reinforcement groups keep their player's
  colours (not done).
- Somtaaw stripes: colours baked into our models' DIFF textures (NOTES.md "Ships and HODOR"); all models and Kuun-Lan
  modules rebuilt; build_kuunlan.sh now installs the modules (make_modules.py).
- Cutscenes: colourSchemeTrail (engine trails in the faction colour); n01 shows the Kuun-Lan's 5 modules again
  (nis2hwrm.py NIS_MODULES default, a regeneration had dropped them).
- Sky: stock ez14 for Mission 1 (NOTES.md "Backgrounds"); bloom left as is for now (user watches it).

## RESUME HERE (updated 2026-10-09, after the damage conversion; see git log for the last commit)
**Console start:** run `claude` from `C:\Modding\Homeworld` (loads the project memory), then say "resume from
Cataclysm-HWRM/HANDOFF.md". Shells: Git Bash for anything that runs HODOR (tools/build_ship.sh); `powershell -File
launch.ps1` to launch. The user plays every test; Claude launches, reads `Bin\Release\HwRM.log` (strip NULs) and never
sends input. "Game closed" = no HomeworldRM process *with threads* (`Get-Process HomeworldRM | Where-Object
{ $_.Threads.Count -gt 0 }`); ~20 dead 0-thread records linger (Access denied on kill, harmless, cleared by a Steam
restart / reboot). Say what each change needs: .ship/.wepn/.subs/custom code/fx/research = full relaunch; level and
mission scripts (cataclysmkas.lua, m01_*.lua) reload on going back to the menu.

User's direction: faithful port, play each part against the original (one constant per tweak; offer to drop fiddly
cosmetics). **Balance comes from our translated Cataclysm values** (costs, speeds, RU, later health/damage), Cataclysm
Remastered (CR) only for unit setup/logic (memory: balance-from-cataclysm). Rank stars must be real UI beside the stance
icon (not possible from script; message only for now; revisit). Current goal: **get the Acolyte complete for the whole
campaign**, building engine-wide systems (abilities, upgrades) on the way.

**Pipeline** (all in `C:\Modding\Cataclysm-HWRM`): as before (build_kuunlan.sh / build_ship.sh, make_modules.py,
install_cr.py, make_race.py, build_mission.py, nis2hwrm.py, build_speech/music), plus:
- `python tools/make_upgrades.py` (upgrade tables read from cataclysm.exe -> data/scripts/cataclysm/upgrades_gen.lua)
- `python tools/make_abilities.py` (ability buttons/commands -> ui/newui/{newtaskbar,commanduidefines}.lua,
  taskbar/cat_abilities.lua, scripts/cataclysm/abilities_gen.lua)
- install_cr.py runs make_shipcode.py (hooks shiprules.lua into every campaign ship, chaining their custom code)
- `python tools/make_rankfx.py` (rank star fx, unused while stars are off)
Order after editing abilities/upgrades: make_upgrades -> make_abilities -> make_race (if research changed) ->
install_cr. Heredocs mangle backslashes in Python edits: use the Edit tool or a script file (bit me ~6 times).

**This session (2026-10-09), all confirmed in game unless marked:**
- Data layers: **Players Patch 2.3** (workshop 1190476337, extracted to Cataclysm-decomp/reference/players_patch) under
  CR under ours; fixes the "only the lead fires" formation bug (confirmed); its HW1 ships are our Kushan/Taiidan;
  install never overwrites git-tracked files.
- `data/scripts/cataclysm/shiprules.lua` (custom code on all 63 campaign ship types): **pilot experience** (kills per
  victim class, Cataclysm's weights/thresholds, x1.1 damage+speed per rank, rank-up message; stars off), **damage slows
  ships**, **Link/Unlink** (pair, fly together, swap ship with health/kills; confirmed only selected Acolytes link),
  **upgrades**, **abilities**. Ship scripts run in a separate Lua state from the mission: they communicate through
  named SobGroups. A Lua error in ship code is a fatal exit (Lua 4 call() can't catch engine errors).
- CR weapons did 0 damage to HW1 armour: install patches `_hw1` armour families in (confirmed: Acolytes now hurt the
  Taiidan). Asteroids worth Cataclysm RU (10x HW1), RU trickle, Cataclysm build cost/time, Worker speed 208.
- **Abilities** (make_abilities.py): HWRM keeps ONE CustomCommand per ship (tested). Each ship type has one *native*
  ability (engine button + right-click + energy bar; energy spec per ability in ENERGY) and any number of *button*
  abilities (our taskbar buttons -> MainUI_ScarEvent -> mission script fills cat_cmd_<name> -> ships act if also
  SobGroup_Selected). Acolyte: native **Fire Missiles** (energy bar = missile cooldown, 20.75 s), button **Link**;
  ACV: native **Unlink**; every upgradable type: button **Upgrade**. A native command is on only once the ship has
  its upgrade (AB_Custom per ship).
- **Upgrades** (make_upgrades.py reads cataclysm.exe: research -> ability bits, per-type masks, armour caps, times):
  Upgrade command (timed; strike craft dock and relaunch), any docking of an UpgradeByDocking ship (instant), new
  ships, kasfShipsUpgrade (0x498c70, renamed from kasfResetShipRenderFlags; every Mission01 team runs it at start).
  Abilities are upgrades (Link needs the LINK upgrade). Advanced Drive +0.15 speed.
- **Acolyte missiles** (ORDINANCE): two cat_acolytemissile "Special Attack" weapons on Weapon_GUN2/GUN3 that fire in
  normal attacks only while UseSpecialWeaponsInNormalAttack is on: granted to Acolytes by research
  CAT_ACOLYTE_MISSILES (make_race RUNTIME_RESEARCH, granted at mission start), switched per ship (confirmed: none
  before the upgrade, missiles after, Upgrade adds them). Dead ends recorded in NOTES.md (weapon subsystems).
- Development switches, **keep empty in commits**: cataclysmkas.lua KAS_DevTechs / KAS_DevModules, shiprules.lua
  CatDevUpgrades (e.g. { ORDINANCE = 600 }: game time includes the opening cutscene).

**Not yet confirmed in game** (check next session): instant upgrade on any docking; kasfShipsUpgrade at mission start;
the Fire Missiles bar refill time (~21 s = energy recharge is per second; ~2 s = percent, rescale ENERGY); Fire
Missiles disabled before the upgrade (no energy spent); missiles in normal combat again (volley = 0).

**Next, in order (the Acolyte, then the rest):**
1. **Energy Cannons: SHELVED by the user (2026-10-09)** after the in-hangar swap failed in game (NOTES.md "Weapon
   upgrades"). What stays: the WEAPON_ENERGY upgrade, recorded per ship from the exe's weapon-level rules (19
   Somtaaw/Beast types; make_upgrades.py), for the damage conversion to use; the variant machinery
   (tools/ship_variants.py, shiprules.lua CatVariant_*, data/weapon/cat_acolyteenergy) is off (VARIANTS empty).
   Untried ideas: swap in open space at the hangar exit (Link's spawn/despawn work), or only build the variant after
   the research.
2. **Health + damage conversion: DONE** (tools/make_damage.py in install_cr; commit a018787; user: "feels good").
   Answers: all ships, Cataclysm 1:1; CR accuracy rolls kept; armour levels later; missiles 1:1. Left: Beast ships,
   mines, Somtaaw ramming frigate (no Cataclysm guns), armour upgrade levels (TECH_ARMOUR2/3: no per-ship incoming
   multiplier in HWRM), the Energy upgrade's damage (could be SobGroup_SetDamageMultiplier x energy/projectile per
   ship, now that Energy Cannons are shelved).
3. **DONE (2026-10-09):** our ACV model (som_acv from sacv), the Acolyte's animations (combat wings, Link / Unlink
   with Cataclysm's clips; NOTES.md "Link / Unlink animation"), and the **Unit test range** (campaign entry 1) for
   trying units outside the missions. ACV muzzle flashes and balance done. **Mimic disguises DONE (2026-10-10,
   user-tested):** Mimic button opens a menu of disguises (tools/ship_variants.py DISGUISES: each its own ship type,
   the Mimic swapped in place and kept selected, painted in the target's colours, untargetable; Unmimic swaps back;
   lines 165/166). Research: Fighter Drive + Holographic Emitter. Left: Mimic kamikaze (kamikazeDamage 1000, blast
   275, Quantum Explosive Charge; line 167), asteroid / crate disguises, MCV frigate disguises, Advanced Sensors
   detection; ACV EMP (TECH_EMP). Also done: Kuun-Lan module health bars (modules recentred on their hardpoints),
   its tactical overlay distances (stock kus_mothership).
4. Then Mission 1 against the original, the hyperspace exit (K_497290 stub), Missions 02-17.
Open, lower priority: rank stars as UI; Fire Missiles burst (HWRM can't fire weapons from script; user: keep as-is);
icons for our ability buttons (stock placeholders); sensor freeze / blanket defensive ROE (maybe unneeded since the AI
is off); Support units; Siege Cannon; engine loss slowing the Kuun-Lan; Kuun-Lan arrival heading.

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

