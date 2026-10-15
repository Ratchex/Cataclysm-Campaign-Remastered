"""Every voice line goes through Cataclysm's speech queue (data/scripts/scar/cataclysmvoice.lua, CatVoice_Event):
fail when a script plays speech any other way.

  scripts (data/scripts, data/leveldata): Subtitle_AddSkippable / Subtitle_Add / Sound_SpeechPlay only in
      cataclysmvoice.lua (scar_util.lua is Gearbox's, unused by us)
  the engine's speech logic: playSpeechActor(Linked) only in data/soundscripts/cataclysm/catspeech.lua (its calls go
      through CatSpeech_Play, tools/install_base.py)

Run by tools/build_mission.py; usage: check_voice.py
"""
import os
import re
import sys

MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = [
    (("data/scripts", "data/leveldata"), re.compile(r"\b(Subtitle_AddSkippable|Subtitle_Add|Sound_SpeechPlay)\s*\("),
     {"data/scripts/scar/cataclysmvoice.lua", "data/scripts/scar/scar_util.lua"}),
    (("data/soundscripts",), re.compile(r"\bplaySpeechActor(Linked)?\s*\("),
     {"data/soundscripts/cataclysm/catspeech.lua"}),
]


def main():
    bad = []
    for roots, pat, allowed in RULES:
        for root in roots:
            for d, _, files in os.walk(os.path.join(MOD, root)):
                for fn in files:
                    if not fn.endswith(".lua"):
                        continue
                    path = os.path.join(d, fn)
                    rel = os.path.relpath(path, MOD).replace("\\", "/")
                    if rel in allowed:
                        continue
                    for n, line in enumerate(open(path, encoding="latin-1"), 1):
                        if pat.search(line.split("--")[0]):
                            bad.append(f"{rel}:{n}: {line.strip()}")
    if bad:
        print("speech played outside the queue (use CatVoice_Event, data/scripts/scar/cataclysmvoice.lua):")
        print("\n".join("  " + b for b in bad))
        sys.exit(1)
    print("voice: every line goes through the queue")


if __name__ == "__main__":
    main()
