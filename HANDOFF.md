# Session handoff: Cataclysm → HWRM port

Last updated 2026-10-18. Read this first, then `C:\Modding\Cataclysm-decomp\PORT_PLAN.md` (plan and decisions),
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

## Repair (2026-10-10): ordered repair works (Worker healed the Kuun-Lan, confirmed in game)
- HWRM heals only by latching (RepairByLatchingCommand). Our RepairCommand (install_cr.py repair_order: 4th arg 1, no
  latching; data/scripts/attack/*_catrepair.lua) just targets, approaches and holds off; shiprules.lua CatRepair_Tick
  heals the order's target (SobGroup_GetCommandTargets COMMAND_Repair) at 30 HP/s and stops the order when healed.
  Processor's automatic side beams: CatProcessor_Tick. Every model has RepairPoint0 (geo2dae) declared as RepCap.
- **Pending (user):** ships need more than one repair point so several craft can repair one target. Worker salvage
  untested.
- Kuun-Lan (user-tested): Cataclysm's six large guns (data/weapon/cat_kuunlan_gun*: setAngles cone 85 / 60, no
  line-of-fire check); the core has one collision box around the whole ship (geo2dae --col-box, tools/kl_bounds.py), the
  modules none (--col-none: their own stopped the rear guns' shots). Death effects (user-tested): tools/make_events.py
  gives the ships CR left empty stock HW1 effects; install_cr.py keeps every Somtaaw ship alive past its last death blast.
- Mission start / end (user-tested): the Kuun-Lan arrives facing its ARRIVAL_YAW (it waits in hyperspace behind
  the start point, cataclysmkas.lua KAS_ArrivalPlaceBehind), control locked through Fleet Intel briefings (Mission01
  from the warp-in, camera free), "Autolaunch set" (event 104), parade from Cataclysm's layout (tools/make_parade.py).
  End: the "Hyperspace" objective shows Gearbox's HYPERSPACE button; roll call, its Go Now replaced by Cataclysm's
  Emergency Hyperspace (KAS_EmergencyHyperspace). 0x497290 is Cataclysm's autosave. Gearbox's KAS_PlayerMothership
  can't be redefined (HWRM refuses): KAS_KuunLan, and Gearbox's cache group KAS_MothershipGroup0 for the roll call.
  KAS_DevHyperspaceAfter (seconds) shows the button early for testing.
- **Pending (user, after the mission work):** the Guard order is voiced by Fleet Command in Cataclysm, not by the
  ordered ships (done). Carry-over between missions: HWRM persistence. Winning Mission[n] writes
  Profiles/<p>/Campaign/CATACLYSM/persist<n+1>.lua (confirmed: Mission 1 saved the Kuun-Lan, scouts, workers,
  research, RUs). cataclysm.campaign now has Mission[n] = Cataclysm mission n and the range last; test missions
  deleted. Mission02's level: no player fleet, OnInit loads it as HW1's mission02.lua does
  (SobGroup_LoadPersistantData(<mothership type>)).
- **Pending (user):** the Clee-San (a Kushan destroyer) becomes a recoloured stock HWRM destroyer (model and effects
  both; tools/make_events.py leaves it out). The Sentinel's weapons name a mount (Weapon_Autogun) its CR model lacks.

## Processor: COMPLETE (2026-10-10, user-tested)
- Four automatic side beams (shiprules.lua CatProcessor_Tick): each picks the nearest damaged friendly in its 90°
  cone on its side; ship axes are SobGroup_GetCoordSys's ROWS (measured in game: CatAxesRows, logged "CATACLYSM
  axes"). Turrets move like a stock ion turret: the script turns them (rate eased within 10°, accel-limited, 0.2°
  deadband) toward an alpha-beta-filtered target position and sends angles as bit messages (NIS00-02 switches,
  4-bit check) to smt_processor.madstate, which freezes a still turret with pauseAnim and plays a moving one on the
  aim clip's matching speed tier (9 tiers, make_procbeam.py) between the script's 10 Hz updates.
- Look: the cone mesh (make_procbeam.py, tools/build_procbeam.sh) on stock fx_harvest (the stock repair beam's
  animated shader) with stock repair_beam's texture, colour cycle and blending; ion_repairflash on each target.
  Landing pads lit with the Kuun-Lan's pad glow (geo2dae --glow-copy), Cataclysm Remastered's glow elsewhere; the
  Kuun-Lan's engine shape (scaled) and setEngineBurn (install_cr.py patch_processor).

## Ramming Frigate: core ram COMPLETE (2026-10-10, user-tested); upgrades wait for their missions
- The Ram is HWRM's salvage-capture latch (SalCapCommand; no CanAttack: a right-click on an enemy is the latch; the
  button is the harvest icon labelled "Ram"; the order speaks Cataclysm's attack ack via CatSay 5). shiprules.lua
  CatRam_Tick: under the latch order (22), an enemy within 450 ahead -> the charge (x1.2 speed, madstate NIS00:
  AftBurnIgnite, push burn, ManualEngineGlow 1); latched (order 22, an enemy within 150, still 0.5 s) -> hit 1700,
  nose RamCollapse (NIS01), both ships pinned (target CatFreeze'd, frigate steering / collisions off but movement
  kept so its engines draw) and placed every update along the frigate's heading, ramping to 252/s, 30 s, cutting
  beam 20/s, other ships shoved out of the target's box (placed ships collide with nothing; impact: Cataclysm's
  shock bowl, tools/make_ramimpact.py, on marker_ram); then let go,
  RamRecover (NIS02; CancelAftBurn after a charge that never hit), 10 s before it can grapple again.
- Learned: SobGroup_SalvageSobGroup from script does nothing; the engine latches at its own distance (~130 to a
  Taiidan assault frigate's centre) but aligns by the LatchOrientation / SalvageOrientation joints (z 105: straight;
  at the nose tip it latched tilted), so the frigate is snugged in until its nose is on the target's nearest
  salvage point (CatRam_Snug; tools/make_hullinfo.py -> hullinfo_gen.lua: every type's BBOX and SalvagePoints;
  65 measured by a creep on the assault frigate, CAT_RAM_SNUG for unknown hulls);
  the model's hull hangs 56.7 back on JNT[RammingFrigate] (geo2dae --col-slices now builds through joint frames;
  --engines-at places its one nozzle, the .mex put two ahead of the nose); a frozen ship's engines don't draw.
- Engines: stock HW1 frigate burn x1.7 (one nozzle 12 inside the rear face), Processor glow x0.8; push burn
  tools/make_ramburn.py (12 billboard sprites, smt_rammingfrigate.events RamThrust).
- Left (with their missions / upgrades): cutting beam visual and 60/s (Advanced Ion Cannon), afterburner x2,
  pushing crystals. Assault and ion cannon frigates checked in game (user: within tolerance).

## Mission01 fixes (2026-10-12, user-tested: "battle is perfect and lasts the whole mission")
- Damage factors: SobGroup_SetDamageMultiplier COMPOUNDS and ion beams cut out below 0.5 (range tests). Only the ship
  rules set it, by ratio, floored at 0.5 (shiprules.lua CatShip_ApplyMultipliers). Factors under 50 % use weaker
  weapon copies: tools/make_variants.py (<type>_d<pct>, turret subsystems copied with their .hod),
  tools/damage_variants.py places them for teams whose state chain sets such a factor (build_mission.py), later
  factors apply as a ratio to the copy's. Damage values written as expressions (2400*2) are now converted.
- KAS runtime: kasfTeamFinishedLaunching also when none docked / 20 s after the order; original team sizes recorded
  at the start; ship creation spawns in space beside the given ships, owned like them; kasfFirstShip = one ship;
  formations formed again after launch (and 3 / 8 s on); kasfGuardShips holds a sphere; sensor net shown Open.
- Balance: Taiidan collectors at Cataclysm's 0.5 RU/s; Worker on the collector ratio (144); two extra Kushan
  main-guard ion frigates (tools/level_extras.py).

## RESUME HERE (2026-10-18: committed ("Worker salvage (HW1 SalCap, Tow0 underneath)...", after 394eafb), pushed; commit only when the user says)
**Next test (user plays Mission 2 normally; the shortcut test was removed at the user's request):**
- Pod captured -> carrier jumps out -> log "pCarrier departed", "CKAS: Pirates 0 left" -> "Destroy Turanic Raiders"
  completes -> Hyperspace objective / "~ End of Mission". If not: the "Pirates n left:" line says what still counts.
- Patrols by difficulty: the last run logged HWRM 0 -> skill 1 (pPatrol3-5 removed, two left); skill 2 keeps three.
- Disguised corvettes: hits land on the corvette itself (body-only collision); their unmasking shell at 2x (Mimic 3x).
**Then:** remove the TEST traces (list below, plus the "Pirates n left" print in K_492d20 and the worker clamp order
log), commit when the user says, Kuun-Lan nose RU pads, engine work (SU fit / queued count, Veterancy UI, Upgrade UI).
**2026-10-17/18 session (user-tested unless marked):**
- Worker salvage clamps and voice DONE (user-tested 2026-10-18): shiprules.lua CatWorkerClamps_Tick sends
  DockPathOpen3 on the salvage order (22; madstate: clamps out, boom stowed, harvest states skipped) and
  DockPathClosed3 on Idle / Attack; the order also barks event 150 ("Salvaging." etc., CatSay, FUN_004490b0).
  Mission02 visuals (ez16 seam / darkening, orange wisps) DONE, user-tested.
- Worker salvage WORKS (HW1 SalCap, user: "latched correctly and deposited at the kuun-lan"; on the pod's Tow0 side, the
  Worker upside down under it, user-tested 2026-10-18: "worked like a charm"). Workers latch by their
  **LatchOrientation** (the harvest joint 45 ahead of the nose; SalCap uses it for ship targets, SalvageOrientation
  only for salvage objects), a joint's frame comes from its Heading / Left children (FUN_00669ed3). The pod's
  SalvagePoint1 sits where that joint is with the Worker level on the pod's top (build_ship.sh cat_messagepod
  --salvage-at; geo2dae.py --salvage-at X,Y,Z@Up@Heading). Workers are dock family **Corvette** (engine work below:
  they unload RU in the hangar). Not re-tested since the Worker got its own flight model back (the "roll and reset"
  was the latch being released, not its flight). Mission02's salvaged-pod check: capturing the pod didn't end Mission 2
  (user, 2026-10-18): K_498cb0("dMessagePod", 0) took the team for a type (always 0); a team now counts its ships
  the player owns (user-tested: the capture is seen and Fleet Intel's line plays). It still didn't end: the end
  (Objectives pc 67) also needs "DestroyPirates" done, which pCarrier's F_5dd2d0 sends once GS_Pirates (pCarrier,
  Kamikaze, pFighter1-3, pSalvage, pGuard) is empty. Once the pod is taken the undiscovered raiders and pSalvage run
  0x498270, which is **ships die** (FUN_0044a150: a death time now + rand fraction of 1 s, the ship update kills it,
  FUN_00545b80), not the "disguise state reset" no-op it was; Init_Mission02 uses it too, removing pPatrol1-5 by
  difficulty. K_498270 / KAS_DoomTick now kill them (UNTESTED; TEST trace "CKAS: Pirates n left: ..." in K_492d20,
  watch whether the carrier that hyperspaced out still counts). User run: the raiders died, but "Pirates 1 left:
  pCarrier=1": HWRM keeps a ship that jumped out in its groups (Cataclysm removes it from the universe). K_493800
  now puts a team that hyperspaces out mid-mission in KAS_Departed, which KAS_Present leaves out of kasfShipsCount /
  kasfTeamCount (K_492d20 / K_492ce0); K_493600 / K_493630 take it back out (UNTESTED). Also K_493b90: HWRM's
  difficulty 0-2 -> Cataclysm skill 1-3 (raw 0 = skill 0 removed every patrol at start).
  Disguised corvettes (tur_standardcorvette_disguise): collision from the corvette body only (hod2dae.py
  --col-slices; HODOR's took in every disguise, shots hit the frigate's outline, user) and a 2x shell
  (make_mimicfx.py SCRIPT_SHELL 2.0, user: 3x then 2x). UNTESTED.
- Buttons: the Worker has its own Salvage button (make_abilities.py "salvage", CLICK sends eSalCap); the native
  btnSalCap is the Ramming Frigate's Ram only (its commanduidefines entry has no activateButtonName, so the engine
  no longer shows it on every SalCap ship; CatAbilityTick shows it). User-tested.
- Research errors fixed (UNTESTED, see the Mission 2 block below): kasfTechSetResearched; KAS_Unrestrict / KAS_Grant.
- Backgrounds (UNTESTED after the last fixes): Mission02 = **ez16** (Cataclysm's mission02.btg is HW1's ez16 repainted:
  sun beside a dark streak, black filled with haze), relit with mission02.hsf; dimmed like ez14 (data/background/ez16/
  ez16_extra.lua: god rays 0.5, bloom threshold 0.855). User 2026-10-18: STILL TOO BRIGHT. The Terah fog + clouds are
  removed (user: they looked bad; the --atmosphere mechanism is gone); HW1 nebula tendrils (Kadesh) on test in the
  range (range.level: west strand with Nebula0 resources, east tendrils only); the user is checking OG Cataclysm for
  the atmosphere to aim at.
  Mission01's ez14 now carries ez16's homeworld + moon (make_background.py COMPOSITE: ez16's model with ez14's texture
  and flare joints, ez16's PlanetSpin .mad + anims in ez14_extra.lua). User asked for the planets; check them, the
  flare on ez14's sun, Mission 2's brightness and cloud spread.
- Tools: tools/hodread.py decodes 8888 textures (RGBA) and can skip DXT (DECODE_DXT); Cataclysm-decomp/scripts/
  StringRefsFile.java (search strings from a file: cmd mangles parentheses / %).
- Left over: CatUpgrade_Start's "nothing to upgrade" TEST print (shiprules.lua); KAS_SalvageFind (unused, called at
  start); range.lua RANGE_POD_TRACE; geo2dae.py Latch<k> nodes on salvage points (harmless) and GEO2DAE_LIST_DOCKS;
  the Worker's dock clamp animation has never played (smt_worker.madstate CaptureActive / CaptureInActive).

**Cataclysm Remastered / HWU removed (user, 2026-10-14):** no CR file in the mod; plan + status in `REBUILD.md`.
`tools/install_cr.py` is now `tools/install_base.py` (Players Patch + Somtaaw/Beast ships from stock HW1 templates,
TEMPLATES; our 9 models via OUR_MODELS/OUR_WEAPONS; stand-ins keep the template model). Rerun it after any model
rebuild. Checks done: no data/ file identical to a CR-only file; every fx/sound/icon/weapon-fire name resolves to stock
or ours. User-confirmed after the rebuild: Mission01 loads, intro n01 + nislet01 play, Workers launch/dock/unload,
parade (Cataclysm's), Cataclysm ship names/descriptions (set_names, english.script).
Model builds no longer take CR inputs (build_kuunlan.sh / build_ship.sh): no glow maps except --glow-cyan, engines =
geo2dae's quad, Kuun-Lan collector paths from Cataclysm's own `smothership.shp` DockPoint table (geo2dae SHP_DOCKS:
Res0/Res1 only; the queue point doesn't count toward a path's 2 points), medium bay paths also take Utility (Workers
launch there).

**2026-10-14 session (committed in 9921bac, user-tested unless noted):**
- Speech: one queue for every voice line, Cataclysm's exe rules (`data/scripts/scar/cataclysmvoice.lua` CatVoice_Event;
  `tools/check_voice.py` enforces it from build_mission.py; memory voice-lines-through-queue). User: "much closer".
- End of mission: own jump watch (KAS_HyperspaceJumpersGone; the intro's despawned Kuun-Lan blocked mission complete).
  Untested.
- Mission 2 disguised corvettes (tools/hodread.py, hod2dae.py, make_disguise.py, build_disguise.sh;
  tur_standardcorvette_disguise). Untested in game.
- Cutscenes switch the sensors manager off (KAS_NisStart / KAS_LockedOut). Recon: trail per nozzle (its Speed Burst:
  see abilities below).
- TEST traces still in cataclysmkas.lua: KAS_DestroyerTrace (5 s), KAS_ResourcerTrace, the K_495e80 ping print,
  the kDestroyer "team empty" check; shiprules.lua CAT_REPAIR_TRACE. Remove once Mission 2 is signed off.

**Support Units on the engine's unit cap (2026-10-17: limit works in the range, user-tested; HWRM's rule accepted).**
Costs / providers: `tools/make_supportunits.py` -> `data/scripts/cataclysm/supportunits_gen.lua`.
- install_base.py set_support_units: a "SupportUnits" family (familylist.lua unitcapsFamily, numParam 95),
  supplyLimit("SupportUnits", 250) (SU_CAP) with supplyShow Never; every type in the
  Somtaaw build list gets setSupplyValue(NewShipType, "SupportUnits", <SU>); fillers cat_sufiller25/5/1 (kus_probe's
  model); writes data/scripts/cataclysm/sunative_gen.lua (CatSU_Cap, CatSU_Fillers, CatSU_Native).
- make_race.py lists the fillers in sp_build.lua gated by the undefined research "CAT_NEVER".
- cataclysmkas.lua KAS_SUTick (1 s): used / limit as before; fillers (KAS_SUFillTo) = cap - limit + SU of the
  player's ships the engine doesn't count (non-build-list types: handed-over Kushan / Taiidan, damage copies). The
  label (KAS_SUShow) = used + queued / limit, queued only for display (Player_HasQueuedBuild is 0/1). No more
  build-option restricting for SU. KAS_HyperspaceTick clears the fillers (KAS_SUFillersClear) at SHIPSLEAVING.
- Learned in game (filler tests): a type counts against a cap only if the race's build list has it; a filler in the
  world (hidden) counts, a despawned one doesn't (Complex EVO, MP, relies on despawned ones: not so here).
  SCAR can't read caps (supplyLimit / GetUnitCapForFamily nil); Stats_SquadronsQueued(0, 0) is always 0;
  Player_HasQueuedBuild hides restricted types.
  2026-10-17 (user-tested in the range): HWRM allows a queue while the cap's count is below the limit, whatever
  the unit costs, so the last unit overshoots by up to its cost - 1 (at 245 / 250 a Processor, 13, went in). User:
  accept HWRM's rule for now (engine work below). A limit of 400 was also blocked from ~250 used (fixed filler
  totals 150 / 175 / 275 / 300), so the engine seems to hold a cap near 250 at most: SU_CAP is 250. Cataclysm's
  most (300: Kuun-Lan 70, Hangar 30, 12 Support Modules, 2 Carriers) doesn't fit: open item. The engine's count
  (unit cap popup "UnitCapInfoPopup" with supplyShow "Always"; the build menu never lists the family) read
  213 / 250 at the start (57 counted + 156 fillers) and matched our count + fillers throughout. Source idea: Complex EVO (workshop 398406822, extracted to
  Cataclysm-decomp/reference/complex_evo: leveldata/multiplayer/lib/lib.lua UnitCap, ship/spc_unitcap*).
- To check: module loss / Carrier raise it; fillers not
  selectable / visible / in the sensors manager; roll call unaffected; Mission01's persist2.lua (Profiles/<p>/
  Campaign/CATACLYSM) has no cat_sufiller; Mission 1's handed-over Kushan count (CatSU_Cost has kus_ types).

**Mission 2, meteors, abilities (2026-10-17; engine rules in NOTES.md "Engine rules learned with Mission 2"):**
- Meteors DONE (user-tested in the range): contact against the ship's hull box turned with the ship (KAS_BoxDistance,
  CatHull box, coordsys rows) and the meteor's largest half-extent x KAS_MeteorContact 1.2; swept along the storm's
  velocity since the last check (5 samples); meteors ghosted (SobGroup_SetGhost). The range has a 24-meteor belt
  (range.level KAS_Meteors0, players 2 empty ally / 3 meteors, maxPlayers 4; range.lua RANGE_METEORS; RANGE_MUSIC
  plays a track at the start).
- Music DONE (user-tested): held through HWRM's carried-over fleet arrival and played once the mothership is out
  (K_497000 / KAS_ArrivalWatch, as Gearbox's HW1 Mission02); the sensors manager's music duck lifted whenever it's
  shut (K_496bc0 / KAS_SensorsDuckTick); tools/build_music.py levels every track to one median loudness (--loudness
  2500: track 1 was 3-5x quieter than the rest). Mission 1's loud tracks are a little quieter than before.
- Abilities DONE (user-tested: buttons hide correctly): Link / Unlink / Mimic buttons need a selected ship that has
  the upgrade (shiprules.lua CatUpgrade_Apply keeps cat_has_<UPGRADE>; CatAbilityTick); the selection is read per ship
  (SobGroup_Selected: MainUI_CurrentSelection's group only grows) and the buttons set every tick. Template leftovers:
  ACV's burst attack and the Hive Frigate's repair commented out (install_base.py TEMPLATE_DROP, whole statement),
  the Recon's Speed Burst kept with enable flag 0 (Cataclysm Remastered's way). Worker keeps its kamikaze (user).
- 0x4984c0 is INVULNERABILITY (not paralyse): K_4984c0 = SobGroup_SetInvulnerability, re-applied every second
  (KAS_InvulnerableTick: a despawn / respawn cleared it). Mission02: the BUSHAN-RE from arrival; Fleet Intel's
  briefing right after it is FOUND switches it off (not the ambush's, as first thought), and the pirates killed it
  while the Worker flew there. So a disabled ship keeps it until a repair first holds it still (user: protection ends
  when the Worker gets there; K_4984c0 / KAS_DisabledTick, KAS_InvulnerableHeld; DONE, user-tested 2026-10-18: two
  pirate wings on it, never below ~8k). The disguised corvettes /
  decoy while disguised. Mission01's
  Kushan destroyer uses it too (untested since).
- Ambush (technically working, user; polish built, UNTESTED): disguised team switched to the allied player while
  disguised (shows friendly; left out of the pirates' "Enemy"), visible through the fog (KAS_DisguiseVisible), stops
  at the BUSHAN-RE's sensor edge (K_4924e0 intercept, KAS_InterceptStop kDestroyer 9000; default Cataclysm's 4000),
  drops the disguise with our Mimic's Unmimic shell (MimicOut_kadvancesupportfrigate: make_mimicfx.py
  SCRIPT_DISGUISES; shell from Cataclysm's model, HWRM shows the Remastered one). Far camera focus reveals for 45 s.
- Pirates' "Enemy" leaves out player 2 until it joins where the level starts it unallied (KAS_FillHumanSide).
- Research (2026-10-18, UNTESTED): 0x498c10 is kasfTechSetResearched (cataclysm.exe: marks a tech researched for the
  computer player, "" clears; its args are string addresses, TECH_MIMIC / TECH_SALVAGE for Mission02's pirates), not
  kasfMusicStop (Cataclysm-decomp/out/kas_api.tsv; K_498c10 keeps KAS_CPUTechs, read by CatUpgrade_Researched).
  "unable to unrestrict / grant" were calls on techs already done (HWRM unrestricts only a restricted item and grants
  only an unresearched one): KAS_Unrestrict / KAS_Grant check first. Link's research is fine (needs the Hangar).
- Open: the intermittent access violation loading a mission (NOTES.md; launch with ProcDump attached to catch it);
  autosave "invalid key for next". The BUSHAN-RE stays as it is (stock kus_destroyer; user: HWRM models wherever one
  exists).
- Next: the user checks the skies (Mission 1 planets, Mission 2 brightness / clouds); then a Mission 2 run: research
  (pirates' Mimic / Salvage, no unrestrict / grant warnings), the ambush polish (friendly display, the stop at the
  sensor edge, the transform), the message pod salvaged into the Kuun-Lan and Mission 2's salvaged check; then the
  rest of Mission 2 against the original.

**Engine work (later, with the Veterancy rank stars and the Upgrade UI displays; user, 2026-10-17):**
- Support Units: Cataclysm's queue rule (a unit only if its whole cost fits; HWRM checks count < limit only), the
  build menu's SU line counting every queued unit (Player_HasQueuedBuild is 0/1 per type), and a limit above ~250.
- Veterancy: rank stars as real UI beside the stance icon (script can only message).
- Upgrade UI displays.
- Worker salvage vs RU unloading (2026-10-18, UNTESTED): Workers are back to dock family **Utility** (user: the
  Processor working is a release blocker; as Corvette they nosed into its pads, or with plain paths vanished inside).
  Salvage's carrier rule (FUN_004b14d7 / FUN_004b0a9e mode 5: a plain path for the family and no latch path for it)
  had ruled the Kuun-Lan out through its nose RU latch paths, so the Kuun-Lan has none for now (geo2dae.py --no-res,
  build_kuunlan.sh): Workers unload in its hangar (medium bay, plain "Corvette, Utility") and latch on the Processor's
  pads (Utility latch paths, which also rule the Processor out as a carrier). The nose pads come back later (user).
  Earlier tries (2026-10-17): pod Corvette / Controller (+ no Guard, bay taking Controller); RU paths plain (every
  docking vanished at the nose); RU paths on the Upper Engines module (subsystem dock paths are ignored); Workers as
  Corvette (salvage worked; the Processor didn't). No scripted tow (user). The nosing into the Processor's pads was
  NOT the family: every Processor rebuild since geo2dae.py's .shp latch branch (made for the Kuun-Lan's nose pads)
  faced the Worker wrong; that branch is now opt-in (--shp-latch, the Kuun-Lan only) and the Processor's RES paths
  match its old working model again.

**Other open items:** speech.dat "colliding name" in the log (subtitle file, pre-existing); Carrier Support Modules;
stand-in capitals keep stock damage (turret subsystems shared with Kushan); model conversions for the 23 stand-ins
(REBUILD.md Phase C).

## Earlier resume notes (2026-10-09, after the damage conversion)
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
   user-tested, NOTES.md "The Mimic"):** Mimic button opens a menu of 7 disguises shown on the Mimic's own model (one
   joint each, madstate), with Cataclysm's transformation shell (mesh effects), untargetable while disguised; it keeps
   flying. Research: Fighter Drive + Holographic Emitter. **Kamikaze DONE (2026-10-10, user-tested, NOTES.md
   "Kamikaze"):** its attack is a kamikaze of about 1000 through HWRM's own (health x3.33, MimicArmour), scream
   line 167. Left: the Quantum Explosive Charge multiplier (value not found), asteroid / crate disguises, MCV
   (frigate disguises, kamikaze 2500, its own 167 takes), Advanced Sensors
   detection; ACV EMP (TECH_EMP). (Unmimic shows only for disguised Mimics: the ship rules' cat_disguised group.) Also done: Kuun-Lan module health bars (modules recentred on their hardpoints),
   its tactical overlay distances (stock kus_mothership).
4. Then Mission 1 against the original, the hyperspace exit (K_497290 stub), Missions 02-17.
Open, lower priority: Fire Missiles burst (HWRM can't fire weapons from script; user: keep as-is);
icons for our ability buttons (stock placeholders); sensor freeze / blanket defensive ROE (maybe unneeded since the AI
is off); Siege Cannon; engine loss slowing the Kuun-Lan; Kuun-Lan arrival heading.

## Repositories
| Path | What |
|---|---|
| `C:\Modding\Cataclysm-decomp` | Ghidra project, decompile exports (`out/`), extractors (`tools/`), catalogue, plan. Public: github.com/Ratchex/Cataclysm-DECOMP (2026-10-18, user). Never pushed: `bin/*.exe` (stripped from history), `project/`, `project_hwrm/`, `out/hwrm/`, `extracted/`, `reference/` (other games' and mods' files). |
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

