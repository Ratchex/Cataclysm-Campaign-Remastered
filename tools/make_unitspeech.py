"""Cataclysm's Somtaaw announcer (Fleet Command) and unit barks for HWRM's speech logic.

Cataclysm's generic speech events (out/speech_events_sect.tsv, events 0-197; the variable is the ShipType, so most
barks exist per ship type) were identified from their transcripts (tools/transcribe_speech.py ->
out/speech_text_sect.tsv): e.g. 0 selected ("Roger, command."), 1 move, 5 attack, 11 damaged, 61 "<ship>.
Construction completed.", 101 "<ship> destroyed". PILOT and FLEET below map HWRM speech events (the names the
Players Patch logic passes to playSpeechActor) onto them.

Writes (data/sound/speech is git-ignored):
  data/sound/speech/allships/cat<ship>_1/<event>/<event>.lua + <event>_<n>.wav   per ship type, every variation
      (the stock pilot layout: actor "cat<ship>_" with voice count 1 -> folder cat<ship>_1)
  data/sound/speech/allships/cat_fleet/<event>.wav    Fleet Command lines, flat as stock "fleet" (count 0)
  data/soundscripts/cataclysm/catspeech_gen.lua        tables for data/soundscripts/cataclysm/catspeech.lua
Usage: make_unitspeech.py [--rate 44100]
"""
import argparse
import csv
import os
import re
import shutil
from collections import defaultdict

import build_speech
import make_upgrades

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
DECOMP = r"C:\Modding\Cataclysm-decomp"
SPEECH = os.path.join(DECOMP, "extracted", "audio", "speech")
ALLSHIPS = os.path.join(MOD, "data", "sound", "speech", "allships")
MOTHERSHIP = 18           # ShipType of the Kuun-Lan (sMothership): Fleet Command's own acknowledgements

# HWRM pilot event (regex on the upper-case name) -> Cataclysm event, spoken by the ship's own type
PILOT = [
    (r"COMMAND_(CAPITAL)?SELECTED", 0),                     # "Roger, command." / "Carrier here."
    (r"COMMAND_(MOVE|STRIKEGROUP_MOVE|WAYPOINT|ORDEREDTOENTERNEBULA)", 1),   # "moving out"
    # (Guard: Fleet Command's, not the ship's: FLEET COMMAND_GUARD_1, catspeech.lua CatSpeech_ToFleet)
    (r"COMMAND_MOVECANCELLED", 2),                           # "Standing by, command."
    (r"COMMAND_(ANYSHIPGENERICDOCK\w*|STRIKECRAFTDOCK|\w*RETIRE)", 3),   # "Returning to Hangar."
    (r"(STATUS_CAPITALSHIPSSHIPDOCKED|CHATTER_ANYSHIPDOCKING)", 4),    # "Docked and locked."
    (r"COMMAND_(ATTACK|ATTACK_CAPSHIP|CAPSHIP_TO_ATTACK|BOMBERSUBSYSTEMATTACK|STRIKEGROUP_ATTACK|MOVEATTACK|"
     r"CAP_MOVEATTACK|COMBATMAN|CAP_COMBATMAN)", 5),         # "Target acquired."
    (r"COMMAND_(CAP_)?ATTACK_CANCELLED", 6),                 # "Weapons down."
    (r"COMMAND_FORCEATTACKFRIENDLY", 7),                     # "Be advised that's a friendly."
    (r"COMMAND_FORCEATTACK", 8),                             # "Targeting resources." / "Whatever, command."
    (r"COMMAND_CANNOT", 9),                                  # "Cannot comply, Command."
    (r"(CHATTER_STRIKECRAFTDAMAGED|STATUS_\w*DAMAGED_REPORT\w*)", 11),   # "I need some repairs, command."
    (r"STATUS_CAPITALSHIPDIES", 12),                         # "REACTOR CRITICAL!"
    (r"COMMAND_SETTACTICSPASSIVE", 13),                      # "Taking evasive."
    (r"COMMAND_SETTACTICSDEFENSIVE", 14),                    # "On alert."
    (r"COMMAND_SETTACTICSAGGRESSIVE", 15),                   # "Understood. On high alert."
    (r"(STATUS_GENERICGROUPUNDERATTACK\w*|STATUS_FRIGATE_UNDER_ATTACK|STATUS_V_GENERIC_UNDER_ATTACK)", 17),
    (r"CHATTER_GENERICGROUP(POSITIVE|WINNING)BATTLE_REPORT", 18),     # "We've got them."
    (r"CHATTER_GENERICGROUPSTARTBATTLEADVANTAGED_REPORT", 19),         # "They don't stand a chance."
    (r"CHATTER_GENERICGROUPNEGATIVEBATTLE_REPORT", 20),                # "This is getting rough, Command."
    (r"(CHATTER_GENERICGROUPBATTLEWON_REPORT|STATUS_ ?ATTACKCOMPLETE)", 22),   # "It's all over."
    (r"CHATTER_GENERICGROUPLOSINGBATTLE_REPORT", 23),                  # "We could use some assistance here."
    (r"CHATTER_GENERICGROUPSTARTBATTLEFAIR_REPORT", 24),               # "Pick a target and fire at will."
    (r"STATUS_GENERICGROUPLOSINGBADLY_REPORT", 25),                    # "Command, we must retreat."
    (r"COMMAND_RESOURCECOLLECTORHARVEST", 163),              # Worker: "Understood. Harvesting."
    (r"COMMAND_RESOURCESALVAGE", 150),                       # Worker: "Salvaging."
    (r"COMMAND_STARTEDREPAIRS", 146),                        # "Repairs underway."
    # the salvage-capture order: the Ramming Frigate's Ram (shiprules.lua CatRam_Tick), Cataclysm's attack order
    (r"COMMAND_(INFILTRATORFRIGATE|MARINEFRIGATE)_CAPTURE", 5),   # "Got it! Hitting in." / "Target acquired."
]
# Cataclysm events recorded once for every ship (variable 0), used for any ship type
GENERIC = {146}
# ...except for these Cataclysm types (lower case), which never said it (user: the Processor has no repair order line)
GENERIC_SKIP = {146: {"sprocessor"}}

# HWRM announcer event (exact upper-case name) -> (Cataclysm event, variable)
FLEET = {
    "COMMAND_SELECTED_1": (0, MOTHERSHIP), "COMMAND_MOVE_1": (1, MOTHERSHIP), "COMMAND_WAYPOINT_1": (1, MOTHERSHIP),
    # Guard: Fleet Command's "Escorts assigned." for any ship ordered (user: Cataclysm voices it from Fleet
    # Command, not the ships)
    "COMMAND_GUARD_1": (97, 0), "COMMAND_MOVECANCELLED_1": (2, MOTHERSHIP), "COMMAND_ATTACK": (5, MOTHERSHIP),
    "COMMAND_MOVEATTACK_1": (5, MOTHERSHIP), "COMMAND_COMBATMAN_1": (5, MOTHERSHIP),
    "COMMAND_ATTACK_CANCELLED_1": (6, MOTHERSHIP), "COMMAND_FORCEATTACKFRIENDLY_1": (7, MOTHERSHIP),
    "COMMAND_FORCEATTACK_1": (8, MOTHERSHIP),
    "STATUS_CONSTRUCTIONBEGUN_1": (53, 0), "COMMAND_BUILD_PAUSED": (54, 0), "STATUS_BUILDNORUS_1": (55, 0),
    "COMMAND_CONSTRUCTIONCANCELALL_1": (59, 0),
    "STATUS_RESEARCHCOMPLETE_1": (51, 0), "STATUS_RESEARCHNORUS_1": (50, 0), "STATUS_UPGRADECOMPLETE_1": (149, 0),
    "COMMAND_HS": (32, 0), "STATUS_HYPERSPACECOMPLETE_1": (34, 0), "STATUS_HYPERSPACEINTERUPTED_1": (35, 0),
    "STATUS_MOTHERSHIPUNDERSMALLATTACK_REPORT": (88, 0), "CHATTER_CAPITALSHIPSMALLHITS_QUERY": (88, 0),
    "STATUS_MOTHERSHIPUNDERLARGEATTACK_REPORT": (89, 0),
    "COMMAND_ALLIANCEFORMED_1": (43, 0), "COMMAND_ALLIANCEBROKEN_1": (44, 0), "COMMAND_RUS_TRANSFERRED": (69, 0),
    "STATUS_ENEMYFRIGATECAPTURED_1": (66, 0), "STATUS_ENEMYDESTROYERCAPTURED_1": (66, 0),
    "STATUS_ENEMYCARRIERCAPTURED_1": (66, 0), "STATUS_ENEMYBATTLECRUSIERCAPTURED_1": (66, 0),
    "STATUS_ENEMYSHIPYARDCAPTURED_1": (66, 0),
}
for g in range(1, 11):    # hotkey groups: the variable is the group number ("... Group three.")
    gg = "10" if g == 10 else f"0{g}"
    FLEET[f"STATUS_ASSIGNEDGROUPUNDERATTACK_REPORT_G{g}"] = (91, g)   # "Report of hostiles by Group n."
    FLEET[f"COMMAND_GROUP_ASSIGNED_{gg}"] = (99, g)                    # "Setting assigned. Group n."
    FLEET[f"STATUS_HOTKEYGROUP_VICTORY_{gg}"] = (94, g)                # "Group n. Reports that enemy has retreated."
    FLEET[f"STATUS_HOTKEYGROUP_DEFEAT_{gg}"] = (118, 0)                # "Group destroyed."
    # the group's key pressed (HWRM CommandHotKeyGroupSelected, ACT_Selected: a pilot's COMMAND_SelectGroup0n; Fleet
    # Command's in Cataclysm, catspeech.lua CatSpeech_ToFleet)
    FLEET[f"COMMAND_SELECTGROUP{gg}"] = (92, g)                           # "Stand by. Group n."
    # ships added to the group (HWRM CommandHotKeyGroupSelected, ACT_Reinforced; its group 10 event is "_20_2")
    FLEET[f"STATUS_HOTKEYGROUP_ADDED_{'20' if g == 10 else gg}_2"] = (100, g)   # "Adding ships to... Group n."
# per ship type announcer lines, played by catspeech.lua itself: CAT_BUILT_<type>, CAT_DESTROYED_<type>,
# CAT_AVAILABLE_<type> ("<ship> is now available for construction")
PER_TYPE = {"CAT_BUILT": 61, "CAT_DESTROYED": 101, "CAT_AVAILABLE": 52}
# Kuun-Lan modules coming online (event 48, the variable is Cataclysm's module index): our subsystem -> variable
MODULE_ONLINE = 48
MODULES = {"smt_kl_dockingbay": 0, "smt_kl_armour": 1, "smt_kl_micro": 2, "smt_kl_special": 3, "smt_kl_weapons": 4}
# "<technology> available. Upgrade <ships>." (event 188, the variable is the TechnologyType): played by the mission
# script when the player gains that research (cataclysmkas.lua CatTechLineTick)
TECH_LINE = 188


def load():
    rows = defaultdict(list)   # (event, variable) -> [row per variation]
    with open(os.path.join(DECOMP, "out", "speech_events_sect.tsv"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            files = [x for x in r["files"].split(",") if x and not x.startswith("?")]
            if files and int(r["event"]) <= 197:
                rows[(int(r["event"]), int(r["variable"]))].append(files)
    return rows


def write_clip(files, out, rate):
    paths = [os.path.join(SPEECH, x) for x in files]
    if all(os.path.exists(p) for p in paths):
        build_speech.join_wavs(paths, out, rate)
        return True
    return False


def wav_secs(path):
    import wave
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


FLEET_SECS = {}   # announcer event -> its longest recording, seconds (catspeech.lua: no repeat while it plays)


def write_fleet(fleet_dir, key, variants, rate, ce):
    """An announcer line: every Cataclysm recording of it, played at random (user: selecting the Kuun-Lan always said
    "Bridge"). One recording: <key>.wav, flat as stock "fleet"; more: <key>/<key>.lua (a random sample container, as
    Cataclysm Remastered's Beast announcer) + <key>_<n>.wav. True if anything was written."""
    variants = [f for f in variants if all(os.path.exists(os.path.join(SPEECH, x)) for x in f)]
    if len(variants) == 1:
        out = os.path.join(fleet_dir, key.lower() + ".wav")
        if write_clip(variants[0], out, rate):
            FLEET_SECS[key] = wav_secs(out)
            return True
        return False
    if not variants:
        return False
    d = os.path.join(fleet_dir, key.lower())
    os.makedirs(d, exist_ok=True)
    for k, files in enumerate(variants):
        out = os.path.join(d, f"{key.lower()}_{k + 1}.wav")
        if write_clip(files, out, rate):
            FLEET_SECS[key] = max(FLEET_SECS.get(key, 0), wav_secs(out))
    with open(os.path.join(d, key.lower() + ".lua"), "w", newline="\n") as f:
        f.write("-- Cataclysm-HWRM: Cataclysm speech event %d (tools/make_unitspeech.py)\n"
                "version = 4\nrandSampContainer = 1\n" % ce)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=int, default=44100)
    a = ap.parse_args()
    rows = load()
    types = make_upgrades.ship_types()
    hwrm = defaultdict(list)                       # Cataclysm type -> our HWRM ship names
    for line in list(open(os.path.join(HERE, "shipmap.tsv"), encoding="utf-8"))[1:]:
        c = line.rstrip("\n").split("\t")
        if len(c) > 2 and c[0] == "RACE_SECT" and c[2]:
            hwrm[c[1]].append(c[2].lower())
    for d in os.listdir(ALLSHIPS) if os.path.isdir(ALLSHIPS) else []:
        if d.startswith("cat"):
            shutil.rmtree(os.path.join(ALLSHIPS, d))

    pilot_events = sorted({m for m in re.findall(r"[A-Z_ ]{4,}", " ".join(p for p, _ in PILOT))})
    # the event names the logic actually passes: listed in the speech logic files
    # (Players Patch's pristine copies: the installed ones call CatSpeech_Play, install_base.py patch_speech_logic)
    logic = r"C:\Modding\Cataclysm-decomp\reference\players_patch\soundscripts\speechlogic"
    names = set()
    for fn in ("commands.lua", "status.lua", "chatter.lua"):
        for m in re.finditer(r'playSpeechActor\w*\(\s*"([^"]+)"', open(os.path.join(logic, fn), encoding="latin-1").read()):
            names.add(m.group(1).upper())
    folders, lines, n_pilot = {}, {}, 0
    for v, cat in enumerate(types):
        if cat not in hwrm:
            continue
        base = "cat" + cat[1:] + "_"
        got = {}
        for ev_name in sorted(names):
            ce = next((e for p, e in PILOT if re.fullmatch(p, ev_name)), None)
            if ce is None:
                continue
            generic = ce in GENERIC and cat.lower() not in GENERIC_SKIP.get(ce, ())
            variants = rows.get((ce, v)) or (rows.get((ce, 0)) if generic else None)
            if not variants:
                continue
            d = os.path.join(ALLSHIPS, base + "1", ev_name.lower())
            os.makedirs(d, exist_ok=True)
            k, secs = 0, 0
            for files in variants:
                out = os.path.join(d, f"{ev_name.lower()}_{k + 1}.wav")
                if write_clip(files, out, a.rate):
                    secs = max(secs, wav_secs(out))
                    k += 1
            if k:
                with open(os.path.join(d, ev_name.lower() + ".lua"), "w", newline="\n") as f:
                    f.write("-- Cataclysm-HWRM: Cataclysm speech event %d (tools/make_unitspeech.py)\n"
                            "version = 4\nrandSampContainer = 1\n" % ce)
                got[ev_name] = secs
                n_pilot += k
        if got:
            for name in hwrm[cat]:
                folders[name] = base
            lines[base] = got
    fleet_dir = os.path.join(ALLSHIPS, "cat_fleet")
    os.makedirs(fleet_dir, exist_ok=True)
    fleet = {}
    for key, (ce, v) in FLEET.items():
        variants = rows.get((ce, v))
        if variants and write_fleet(fleet_dir, key, variants, a.rate, ce):
            fleet[key] = key
    per_type, var_of = {}, {}
    for prefix, ce in PER_TYPE.items():
        for v, cat in enumerate(types):
            if cat in hwrm and rows.get((ce, v)):
                key = f"{prefix}_{cat[1:].upper()}"
                if write_fleet(fleet_dir, key, rows[(ce, v)], a.rate, ce):
                    for name in hwrm[cat]:
                        # module dummy ships share their subsystem's name minus _dummy
                        for alias in {name, name[:-len("_dummy")] if name.endswith("_dummy") else name}:
                            per_type.setdefault(alias, cat[1:].upper())
    for v, cat in enumerate(types):
        for name in hwrm.get(cat, []):
            var_of.setdefault(name, v)
    modules = {}
    for sub, v in MODULES.items():
        if rows.get((MODULE_ONLINE, v)):
            key = "CAT_MODULE_" + sub[len("smt_kl_"):].upper()
            if write_fleet(fleet_dir, key, rows[(MODULE_ONLINE, v)], a.rate, MODULE_ONLINE):
                modules[sub] = key
    tech_line = {make_upgrades.TECHS[v]: v for (e, v) in rows if e == TECH_LINE and v < len(make_upgrades.TECHS)}

    out = os.path.join(MOD, "data", "soundscripts", "cataclysm", "catspeech_gen.lua")
    with open(out, "w", newline="\n") as f:
        f.write("-- Generated by tools/make_unitspeech.py: Cataclysm's Somtaaw voices (see catspeech.lua)\n")
        f.write("CatSpeech_Folders = {   -- our ship type -> its voice folder base (folder <base>1)\n")
        for k in sorted(folders):
            f.write(f'    ["{k.upper()}"] = "{folders[k]}",\n')
        f.write("}\nCatSpeech_Lines = {     -- voice folder base -> its events: the longest recording, seconds\n")
        for b in sorted(lines):
            f.write(f'    ["{b}"] = {{ ' + ", ".join(f"{e} = {lines[b][e]:.2f}" for e in sorted(lines[b])
                                              if re.fullmatch(r"\w+", e))
                    + " },\n")
        f.write("}\nCatSpeech_Fleet = {      -- announcer events with a Fleet Command line (cat_fleet/<event>.wav)\n")
        for k in sorted(fleet):
            f.write(f'    {k} = "{k}",\n')
        f.write("}\nCatSpeech_Type = {       -- our ship type -> CAT_BUILT_ / CAT_DESTROYED_ / CAT_AVAILABLE_<x> in cat_fleet\n")
        for k in sorted(per_type):
            f.write(f'    ["{k.upper()}"] = "{per_type[k]}",\n')
        f.write("}\nCatSpeech_Module = {     -- Kuun-Lan module subsystem -> its \"... module is now online\" line\n")
        for k in sorted(modules):
            f.write(f'    ["{k.upper()}"] = "{modules[k]}",\n')
        f.write("}\nCatSpeech_Var = {        -- our ship type -> Cataclysm ShipType (the speech variable; mission barks)\n")
        for k in sorted(var_of):
            f.write(f'    ["{k}"] = {var_of[k]},\n')
        f.write("}\nCatSpeech_Secs = {       -- announcer event -> its length, seconds (the longest recording)\n")
        for k in sorted(FLEET_SECS):
            f.write(f"    {k} = {FLEET_SECS[k]:.2f},\n")
        f.write("}\nCatSpeech_TechLine = {   -- research -> its \"<tech> available\" line (event %d variable)\n" % TECH_LINE)
        for k in sorted(tech_line):
            f.write(f'    {k} = {tech_line[k]},\n')
        f.write("}\n")
    print(f"{len(lines)} ship voices, {n_pilot} pilot lines over {sum(len(v) for v in lines.values())} events; "
          f"{len(fleet)} Fleet Command events, {len(per_type)} ship types with built/destroyed lines -> {out}")


if __name__ == "__main__":
    main()
