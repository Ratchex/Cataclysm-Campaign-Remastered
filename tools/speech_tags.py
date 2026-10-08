"""Subtitles for Cataclysm's unsubtitled speech (shared by tools/build_speech.py and tools/nis2hwrm.py).

HWRM plays nothing for a line whose subtitle string is blank (speechEventActor in NIS, Subtitle_AddSkippable in
missions: it returns 0; confirmed in game with n01's pilot chatter), so every unsubtitled line the missions or
cutscenes play gets a speaker tag: tools/speech_speakers.tsv for the lines whose speaker is known, else one from
the actor bits the line is played with (Cataclysm: 0x800 a ship's pilot, 0x1000 Fleet Command, 0x2000 Tactical
Officer, others: allied / alien / other fleets). A no-break space showed as "?" in game.
"""
import csv
import glob
import os
import re

DECOMP = r"C:\Modding\Cataclysm-decomp"
MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEAKERS_TSV = os.path.join(MOD, "tools", "speech_speakers.tsv")
TAG_BY_BITS = {0x800: "(Pilot)", 0x1000: "(Fleet Command)", 0x2000: "(Tactical Officer)"}
DEFAULT_TAG = "(Comms)"
ACTOR_MASK = 0x3FC00


def call_site_bits():
    """Speech event -> actor bits, from every call: NIS scripts (fleetSpeechEvent / speechEvent) and the missions'
    kasfSpeechEvent (decompiled K_496eb0 constants)."""
    bits = {}
    for path in sorted(glob.glob(os.path.join(DECOMP, "extracted", "big", "nis", "*.script"))):
        for m in re.finditer(r"(?i)(?:fleet)?speechEvent\s*\(([0-9+ ]+)\)", open(path, encoding="latin-1").read()):
            v = eval(m.group(1))
            bits.setdefault(v & 0x3FF, v & ACTOR_MASK)
    for path in sorted(glob.glob(os.path.join(DECOMP, "out", "missions", "*.c"))):
        for m in re.finditer(r"K_496eb0\((0x[0-9a-fA-F]+|\d+)", open(path, encoding="latin-1").read()):
            v = int(m.group(1), 0)
            bits.setdefault(v & 0x3FF, v & ACTOR_MASK)
    return bits


def known_speakers():
    """String id -> tag from tools/speech_speakers.tsv (id, tag, where heard)."""
    if not os.path.exists(SPEAKERS_TSV):
        return {}
    with open(SPEAKERS_TSV, encoding="utf-8") as f:
        return {int(r["id"]): r["tag"] for r in csv.DictReader(f, delimiter="\t")}


class Tagger:
    def __init__(self):
        self.bits = call_site_bits()
        self.known = known_speakers()

    def tag(self, event, sid):
        """Subtitle for an unsubtitled phrase, or None when nothing plays it (the engine's own ship chatter)."""
        if sid in self.known:
            return self.known[sid]
        if event not in self.bits:
            return None
        return TAG_BY_BITS.get(self.bits[event], DEFAULT_TAG)
