"""Build Cataclysm's music for the mod from Cataclysm-decomp/extracted/audio/music/music_NN.wav (the 62 streams of
Cataclysm's .wxh/.wxd, in stream order):
  data/sound/music/cataclysm/music_NN.wav   resampled from 22050 Hz to 44.1 kHz (HWRM plays WAVs at 44.1 kHz
                                            regardless of their header, as with speech)
  data/sound/music/cataclysm/music_NN.lua   Relic Audio Tool sidecar, as Cataclysm Remastered's music has
kasfMusicPlay(n) plays stream n (cataclysm.exe FUN_00523480 indexes the stream table directly; n = 1102 picks
0-16 at random). The runtime side is K_497000 / K_498c10 in scripts/scar/cataclysmkas.lua.

Each track is levelled to the same median loudness (--loudness, 16-bit RMS of one-second windows), never past
clipping: one gain for all (0.5) left the quiet ones lost under the battle (Mission02's track 1, 3-5x quieter than
the others, unheard in the mission: user, 2026-10-17); Cataclysm Remastered's tracks sit at medians 1450-4900.
Usage: build_music.py [--rate 44100] [--loudness 2500]
"""
import argparse
import array
import glob
import math
import os
import subprocess
import wave

DECOMP = r"C:\Modding\Cataclysm-decomp"
MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FFMPEG = r"C:\Modding\ffmpeg\bin\ffmpeg.exe"
SIDECAR = """-- This file is generated automatically by the Relic Audio Tool

version = 4

volume = 0.900000
randSampContainer = 0

"""


def levels(path):
    """(median RMS of its one-second windows, peak) of a 16-bit WAV."""
    w = wave.open(path)
    rate, n, rms, peak = w.getframerate(), w.getnframes(), [], 0
    for start in range(0, n, rate):
        w.setpos(start)
        d = array.array("h", w.readframes(rate))
        if d:
            rms.append(math.sqrt(sum(x * x for x in d[::8]) / len(d[::8])))
            peak = max(peak, max(abs(x) for x in d))
    rms.sort()
    return (rms[len(rms) // 2] if rms else 0), max(peak, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=int, default=44100)
    ap.add_argument("--loudness", type=float, default=2500,
                    help="median RMS each track is levelled to (one gain of 0.7 for all still played too loud)")
    a = ap.parse_args()
    out_dir = os.path.join(MOD, "data", "sound", "music", "cataclysm")
    os.makedirs(out_dir, exist_ok=True)
    tracks = sorted(glob.glob(os.path.join(DECOMP, "extracted", "audio", "music", "music_*.wav")))
    for src in tracks:
        name = os.path.splitext(os.path.basename(src))[0]
        median, peak = levels(src)
        gain = min(a.loudness / median, 0.98 * 32767 / peak) if median > 0 else 1.0
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-ar", str(a.rate),
                        "-filter:a", f"volume={gain:.4f}", os.path.join(out_dir, name + ".wav")], check=True)
        print(f"  {name}: median {median:.0f}, peak {peak}, gain {gain:.2f}")
        with open(os.path.join(out_dir, name + ".lua"), "w", newline="\n") as f:
            f.write(SIDECAR)
    print(f"{len(tracks)} music tracks -> {out_dir}")


if __name__ == "__main__":
    main()
