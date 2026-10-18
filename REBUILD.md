# Rebuild without Cataclysm Remastered / HWU (started 2026-10-14)

**2026-10-17 update:** the HWCR lead developer brought the user aboard (unreleased dev build in C:\Modding\HWCR, from his server). Plan: once Mission 2 works, publish on the Steam Workshop with HWCR as a required item, using their content through that requirement (confirm with them before bundling any of their files). Our converted models and Cataclysm-data pipeline stay; which HWCR assets to bring back is decided case by case.

Goal: no file from Cataclysm Remastered (workshop 2195601016, HWU-derived) in the mod. Everything comes from
Cataclysm's own data (Cataclysm-decomp/extracted), stock HWRM (Gearbox's HW1/HW2 files as templates and stand-ins),
the Players Patch (kept: user, 2026-10-14) and our own tools. Work happens on main (user).

## What Cataclysm Remastered provided (tools/install_cr.py, data/cr_files.txt)
- ship/ (652 files): every smt_* / bst_* ship setup (.ship/.events/.mad), and 23 models we never converted.
- subsystem/, weapon/, missile/ (~1000): their Kuun-Lan/Carrier modules, guns, projectiles.
- scripts/races/ (277): the Somtaaw / Beast race definitions, props, AI, unit caps (+ copies of other races).
- scripts/{weaponfire,attack,formations,strike groups,startingfleets,rules,lib}: mostly copies of stock / PP.
- ui/ (tactical icons, build menu, ship icons), badges/, art/fx (364), sound/sfx (476).

## Approach
The downstream steps of install_cr.py (Cataclysm costs, speeds, damage, repair, harvest, ship rules, events,
variants, speech hooks) already edit ship files with Cataclysm data; only the base layer changes:
1. tools/install_base.py replaces install_cr.py: removes the old CR copies, installs the Players Patch, then
   generates each smt_* / bst_* ship from a stock HW1 template ship (tools/templates.tsv: its .ship, .hod, .events,
   .mad), renamed and set to the Somtaaw / Beast race, then runs the existing Cataclysm patches.
2. Models: our converted ones (tools/build_ship.sh, OUR_MODELS) replace the template's; every other ship keeps its
   template's stock model as a stand-in until converted (user, 2026-10-14). Weapon configs on our models come from
   Cataclysm's .shp guns (Weapon_GUN<n>).
3. Race: our own somtaaw / beast race files (from 430beb3^, the pre-CR Phase 1 race, Kushan-based), familylist from
   stock + PP, build/research from tools/make_race.py.
4. UI / badges / effects / sounds: stock HWRM and PP only; Cataclysm's own sounds where a ship needs its own.
5. Convert the remaining models from Cataclysm's .geo (tools/geo2dae.py, build_ship.sh), one ship at a time.

## Status
- [x] Phase A code: tools/install_base.py (TEMPLATES, RACES, our build families *_Smt / *_Bst, OUR_WEAPONS); the
  manifest removed 2160 CR files; no file in data/ is identical to one only CR has (checked by content); every
  effect, sound and tactical icon the ships name is stock or ours (checked). Models rebuilt without CR inputs
  (build_kuunlan.sh / build_ship.sh: no --glow-from / --engines-from / --dock-from: glow only where --glow-cyan,
  engines geo2dae's own quad, the Kuun-Lan's collector docks from Cataclysm's RES points). make_hullinfo boxes our
  models from their meshes; make_disguise's Acolyte is ours; badges stock (make_colours.py).
- [ ] Phase A test: Missions 1-2 load and play
- Interim gaps: stand-in capitals (destroyer, dreadnought, hive frigate) keep stock damage (their guns are turret
  subsystems shared with the Kushan: make_damage needs per-ship subsystem copies); Carrier Support Modules; a
  Somtaaw / Beast badge of our own; Kuun-Lan glow maps (Cataclysm has none: only --glow-cyan areas).
- [ ] Phase B: weapons / effects / sounds on our models without CR files
- [ ] Phase C: models: carrier, destroyer, dreadnought, hive / multibeam frigates, sentinel, swarmer, MCV, Beast
