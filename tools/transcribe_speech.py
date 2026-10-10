"""Transcribe Cataclysm's unsubtitled speech (unit barks, Fleet Command status lines) with faster-whisper, locally.

Cataclysm's generic speech events (out/speech_events_<bank>.tsv, events below the story range) carry no subtitles and
their numbering is not HW1's named enum, so the text is what tells which HWRM speech event a line belongs to
(tools/make_unitspeech.py). One row per phrase: event, variation, variable, phrase, text.

Writes Cataclysm-decomp/out/speech_text_<bank>.tsv (resumable: phrases already there are skipped).
Usage: transcribe_speech.py [--bank sect] [--limit N] [--model small.en] [--max-event 197]
"""
import argparse
import csv
import os

DECOMP = r"C:\Modding\Cataclysm-decomp"
SPEECH = os.path.join(DECOMP, "extracted", "audio", "speech")


def load16k(path):
    """A 16-bit PCM WAV as float32 mono at 16 kHz (faster-whisper's input; its own decoder needs a newer PyAV)."""
    import wave
    import numpy as np
    with wave.open(path) as w:
        rate, ch = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    if ch > 1:
        x = x.reshape(-1, ch).mean(1)
    n = int(len(x) * 16000 / rate)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default="sect")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default="small.en")
    ap.add_argument("--max-event", type=int, default=197, help="generic events end here (story lines above)")
    a = ap.parse_args()
    from faster_whisper import WhisperModel
    try:
        model = WhisperModel(a.model, device="cuda", compute_type="float32")   # GTX 1080 Ti: no fast float16
        import numpy as np
        list(model.transcribe(np.zeros(16000, np.float32), language="en")[0])  # CUDA libraries load only here
    except Exception as e:                      # no CUDA runtime: CPU int8
        print("CUDA unavailable (%s); using CPU" % str(e)[:80])
        model = WhisperModel(a.model, device="cpu", compute_type="int8")
    rows = []
    with open(os.path.join(DECOMP, "out", f"speech_events_{a.bank}.tsv"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if int(r["event"]) <= a.max_event and not r["subtitle"].strip():
                rows.append(r)
    out = os.path.join(DECOMP, "out", f"speech_text_{a.bank}.tsv")
    done = set()
    if os.path.exists(out):
        with open(out, encoding="utf-8") as f:
            done = {r["phrase"] for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)}
    new = not os.path.exists(out)
    n = 0
    with open(out, "a", encoding="utf-8", newline="\n") as f:
        if new:
            f.write("event\tvariation\tvariable\tphrase\ttext\n")
        for r in rows:
            if r["phrase"] in done:
                continue
            files = [os.path.join(SPEECH, x) for x in r["files"].split(",") if x and not x.startswith("?")]
            texts = []
            for p in files:
                if os.path.exists(p):
                    segs, _ = model.transcribe(load16k(p), language="en", beam_size=5, vad_filter=False)
                    texts.append(" ".join(s.text.strip() for s in segs))
            text = " ".join(t for t in texts if t).replace("\t", " ").replace("\n", " ")
            f.write(f"{r['event']}\t{r['variation']}\t{r['variable']}\t{r['phrase']}\t{text}\n")
            f.flush()
            done.add(r["phrase"])
            n += 1
            if a.limit and n >= a.limit:
                break
    print(f"{n} phrases transcribed -> {out} ({len(done)} total)")


if __name__ == "__main__":
    main()
