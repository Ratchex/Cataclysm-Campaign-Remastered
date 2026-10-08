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

## Ships and HODOR (Phase 0.3, confirmed in game)
- Pipeline: `tools/build_ship.sh` = `geo2dae.py` (Cataclysm .geo -> Collada + TGA) then HODOR (`.hod`) into
  `data/ship/<name>/`. Intermediates in `build/ships/` (git-ignored).
- HODOR: `HODOR.exe -action=convert -$CONVERT_IN=<dae> -$CONVERT_OUT=<hod> -$SHADER_MAP=<SHADERS.MAP>`.
  - Must be started from Git Bash. Started from Python, PowerShell (or bash spawned by Python) it spins at 100%
    CPU forever with no output; not the environment, stdio, cwd, console or error mode (all tested).
  - Forward-slash paths only. Textures: square power of two, >= 64 px, or it loops forever building mips.
  - Image id `IMG[<x>_DIFF]-image`, name `IMG[<x>_DIFF]_FMT[DXT1]`, effect `<diffuse><texture texture="IMG[..]-image">`;
    other ids segfault it. A `<x>_TEAM.tga` next to `<x>_DIFF.tga` is picked up automatically (R = 1 - team
    colour, G = 1 - stripe).
  - RODOH only reads HW2 Classic HODs (does nothing on HWRM ones).
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
  ("speech:" is not an alias for it). Fix: speech.dat gets a speaker tag for every unsubtitled line a mission or
  cutscene plays (tools/speech_tags.py; tools/build_speech.py writes it): `tools/speech_speakers.tsv` for known
  speakers ("(Recon)"), else from the actor bits it is played with: 0x800 "(Pilot)", 0x1000 "(Fleet Command)",
  0x2000 "(Tactical Officer)", others "(Comms)". 314 phrases; the user chose visible tags. A Latin-1 no-break
  space shows as "?". nis2hwrm stops if a line it emits would still be blank.
- `startMusic n`: the NIS script's `musicStart("cataclysm/music_nn")` stayed silent; it is a runtime cue
  (`data/nis/cataclysm/<name>_cues.lua`, cataclysmkas.lua KAS_NisCues: `Sound_MusicPlayType`, as kasfMusicPlay;
  0.1 s rule from the NIS start, cleared when it ends). Confirmed in game.
- Speech events with no phrase in Cataclysm's tables (n01 event 347) were silent in Cataclysm too.
- Cataclysm's `subtitle <n> <ms>` (12 uses) is not decoded yet (no string table found; exe string 0x888e88).
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

## Debugging crashes (Phase 1)
- Every crash writes `Bin/Release/<date>_ErrorLog.txt` (+ minidumps): faulting address and stack. The exe is loaded
  at 0x00da0000 here; its Ghidra image base is 0x400000 (project `Cataclysm-decomp/project_hwrm`, copy of the exe;
  `scripts/DecompileAt.java`). Source file/line strings in the exe name the subsystem (e.g. sctobjectload.cpp).
- `.ship`: StartShipWeaponConfig / StartShipHardPointConfig must come after `LoadModel(NewShipType,1)`;
  solStartShipHardPointConfig reads the joint from the loaded HOD (null -> access violation at load).
- Build families must be declared in scripts/familylist.lua ("could not find family ..."); dock path MAD must be a
  valid animation index (stock paths use 0).
- Dock path waypoint (SEG) record, 64 bytes (HODOR flag test): pos f3, rot f3, UseRot u32, Tol f, Unfocus u32,
  Spd f, Check u32, Close, Player, Queue, Clip, ClearRes (u32 each). Stock collector In: Player+Queue, Player,
  ClearRes; fighter In: Player+Queue, Player, Clip+ClearRes; Out paths: no flags. HOLD_DOCK must be under ROOT_LOD[0].
