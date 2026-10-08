"""Subtitles for Cataclysm's unsubtitled speech (shared by tools/build_speech.py and tools/nis2hwrm.py).

HWRM plays nothing for a line whose subtitle string is blank (speechEventActor in NIS, Subtitle_AddSkippable in
missions: it returns 0; confirmed in game with n01's pilot chatter). Every unsubtitled phrase gets INVISIBLE
instead: empty colour tags, which count as text but draw nothing (in game: the speaker's portrait, no subtitle;
nislet01 test of 11 candidates: a no-break space showed "?", most others visible marks).

tools/speech_speakers.tsv names the speaker of lines whose speaker is known (from the original); nis2hwrm uses it
for the portrait (actor) where the actor bits say otherwise (n01's Fleet Command line has the pilots' 0x800).
"""
import csv
import os

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEAKERS_TSV = os.path.join(MOD, "tools", "speech_speakers.tsv")
INVISIBLE = "<c=ffffff></c>"


def known_speakers():
    """String id -> speaker ("Fleet Command", "Worker", ...) from tools/speech_speakers.tsv (id, speaker, heard)."""
    if not os.path.exists(SPEAKERS_TSV):
        return {}
    with open(SPEAKERS_TSV, encoding="utf-8") as f:
        return {int(r["id"]): r["speaker"] for r in csv.DictReader(f, delimiter="\t")}
