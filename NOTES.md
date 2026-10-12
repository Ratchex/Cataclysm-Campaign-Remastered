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

## Unit barks and the announcer (2026-10-09, confirmed in game)
- HWRM: soundscripts/speechlogic/{commands,status,chatter}.lua handlers call playSpeechActor(event, actor, voices,
  freq) / playSpeechActorLinked(..., link). Announcer actor = raceHelper() (Players Patch: Race_ID[currentRace] from
  player:racelist.lua -> Makaan / Emperor / Fleet); pilots = class + random voice ("Fighter_" with 3 -> Fighter_1-3).
  Files: allships/<actor>/<event>.wav flat for announcers; allships/<voice>/<event>/<event>.lua
  (randSampContainer = 1) + <event>_<n>.wav for pilots (.wav works, stock uses .fda).
- That Lua environment refuses redefining a global function ("Cannot overwrite function", the load then aborts and
  the speech logic is broken) and has no getn. So tools/install_cr.py patch_speech_logic() edits the Players Patch
  files from their pristine copy: loads data/soundscripts/cataclysm/catspeech.lua first, each handler stores its ship
  (CatSpeech_Ship), play calls go through CatSpeech_Play(Linked), construction complete / ship destroyed play
  Cataclysm's per-type line, raceHelper returns "cat_fleet" for Race_ID "Somtaaw".
- player:racelist.lua (Bin/Profiles/ProfileN) is written only by Players Patch's skirmish rules (SpeechRaceHelper);
  the campaign writes it at mission start (cataclysmkas.lua KAS_StartEngine). Without it the default Race_ID has no
  Somtaaw and the stock HW2 announcer speaks.
- Cataclysm's generic speech events (0-197; the variable is the ShipType, so barks exist per ship type) are not HW1's
  numbering and have no subtitles: transcribed locally (tools/transcribe_speech.py, faster-whisper small.en on CPU:
  the GTX 1080 Ti has no fast float16 and the CUDA build lacks cublas64_12.dll) -> Cataclysm-decomp/out/
  speech_text_sect.tsv; tools/make_unitspeech.py maps them (PILOT / FLEET tables): 0 selected, 1 move, 2 stop, 3 dock,
  4 docked, 5 attack, 6 cancel, 7/8 force attack, 9 cannot comply, 10 scuttle, 11 damaged, 12 dies, 13-15 tactics,
  17-25 battle chatter, 26-107 Fleet Command (hyperspace, research, construction per type 61, destroyed per type 101,
  hotkey groups 91-100 with the group as variable), 142-189 special abilities (cloak, gravwell, link 156/157, mimic
  165-168, worker harvest/salvage). Also wired (confirmed): module online (48, variable = module index: hangar,
  armour, engineering, advanced engineering, weapons), "<ship> is now available for construction" (52, only when the
  engine names the ship), Link / Unlink (shiprules.lua CatSay -> named group cat_say_<event> -> cataclysmkas.lua
  CatSayTick, KAS_SpeechBark: mission speech files, KAS_SpeechEnd untouched), the Tactical Officer's "<tech>
  available. Upgrade <ships>." (188, variable = TechnologyType: only REPAIR, SALVAGE, CRYSTAL_HARVEST have one) when
  the player gains the research, after "Research completed." + CAT_TECH_LINE_GAP 1 s. No generic "research available"
  line in Cataclysm. Mimic lines (165-168) wait for the Mimic. tools/build_speech.py now keeps events without a
  variable-0 line (base = phrase - variable of a variation-0 row).
- Unit test range (campaign entry 1): range.lua RANGE_GRANT_ALL 0 = all research available, none done (voice
  testing); 1 = everything researched and the placed ships upgraded.
- Alt-tabbing out of fullscreen HWRM can silence all 3D sound (weapons, explosions, engines) for the session
  (looked like a speech regression; confirmed by a clean rerun).

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
- **Switch the skirmish AI off for every computer player** (`CPU_Enable(p, 0)`, as Gearbox's KAS_CPUPlayerInit):
  left on, it commands the KAS teams' ships too (unscripted attack-moves: Mission01's picket wings crossed the map,
  flank fights drifted into the main battle). The runtime does it in KAS_StartEngine. Confirmed in game.
- `SobGroup_FollowPath` is an attack-move (`COMMAND_AttackMove` = 20; `COMMAND_Attack` = 2): kasfPatrolPath is plain
  point-to-point moves on the level path instead (mission2level writes `m<NN>_paths.lua`).
- Cataclysm's kasfTeamSwitchPlayerOwner hands Kushan teams to the human; here they stay on allied player 2
  (out of the player's control). 0x495560/0x495620 = kasfShipsSelectEnemy/Friendly (human side / computer).
  kasfUniversePause freezes every ship (speed 0, no attacks) while KAS runs on (Fleet Intel briefings).
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

## Ships and HODOR (Phase 0.3, confirmed in game)
- Pipeline: `tools/build_ship.sh` = `geo2dae.py` (Cataclysm .geo -> Collada + TGA) then HODOR (`.hod`) into
  `data/ship/<name>/`. Intermediates in `build/ships/` (git-ignored).
- HODOR: `HODOR.exe -action=convert -$CONVERT_IN=<dae> -$CONVERT_OUT=<hod> -$SHADER_MAP=<SHADERS.MAP>`.
  - Must be started from Git Bash. Started from Python, PowerShell (or bash spawned by Python) it spins at 100%
    CPU forever with no output; not the environment, stdio, cwd, console or error mode (all tested).
  - Forward-slash paths only. Textures: square power of two, >= 64 px, or it loops forever building mips.
  - Image id `IMG[<x>_DIFF]-image`, name `IMG[<x>_DIFF]_FMT[DXT1]`, effect `<diffuse><texture texture="IMG[..]-image">`;
    other ids segfault it. HODOR picks up `<x>_TEAM.tga` / `_STRP.tga` / `_PAIN.tga` next to `<x>_DIFF.tga` into
    the $team texture (SHADERS.MAP), but **team masks went wrong three ways in game** (whole hulls blue, then
    white, stripes never right): our models now **bake the Somtaaw colours into the DIFF** instead (geo2dae.py
    write_textures: Cataclysm's own formula, HW1 texreg.c trBufferColorRGB: texel x (1 - mask) + colour x mask,
    team then stripe; Somtaaw scalar 1, colpick.script has curves for the Taiidan only). Confirmed in game: grey
    hulls, blue panels, white stripes. Only the Somtaaw player uses these models. Stale _TEAM/_STRP files next to
    a DIFF are deleted (HODOR would pick them up).
  - RODOH only reads HW2 Classic HODs (does nothing on HWRM ones). The .hod texture data is one compressed POOL
    chunk: u32 3518, then three pools (packed, unpacked, data); pool 1 = all LMIPs' pixel data in order. Codec
    decompiled from HODOR.exe (a flag-word LZ, tools/hodpool.py reads it; packed == unpacked = stored, which HODOR's
    reader takes (the game: to confirm): ez14's sky texture is edited that way, make_background.py DARKEN).
  - Kuun-Lan modules reach the game through `make_modules.py` (data/subsystem, data/ship/*_dummy), not
    install_cr.py: build_kuunlan.sh runs it at the end (a rebuild once never reached the game).
- HW1 model space is X up, Y right, Z forward; HWRM = 0.35 * (-y, x, z) (proper rotation, winding kept: HW1
  polygons are already counter-clockwise around their face normal). 0.35 matches Gearbox's Kus_Carrier size.
- Stats: scale Cataclysm .shp values by Gearbox's ratios for the HW1 Kushan mothership (speed x0.96, health
  x1.75, rotation x0.4) until a better mapping exists.
- The Kuun-Lan core (smothership) is only the spine and 6 gimbals; its look comes from module ships stored in
  the core's frame (Mission01 includes Command, DockingBay, Engineering, EnginesLower/Upper, LowerSpine,
  OreCanArmour). For now they are baked into the hull; real modules need HWRM subsystems + hardpoint joints.

- **Collector dock paths** (Workers): copy Cataclysm Remastered's Kuun-Lan paths (`geo2dae.py --dock-from`),
  moved onto our nose RES points. What did not dock: stock Kus_Mothership flags (Player/Queue/ClearRes, no
  rotations) - Workers stopped short of the nose; CR's flags (Check/Queue, Close, tol 50, UseRot) on straight
  approaches along Cataclysm's RES normals with computed orientations - still no dock. CR's paths dock even with
  their latch moved onto our hull, so the approach shape/turns matter. Their waypoints rotate Z*Y*X (radians).
- Dock path segment record (64 B): pos 3f, rot 3f, u32 UseRot, f Tol, u32 Unfocus, f Speed, u32 Check, Close,
  Player, Queue, Clip, ClearRes; path header u32 6, 10, Exit, Latch, 0.
- `StartShipWeaponConfig`'s 4th argument names the firing **animation** in the .events (stock: the weapon joint's
  name, e.g. kus_interceptor `Weapon_Gun0`), whose events give the muzzle flash/sound.
- `NewShipType.upLOD/downLOD` switch to LOD 1: a LOD-0-only model vanishes at distance with them.

## Backgrounds (2026-10-09, confirmed in game)
- User: use a stock HWRM / HW2RM sky; port one only when none fits. tools/build_mission.py BACKGROUNDS maps each
  Cataclysm mission to a stock sky: 01 -> **ez14** (orange haze, bright core, arc above), 13 -> **ez08** (HW1's
  almost exactly). Found by rendering Cataclysm's mission<NN>.btg and HW1's ez<NN>.btg (reference/hw1classic/btg)
  the same way (make_background.render_page) and comparing per pixel at every rotation, then by eye. Cataclysm's
  own btg/ez<NN>.btg are its repaints, not HW1's. Most Cataclysm mission skies are new art: decide per mission.
  HWRM can't rotate a sky (Cataclysm's theta 200 is lost).
- Stock skies: HWBackgrounds.big background/<name>/ (ez01-16 HW1, m01-15 HW2): <name>_light.hod (what is drawn),
  <name>.lua (lens flares), <name>_extra.lua (sun god rays, ship gamma, bloom, env), _hq_ cube maps. A loose
  data/background/ez14/ez14_extra.lua overrides the stock one: ours dims the god rays (rayExposure 0.735 -> 0.5)
  and raises the bloom threshold 0.68 -> 0.855 (ez10-12's; ez14's low threshold bloomed the whole bright sky).
  Cataclysm has no bloom; the user watches it.
- Our converted sky (tools/make_background.py, BTG -> textured sphere + stock ez01 LITE) looked wrong in game and
  is off (BACKGROUNDS = {}); the BTG / HWRM .hod format notes stay in its docstring.

## Mission start: the fleet's hyperspace arrival (confirmed in game, Mission01)
- kasfStartLevelByHyperspacingShips (all 17 missions) = exe SP flow state 9: the fleet arrives at StartPointPlayer.
  Runtime: the real fleet is captured before the intro NIS (an NIS's ships belong to the player too), small ships
  docked instantly, the Kuun-Lan `SobGroup_Despawn`ed; then `SobGroup_HyperspaceTo(ms, "StartPointPlayer")`, launch
  once its order is COMMAND_Idle, then G_ShipsHaveArrived.
- HyperspaceTo brings the ship in unrotated (bow +Z, port +X), ignoring the point's rotation.
  Its heading comes from where the ship was: the exit flies it in along the line from its old position to the point
  (despawned on the point itself: no line, bow +Z). Turning it by script fails: the exit keeps +Z as its heading
  goal and steers back (logged). So it waits KAS_ArrivalBack behind the point (cataclysmkas.lua
  KAS_ArrivalPlaceBehind, build_mission.py ARRIVAL_YAW; user-confirmed, Mission01).
- Camera: level `addCamera(name, target, eye)` + `Camera_UseCameraPoint`, then
  `Camera_FocusSobGroupWithBuffer(g, distance, 0, 0)`. `Camera_FocusSobGroup(g, 0, 0, 0)` zooms right in, whatever
  the camera point.
- A ship spawned (or SetPosition'ed, even ghosted) inside another ship's collision box is pushed out of it: the
  Workers could not be made to leave through the Hangar this way (dropped by the user).

## Mesh animations and ship effects (Worker, confirmed in game)
- HWRM .mad (IFF; layout in tools/mad2hwrm.py): clip and key times are **seconds** (stock clips e.g. 0.067-1.8),
  tangents in value per second; channels `<joint>_translateX/Y/Z`, `_rotateX/Y/Z` (radians, same Euler triple
  as the HOD joint's, Z*Y*X). Frames made every clip 30x slow (looked frozen).
- Meshes parented to a JNT in the DAE are bound to it in the HOD (MULT records the joint): rigid parts animate.
- Cataclysm .mad ("Mellonn" 0.91): per object 6 TCB splines over shared times (s); local matrix = translation
  (c1, c2, -c0), rotation nisObjectEulerToMatrix(c3..c5). sworker: pose at t=0 equals the .geo matrices exactly.
- .madstate: `<SHIP>_<State>_OnSet/_OnPause`; `setPauseTime(ship, clip, 1000)` holds the last frame. Setting the
  Start state to 0 and back to 1 in `_OnPause` waits for the clip started there (beam after the boom is out).
- NIS: only numbered states work in `setMADState` (`NIS00`, `NIS01`...; "NIS_DockOpen" did nothing), and not at
  frame 0 (moved to frame 5). tools/nis2hwrm.py NIS_STATES maps HW1 `meshAnimStart <clip>`.
- Harvest stand-off = the model's `LatchOrientation` joint (put on the asteroid's surface; stock tai collector:
  95 ahead, Up along the beam). Without one the collector sits on the rock. The Harvest ability's last argument
  did not change it.
- .events effect markers are joints. Stock harvest cone (harvesting_beam_kus) is ~35 long at fx_scale 1, so a
  140-unit stand-off showed only its glow. Effects start where the marker is when started.
- Cataclysm: harvest = SectBeast_resource_solid.ebg (orange cone), repair = Repair_Corvette.ebg (green);
  nozzles = .mex Gun "GUN0" (resources) / "Rep0" (repair), HW1 ResCollect.c ASTEROID_HARVEST_RANGE 400.

## Cutscenes (Phase 0.5, confirmed in game with n01)
**Checklist for every cutscene** (after n01 lost its unsubtitled chatter and music):
1. `python tools/nis2hwrm.py <name>` (or `--audit-only` before it is wired in) writes `docs/nis/<name>.md`: every
   HW1 script event and what became of it (translated / cued / not converted with the reason / no line). Every
   command must be in nis2hwrm's TRANSLATED or NOT_CONVERTED tables: an unknown one stops the conversion.
2. Read the report's audio table: every speech line, its speaker, subtitle or not, and the music.
3. Play the original cutscene (Cataclysm) and the converted one; every line heard in the original must be in the
   table and heard in game. Anything missing that the report does not list is a converter bug: fix the tables.
- **A speech line with a blank subtitle plays nothing** (confirmed in game: `speechEventActor` in NIS, and
  `Subtitle_AddSkippable` in missions returns 0). `Sound_SpeechPlay` stayed silent too, in every path form tried
  ("speech:" is not an alias for it). Fix: every unsubtitled phrase (4762) gets the subtitle `<c=ffffff></c>`
  (tools/speech_tags.py INVISIBLE, written by tools/build_speech.py): empty colour tags count as text but draw
  nothing, so the line plays with the speaker's portrait and no subtitle, as in Cataclysm. Tested in game on
  nislet01's 11 lines: `<c=000000> </c>` works too; a Latin-1 or UTF-8 no-break space, soft hyphen, zero-width
  space, DEL, `\n`, two spaces and a black "." all show something.
- `tools/speech_speakers.tsv`: known speakers (from the original) pick the portrait where the actor bits mislead
  (n01's Fleet Command line has the pilots' 0x800). Speaker bits: 0x800 pilots (and that line), 0x1000 Fleet
  Command, 0x2000 Tactical Officer, 0x200000 n02's research module, others allied / alien fleets.
- **NIS endings** (confirmed in game, n01 -> nislet01 -> Mission01): an NIS needs `wideScreenOut` at its end or it
  never completes (frozen last frame; Gearbox's all end `wideScreenOut(2)`, none fades in). The NIS fade and
  `Universe_Fade` are one fade, and the NIS drops it when it ends. So an NIS that ends on black (KAS_NisEndsBlack)
  ends without a fade-in; cues hide the HUD (`UI_SetScreenVisible("NewTaskbar", 0)` before its wideScreenOut,
  `Camera_SetLetterboxStateNoUI(1, 0)` after), a per-tick rule re-blacks the moment it completes, and the runtime
  fades the game (and HUD) in 3 s later unless another NIS starts. One frame of space + HUD still shows at each NIS
  end; `newNIS("nis/...")` (Gearbox's n08 chain) would avoid it where the next NIS is known.
- HWRM beams stop when their target dies: a target killed while a beam ship (nis2hwrm HALT_DELAY) still fires at
  it becomes hide() + a `death_generic_fighter` effect object on its path (FOLW kind "effect", `triggerEffect`).
  Ion cannons charge 2 s before firing (wepn beam anticipation): attacks ordered 2.2 s early, halted 0.25 s late.
- NIS battle commands as Gearbox's: `attack("obj")`, `haltAttack()`, `death("deathCannon")` (HW1 deathDamage),
  `health(x)`; every NIS ship `invincible()` (death() still kills it); HW1 `fire` dropped.
- `startMusic n`: the NIS script's `musicStart("cataclysm/music_nn")` stayed silent; it is a runtime cue
  (`data/nis/cataclysm/<name>_cues.lua`, cataclysmkas.lua KAS_NisCues: `Sound_MusicPlayType`, as kasfMusicPlay;
  0.1 s rule from the NIS start, cleared when it ends). Confirmed in game.
- Speech events with no phrase in Cataclysm's tables (n01 event 347) were silent in Cataclysm too.
- Cataclysm's `subtitle <n> <ms>` (12 uses) shows nothing in the original (n01, checked in Cataclysm): dropped.
- HWRM NIS = IFF `FORM NIS ` (layout in tools/nis2hwrm.py docstring). Played with `NISLoad("nis/cataclysm/n01")`
  then `NISPlayFromCoordSys(path, pos, matrix)`; `NISShipStartPosition(path, shipType, -1)` finds the centre ship
  by FOLW object *name* = ship type. Wait with `NISGetAnyPlayingHandle()` / `NISComplete(h)`.
- Every camera eye needs a FOLW record of kind "camera" (else "setting a NULL camera" + access violation), and the
  script must pick one (`cameraCut("Camera0")`).
- CMRA lens: u32 0, doubles (0, vertical FOV deg, horizontal FOV deg, 24, near, far). Confirmed: field 1 is the
  vertical FOV. HW1 FOV is vertical on 4:3 (NIS default 75); keep HW1's horizontal view on 16:9.
- HWRM interpolates NIS keys at render rate and snaps them to whole frames: HW1 one-frame steps become slides.
  Camera cuts -> one HWRM camera per shot + `cameraCut`; object repositions -> hide() for that frame.
- Euler: rotate order XYZ (M = Rz Ry Rx), objects face +Z, cameras look down -Z. HW1 cameras rest at gimbal
  lock (ry = -90): hold rz there or the angles flip (visible jiggle).
- HW1 never uses the paths' timeOffset. Script object names differ in case from the NIS ones.
- HW1 left the screen black at the end of an NIS and faded in itself; the converted script fades back in.
- Speech actors: 16 Fleet Command, 17 Fleet Intel (logged from Actor_HW1_*).
- Not converted yet: music (startMusic), subtitle text cards, lights/ambient, lens flares, the planet backdrop,
  buoys, colour schemes, FOV changes inside a shot, Kuun-Lan mesh animations (DockOpen/DockClose; Worker ones are), remainAtEnd (the real ships are hidden during the intro instead; Gearbox keeps the NIS ships).

## Damage multipliers (measured 2026-10-12)
- SobGroup_SetDamageMultiplier COMPOUNDS (0.5 then 0.5 = 0.25; then 2 = 0.5): set it by ratio from one place only.
- Ion beams (InstantHit) stop firing below a 0.5 multiplier (fire at 0.5, cut out at 0.4); low weapon damage itself is
  fine (a 10 % weapon copy fires). Factors below 0.5: weapon copies (tools/make_variants.py).
- SobGroup_CreateShip builds docked inside a ship that can build and returns no usable group (Gearbox, KASUtil
  KAS_RequestShips): spawn in space with SobGroup_SpawnNewShipInSobGroup instead.

## Resource ships' cargo on death (2026-10-12, decompiled, confirmed in game)
- Cataclysm (FUN_00548e00, as HW1 UnivUpdate.c): a dying ship of class Resource with RU aboard leaves dust cloud type
  0 worth its RU x DUSTCLOUD_RCOLLECTOR_BLOWUP_SCALE (1.0, resource.script), shrunk by value (dustcloud0.shp: 50 RU
  full size, min 0.2).
- HWRM already does it: SpawnDustCloudOnDeath / SpawnSalvageOnDeath / SpawnAsteroidOnDeath (handlers 0x60d088 /
  0x60d2d4, kinds 5 / 4 / 3) all store name, count, then **build cost %, held RU %, parent RU %, absolute RU** first
  (the error strings' "position X..." names misled). At death (FUN_00668fc6) the dying ship's build cost / held RU /
  parent RU are shared between its entries by those weights (one entry: all of it); absolute RU / count otherwise; a
  dust cloud spawns only with RU > 0, its size = size + random x sizeRandom (not by value). Stock collectors (Worker
  included): `SpawnDustCloudOnDeath(..., "DustCloud_0", 1, 0,70,0,0, ...)` = held weight 70 = the whole cargo.
- **Confirmed in game:** the cloud carries the cargo and is harvested by a Harvest order's own target search (button /
  hotkey, user), but it **can't be clicked** as a target: HWRM's level functions (addDustCloud / addAsteroid /
  addSalvage, 0x50e6xx-0x50ebxx) and the reactive fleet OR a runtime-set attribute mask (DAT_009dc978, .bss) into the
  new resource's +0x15c; the death spawner (FUN_00668fc6) doesn't. Stock DustCloud_0 also has selectionPriority 0 and
  no blobRadius; ours is HW1's dust cloud 0 (DustCloud0_hw1, install_cr.py patch_cargo_clouds), as Cataclysm drops.
  The dust cloud factory FUN_0066daa2: RU = arg (absolute) << 10, or a % of the type's resourceValue when its 7th
  argument is set.
- Dead end: SpawnAsteroidOnDeath with a dust cloud type crashes the load (null model, 0x5044d6): it loads only from
  data:Resource\Asteroid (category table 0x8bcd5c: Ship, WeaponFire, Volume, Asteroid, Salvage, DustCloud, ...), and a
  StartDustCloudConfig there gets no model either.

## Debugging crashes (Phase 1)
- **Crash on exit with no ErrorLog** = heap corruption (Windows Application log: ntdll, 0xc0000374). HWRM's own
  handler doesn't catch it. Catch it with Sysinternals ProcDump (`C:\Modding\tools\procdump`): launch, then
  `procdump.exe -accepteula -ma -e 1 -f C0000374 <pid> <dir>`; read the stack from the dump (thread context + exe return
  addresses) and decompile them in project_hwrm. Under a debugger the heap is checked harder, so it may trip earlier.
- **Never let two NIS objects share animation channels** (FOLW channel names): HWRM frees each object's channels at
  NIS end (MotionNode / MotionFollower) -> double free -> every exit to the menu crashed. nis2hwrm.py gives every
  object its own copies (own_channels).
- Ship .mad files must drive the model's own joints: Cataclysm Remastered's .mad on our models is not installed.
- Every crash writes `Bin/Release/<date>_ErrorLog.txt` (+ minidumps): faulting address and stack. The exe is loaded
  at 0x00da0000 here; its Ghidra image base is 0x400000 (project `Cataclysm-decomp/project_hwrm`, copy of the exe;
  `scripts/DecompileAt.java`). Source file/line strings in the exe name the subsystem (e.g. sctobjectload.cpp).
- A subsystem with no model (a .subs copied without its .hod, and no LoadSharedModel) crashes the load in
  solStartSubSystemWeaponConfig (null model +0x298, read of 0x10; tools/make_variants.py copies the .hod).
- `.ship`: StartShipWeaponConfig / StartShipHardPointConfig must come after `LoadModel(NewShipType,1)`;
  solStartShipHardPointConfig reads the joint from the loaded HOD (null -> access violation at load).
- Build families must be declared in scripts/familylist.lua ("could not find family ..."); dock path MAD must be a
  valid animation index (stock paths use 0).
- Dock path waypoint (SEG) record, 64 bytes (HODOR flag test): pos f3, rot f3, UseRot u32, Tol f, Unfocus u32,
  Spd f, Check u32, Close, Player, Queue, Clip, ClearRes (u32 each). Stock collector In: Player+Queue, Player,
  ClearRes; fighter In: Player+Queue, Player, Clip+ClearRes; Out paths: no flags. HOLD_DOCK must be under ROOT_LOD[0].

## The Mimic (2026-10-10, confirmed in game)
- Cataclysm (FUN_005b8d70 mode 0 unmimic / 1 ship / 2 asteroid; state machine at ship +0x760, FUN_005b8f30): a phase
  runs 1 -> 0 (mimic) or 0 -> 1 by 0.05 per universe update (16/s: 1.25 s), after a random 0-0.86 s delay. The
  target's model is drawn as a shell (FUN_004b5c90 / 004b5aa0): every vertex pushed out from the centre onto a sphere
  of R = 1.2 x max(target radius, Mimic radius) by the phase, material faded by it; the Mimic's own model is drawn
  while the phase > 0.25. Mimicked, the ship draws the target's model (FUN_005b9640) and takes its stats for display.
- Ours: one ship. Its model (tools/build_mimic.sh, make_mimic.py; geo2dae.py --body / --part) holds joint MimicBody
  and Disguise_<target> per disguise (Cataclysm's model of the target, its faction colours baked: a team colour
  scheme repaints the whole ship). Its .madstate shows one joint (setJointVisible) per state, set by
  shiprules.lua (SobGroup_SetMadState). A swap to another ship type (the first version) stopped the ship, lost its
  orders and needed collisions off and reselection: no engine call sets a ship's speed or reads a move destination.
- SobGroup_SetMadState passes on only the engine's state names: custom names never reach the madstate, and of the
  NIS states only NIS00-02 (stock madstates define no more; NIS03+ were dropped). Mimic: NIS00 itself, NIS01-02 and
  DockPathOpen1-5 the disguises (dock path states: the engine sets them only on ships with dock paths). A madstate
  ran only with a .mad present (tools/make_static_mad.py: one still clip).
- Untargetable: SobGroup_MakeUntargeted takes one argument and sets nothing on the ship (HWRM
  luasobgroupactions.cpp): it removes the ship from every other ship's current attack targets, once. Called every
  ship update while disguised; stopping lets it be targeted again. SobGroup_SetGhost (collisions off) didn't stop
  targeting.
- The shell: mesh effects (STYLE_RING, UseMesh; tools/make_mimicfx.py, build_mimicfx.sh). An effect mesh must be one
  mesh with one material: a ship model (many meshes on joints) drew nothing; with the ship shader it ignored the
  effect's colour (no fade), so shader fx and the model's texture pages packed into one atlas (geo2dae.py --fx-mesh).
  Additive and self-lit like the Keeper's phase meshes, fading by colour. FX_PlayEffect leaves an effect where the
  ship was: started as the ship's events (FX_StartEvent, MimicIn_ / MimicOut_ / MimicTail_<target> on Root) they
  follow it. Mimic: MimicIn_ on the press, the model switched 1 s later (two ship updates) under MimicTail_; Unmimic
  switches at once under MimicOut_.
- Our models have one LOD: the .ship's upLOD / downLOD (made for CR's models) left them invisible zooming out;
  install_cr.py use_our_model removes them (minLOD 1).

## Kamikaze (2026-10-10, confirmed in game)
- Cataclysm (FUN_0043a980): a rammer deals kamikazeDamage[its type] (tactics.script: Mimic 1000, Acolyte 400, ACV
  1000, Worker 1000, MCV 2500...), x the Quantum Explosive Charge multiplier once upgraded (FUN_005b9980: ship
  +0x770; never assigned in the decompiled code, value unknown). Death blast (FUN_00545f00): radius
  blastRadiusShockWave x ship radius (x1.33 for the big variant), damage blastRadiusDamage x (1 - d/R) x 0.5 (0.75):
  for a Mimic about 6 units, only the ship rammed.
- HWRM: its own Kamikaze order (button, hotkey, right-click) deals about the rammer's current health x 7.5
  (tuning.lua CollisionInfo; the kamikazeArmourFamilyDamageMultiplier list goes by the TARGET's family: raising the
  Mimic's own family x5 changed nothing). To a script a kamikaze is just COMMAND_Attack; IsDoingAbility(AB_Kamikaze)
  is 1 for every ship, even idle; a ship mid-kamikaze can stop getting custom-code updates. Close to Cataclysm's for
  the armed fighters on armoured targets (Acolyte about 385 vs 400), so theirs is HWRM's.
- The Mimic (tools/make_mimicarmour.py): health x3.33 (40 -> 133) so HWRM's hit is about 1000 in one blow, and its
  own armour family MimicArmour taking x3.33 from every weapon (setPenetration: its Unarmoured value, else the
  default, x3.33; stock HW2 weapons our ships use are copied in for it) and as a ram target, so it dies to the same
  fire. A damaged Mimic hits for less (user: a good quirk). Its attack is a kamikaze: CanAttack kamikaze styles on
  every family (its own numbers: the collector's 1, 5, 2 took attack orders away) and the ship rules reissue an attack
  order as SobGroup_Kamikaze (shiprules.lua CatKamikaze_Tick). Line 167 (four takes) instead of HWRM's attack
  acknowledgement (catspeech.lua CatSpeech_SilentAttack). Only the Mimic and MCV have kamikaze lines.
- Tried and dropped: script top-up on the target at the Mimic's death (worked, but the damage showed in two parts).
- Unit barks pick a random Cataclysm take (KAS_SpeechBark: {takes, stride, base}, a take exists if it has a duration);
  announcer lines with several takes are random sample containers (tools/make_unitspeech.py write_fleet, as CR's
  Beast announcer: <event>/<event>.lua + <event>_<n>.wav). The Kuun-Lan said "Bridge" every time.

## Pilot experience, linking, economy (from cataclysm.exe, 2026-10-09)
- **Experience** (FUN_005147d0, tables at 0x72bb78-0x72bce4): ship + 0x5c8 = kills per victim class (12 HW1 classes:
  Mothership 0 ... Fighter 6, Resource 7, NonCombat 8, MonsterShip 9, Component 10, Micro 11), credited to the ship
  that fired the killing shot (FUN_00546250; missiles credit their launcher). Score = sum(kills x weight)
  (weights 20,8,10,9,5,3,1...); rank (ship + 0x5f8, 0-4) = how many of the killer class's 4 thresholds the score
  strictly exceeds (fighter 1/2/3/4, corvette 2/4/6/8, frigate 3/6/12/16, destroyer 5/10/20/40, capitals
  10/30/60/100). Rank x1.0-1.4 on weapon damage (FUN_005148f0) and speed (FUN_00514940); speed also drops with
  damage for every ship (-0.1 <75%, -0.2 <50%, -0.4 <25%, -0.6 <10% health). Rank names strExperienceLevel0-4,
  rank-up message strShipLevelUpNotify ("has gained a Level:"), human player only. Stars: overlayicons/expstar.lif
  (magenta), one per rank beside the selected ship's health bar (FUN_00507630).
- HWRM: `data/scripts/cataclysm/shiprules.lua` (custom code on every campaign ship, tools/make_shipcode.py; a ship's
  own custom code is chained). No killer info in HWRM: one of the victim's attackers (SobGroup_GetAttackers each
  0.5 s) gets the kill, the human's first. **Stars are off**: FX_PlayEffect is not attached to the ship (left
  behind as it moves), and ui/ati/ati.lua only draws engine values (no per-ship icon from script; checked the
  exe's 362 SobGroup/Player/UI/FX functions). The user wants them as real UI beside the stance icon: later.
- **Link** (FUN_0044d3b0 command, FUN_00467b80 link, FUN_00468650 unlink): two Acolytes dock (DPT_Link point,
  linkDistance 50) and are replaced by an sACV: health fraction = mean of theirs, kills summed (each part's saved
  for unlink); unlink gives each part its own kills + half of what the ACV gained. ACVs are also buildable
  (SPRSShipDepend sACV TECH_DRIVE_FIGHTER, TECH_LINK). The Link/Unlink objectives are the tutorial's.
  HWRM: CustomCommand "Link" (Acolyte) / "Unlink" (ACV); a ship has one CustomCommand, and it shows an energy bar
  (ati.lua auxiliaryPower). Plan (user): from Mission 3 (first kasfAllowPlayerToResearch TECH_MISSILE) the
  Acolyte's missile volley (sacolyte.shp MissileRegenerateTime 10.375, MissileVolleyTime 1.2) takes the
  CustomCommand and its energy bar; Link then needs another trigger.
- **Link / Unlink animation (confirmed in game, user: "that's actually it 100%")**. Cataclysm (FUN_00467b80): both
  Acolytes on one spot, the first rolled 180 about forward (right/up negated), both play sacolyte.mad "Link" (body
  slides from 50 to 9.65 along its up axis, thrusters fold); the sACV replaces them when the clips end (2 s timer
  fallback) with the second's orientation. Unlink: Acolytes 50 either side along the ACV's up, the second rolled,
  "Unlink" clip slides each body out from the ACV half's pose (3 s). The ACV mesh is the two halves at +-9.65,
  overlapping (Acolyte up extent -13.8..11). HWRM version (shiprules.lua CatLink_*, build_ship.sh som_acolyte):
  - the partner stops and waits; the lead flies to a point 300 behind its slot (50 below the partner, along the
    partner's heading), then to the slot; once it has **stopped** there it is swapped for one stand-in Acolyte at
    rest at its exact pose, which glides 0.8 s into the start pose; then both clips; the ACV at the clip's end.
  - the lower ship flies **upright**, its model shown rolled: clips LinkB / UnlinkB (mad2hwrm --rolled: the root
    joint turned 180 about forward; UnlinkB then turns upright in place over 1 s). The Link clip is shifted -50
    (mad2hwrm --shift) so each ship sits where its body starts: two ships on one spot collide and shake.
  - ships held for a clip: re-placed every update (SetPosition + SetTransform; the Acolyte's custom code runs every
    0.05 s, its rules still every 0.5 s), AB_Move / AB_Steering off, SobGroup_SetGhost on.
  - dead ends: a really rolled ship jiggles (the engine levels it, the pin snaps it back); a ship that was flying
    jiggles when pinned (no script way to zero its speed); swapping both ships (or a moving one) for stand-ins
    drops frames visibly; both flying to one point bounce (avoidance).
- **HWRM script facts found doing this**:
  - the custom-code group (g) is **one name per ship type**, holding whichever ship's code is running: acting on
    another ship needs that ship's own group (CatShip_Create: cat_ship_<id>), and g is still **empty in Create**
    (fill the own group, and match spawned ships to their pending data, on the first update);
  - ship scripts keep their Lua state across games (a restarted mission saw the last one's data): reset when the
    game clock goes back (CatSession);
  - SobGroup_GetCoordSys: 9 numbers **row by row**, columns = right, up, forward (Matrix3_GetVector3FromCol, only in
    the mission script state; checked with a tilted ship in range.lua); SobGroup_SetTransform takes the same;
  - madstate: only the engine's own state names reach <SHIP>_<State>_OnSet (NIS00-02, DockPathOpen4 /
    DockPathClosed4 are spare on a fighter). A madstate runs in its own Lua state: no globals shared with ship
    scripts either way (probe, 2026-10-10), but each SobGroup_SetMadState runs its OnSet at once, so a script can
    send it bits (shiprules.lua CatProcBeam_Send, smt_processor.madstate). Joint aim from a script: a clip that
    sweeps the joint, played toward the new angle and paused there (setTime / setPauseTime).
  - Effect cones on script-aimed joints (tools/make_procbeam.py): standard right-handed joint rotations (DAE and
    .mad alike), an effect mesh drawn along its marker's +Z, model x = the engine's right. Settled by a calibration
    (CAT_PROC_CALIBRATE: fixed poses, read off screenshots); three readings of loose descriptions went wrong first.
  - The repair order: HWRM heals only by latching (RepairByLatchingCommand); SobGroup_GetCommandTargets returns
    nothing for COMMAND_Repair (or any order) and SobGroup_GetSobGroupRepairingGroup nothing; heal weapons never
    fire at friendlies. Ours: a non-latching RepairCommand positions the ship, shiprules.lua CatRepair_Tick heals.
- **Unit test range** (campaign entry 1, leveldata/campaign/cataclysm/range): Kuun-Lan with every module, Acolytes,
  ACVs, Workers, a Recon, asteroids, Taiidan targets; all research granted (range.lua RANGE_GRANT_ALL).
- **Economy**: Cataclysm asteroids are worth ~10x HW1's (resources/asteroids/*.shp resourcevalue: 11, 160, 400,
  1000, 2000); HWRM's HW1 asteroids are 100 RU x addAsteroid's percent, so mission2level.py writes the percent that
  gives Cataclysm's RU. RU trickle (resource.script): +25 RU every 256 frames (16 s) while under 400 RU, every
  player (cataclysmkas.lua KAS_RURegen). Build cost/time 1:1 from the .shp (install_cr.py set_costs).
- **Their weapons and HW1 armour**: Cataclysm Remastered's setPenetration lists HW2 families with default 0, so
  they did no damage to stock HW1 ships (Unarmoured_hw1 / LightArmour_hw1); install_cr.py patch_hw1_armour copies
  the HW2 value, as stock HW1 weapons do.
- Restarts: .ship/.wepn/custom code/fx load at game start (full relaunch); level and mission scripts reload on
  every mission start (back to the menu is enough).
- **Abilities** (tools/make_abilities.py): HWRM keeps ONE CustomCommand per ship (a second line replaces the first:
  tested). commanduidefines.lua has 32 custom IDs (INFO_CustomStart + 0-31, stock uses 0-3), each with a taskbar
  button and right-click name. So each ship type has one *native* ability (engine button, right-click entry, energy
  bar, sent to exactly the selected ships) and any number of *button* abilities: our taskbar buttons call
  MainUI_ScarEvent("CatAbility('x')"); the mission script copies the human's MainUI_CurrentSelection() into
  cat_cmd_x and toggles button visibility (UI_SetElementVisible("NewTaskbar", ...)); ship rules act if in cat_cmd_x
  AND SobGroup_Selected (the reported selection alone was too wide: 22 ships for a smaller selection). Button
  abilities can't be in the engine-built right-click menu. Link works on exactly the selected Acolytes (user).
- **Players Patch 2.3** (workshop 1190476337, extracted to Cataclysm-decomp/reference/players_patch) is the bottom
  data layer (install_cr.py PP; Cataclysm Remastered over it; never our tracked files): strike-group formation
  fixes, its HW1 ships for our Kushan/Taiidan (make_shipcode.py copies its .ship), familylist families merged.
  Its HW1 rebalance comes with it for now; the target is Cataclysm's balance (user).
- **Upgrades** (tools/make_upgrades.py reads the tables from cataclysm.exe; shiprules.lua CatUpgrade_*): ship +0x3f4
  = ability bits (ABILITY_* enum: ADRIVE_FIGHTER 0 ... ORDINANCE 26), +0x3f0 = armour level. Research -> bits:
  table 0x72b9e8 {tech, bits, bits2} (TechnologyType = the TECH_* strings' order minus TECH_ADVANCED_SYSTEMS:
  TECH_ARMOUR2 = 14); ship type mask 0x72b7a0 (ShipType = english.script's ship name order, sRecon 0, sAcolyte 1);
  armour cap 0x72b31c; times: 10 s per new ability bit (20 for INFECT), armour 10/20/30 s, x upgradeTimeModifier.
  Upgrades happen (FUN_00514490 callers): the Upgrade command (FUN_0044de80, timed; UpgradeByDocking strike craft
  dock), any docking of an UpgradeByDocking ship (FUN_00465860, instant), new ships (FUN_00542320), mission
  start / load (FUN_005a91d0), kasfShipsUpgrade (0x498c70, first named kasfResetShipRenderFlags: every team in
  Mission01 runs it at start). Abilities are upgrades too: an Acolyte links only once it has the
  LINK bit (tutorial: "Upgrade Acolytes", "Link the upgraded Acolytes"). New ships come upgraded. ADRIVE_* = +0.15
  speed. Armour levels change incoming damage (base damage table 0x72b228 [weapon type][target armour]: with the
  damage conversion, not applied yet: "Damage model"). Weapon levels (projectile -> energy ...: 0x72bb18) also not yet.
- **Weapon upgrades** (the Acolyte's missiles, ORDINANCE): its two launchers (cat_acolytemissile on Weapon_GUN2/GUN3)
  are "Special Attack" weapons; they fire in normal attacks only while the ship's UseSpecialWeaponsInNormalAttack
  ability is on. Research CAT_ACOLYTE_MISSILES (tools/make_race.py RUNTIME_RESEARCH, granted at mission start)
  gives Acolytes the ability; shiprules.lua CatUpgradeWeapons switches it per ship (SobGroup_AbilityActivate) once
  the ship has the upgrade (confirmed: none before, missiles after, Upgrade adds them). Dead ends: weapon
  subsystems added by SobGroup_CreateSubSystem need a ship that can build (else a fatal Lua error; and only out of
  a hangar), which gives every Acolyte a build menu tab; innate damageable ones held at 0 health still fire (the
  engine puts them back to activateHealthPercentage). A subsystem with timeToBuild 0 on a ship that can build it
  crashes the game (integer divide by zero). Lua 4 call() can't protect engine calls (_ERRORMESSAGE can't be set).
- Development switches (keep empty in commits): cataclysmkas.lua KAS_DevTechs / KAS_DevModules (research and
  Kuun-Lan modules for testing a later mission), shiprules.lua CatDevUpgrades (upgrades counted as researched from
  a game time; game time includes the opening cutscene).
- **Energy weapons** (exe FUN_00514140 / 005142e0 / 00514490, decompiled with Ghidra headless + scripts/DecompileAt.java):
  research sets the player's weapon levels (table 0x72bb18 {tech, level}: none -> 0 PROJECTILE, TECH_ENERGY -> 1,
  TECH_ION -> 2, TECH_PLASMA_WEAPONS -> 3, TECH_MISSILE -> 5, TECH_BIG_GUN -> 7); a ship's upgrade only moves a gun
  from 0 to 1 (EndUpgradeLevel WEAPON_ENERGY), for 10 s (0x72b204[0]). make_upgrades.py: pseudo-ability
  WEAPON_ENERGY on the Somtaaw/Beast types with such guns (19). **Showing it is SHELVED (user)**: a weapon change
  needs another ship type (tools/ship_variants.py), and swapping a *docked* ship failed: SobGroup_Despawn does
  nothing to a docked ship (the engine relaunched it), a ship spawned and DockSobGroupInstant'ed in the same tick never
  ran its ship code, new builds count as docked inside the Kuun-Lan, SobGroup_GetSobGroupDockedWithGroup is empty for
  the Kuun-Lan's hangar. CR's Acolyte has an energy cannon already (Ksh_KineticAutoGun1, SmallEnergyCannon bolts, a
  "Special Attack" weapon: data/weapon/cat_acolyteenergy is it as a normal weapon); their Super Acolyte pulsar fires
  only within 10 degrees ahead at 0.06 accuracy vs fighters. Projectile looks: data/missile/<name>/ (.miss/.hod/.events)
  and scripts/weaponfire/<name>.wf.
- **Damage model** (decoded 2026-10-09; survey: `python tools/cat_damage.py`, every mapped ship's Cataclysm health
  and per-gun damage/DPS next to CR's). Bullet type = FUN_0048b7c0(weapon level, GunSize), the GS_* enum (name/value
  table at 0x889da0, also the etg race scripts' setFireEvent sound types): 0 LargeEnergyCannon, 1 LargeIon,
  2 LargePlasmaBomb, 3 LargeProjectile, 4-7 Medium (same order), 8 MineLauncher, 9 MissleLauncher, 10-13 Small,
  14-16 VeryLarge Energy/Ion/PlasmaBomb, 17 Laser, 18 BigGun, 19 BeastWeapon (VeryLarge projectile has no case: 3).
  A gun uses its EndUpgradeLevel's type once upgraded (FUN_0048bb00: gun level == End and Start != End), else Start's.
  Damage per hit (FUN_00546a20) = table 0x72b228 [type][target armour 0-2] (3 floats per row; e.g. small
  projectile 7/4/4, small energy 22/20/14, large ion 16/14/9, missile 60/40/38) x bullet +0x138 (gun
  DamageMult x shooter +0x33c, the rank multiplier) x the target static's per-side factor (+0x1c8[side]) x a
  friendly-fire factor; non-ship targets use armour 0; force-field ships (FUN_005affa0) take nothing from types
  2, 3, 6, 7, 9, 12, 13, 16 (plasma, projectile, missile). Missiles/mines (FUN_0048aac0) = table [9 / 8][armour] x
  DamageMult x FUN_005148f0(shooter) (x ship +0x3e0 when flag 0x4000, likely Link). Beams (bullet +0x108 == 2 or 8:
  ion, FUN_0043c900) take the full per-hit damage on every collision check while they live (BulletLifeTime, e.g. 2.3 s
  for the Kushan ion frigate): per *tick*, not per shot; 16 ticks a second (HW1 source, Gardens of Kadesh Collision.c collCheckBeamColl: beam damage
  applied once per original-rate update, UNIVERSE_UPDATE_RATE_ORIG 16). Scale:
  Cataclysm Acolyte 220 HP / 2 guns x 7 (0.3 s, bursts 1.4 on / 1.3 off: ~24 DPS), missiles 60 x 7 = 420 each every
  13 s; CR Acolyte 175 HP / 18 per shot; CR capital ships ~2.5x Cataclysm's health and ion beams 2600 per shot.
- **Group names in ship code**: the `g` a ship's custom code gets is reused for later ships once that ship's code
  ends; act on a ship only through its own g while it lives (a list of kept names removed every Acolyte).
- **Fire Missiles** (the Acolyte's native custom command, ORDINANCE; Link is a button ability): energy 1000, all of
  it spent on a press (the engine spends the "minimum to activate"), refilling over 20.75 s (2 x MissileRegenerate
  10.375 s; energy recharge is per second: to be confirmed in game). Each ship's native command is on only once
  the ship has its upgrade (SobGroup_AbilityActivate AB_Custom: otherwise a press the script ignored still spent
  energy). HWRM can't fire weapons or change fire rate from script, so the volley only keeps the Acolytes on their
  target; missiles fire in normal combat as in Cataclysm. User: keep as-is for now (Cataclysm's volley dumps the
  loaded missiles 1.2 s apart and pauses regeneration 12 s).
- **Health and damage conversion** (tools/make_damage.py, run by install_cr.py; user, 2026-10-09: all ships,
  Cataclysm's scale 1:1, CR's accuracy rolls kept, armour levels later; confirmed in game: "feels good"). Health =
  .shp maxhealth. Per ship, Cataclysm DPS (table x DamageMult over FireTime / burst duty; beams per hit x 16 x
  BulletLifeTime) / HWRM DPS of its weapons (ship configs + innate turret subsystems; SpawnWeaponFire followed to the
  weapon holding the damage) = a factor on those weapons' damage; setPenetration flattened to 1 for every family.
  Shared weapons with different factors: per-ship copies (cat_<ship>_<weapon>, via ship configs only). Originals read
  from the source layers, never data/ (no double scaling). Our cat_* weapons carry Cataclysm's values (Acolyte
  missile 420). Not converted: Beast ships, mines, Somtaaw ramming frigate (no Cataclysm guns), armour levels, the
  Energy upgrade's damage. Beam tick confirmed 16/s (HW1 Collision.c).
