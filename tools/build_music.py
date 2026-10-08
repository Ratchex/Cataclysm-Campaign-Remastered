"""Build Cataclysm's music for the mod from Cataclysm-decomp/extracted/audio/music/music_NN.wav (the 62 streams of
Cataclysm's .wxh/.wxd, in stream order):
  data/sound/music/cataclysm/music_NN.wav   resampled from 22050 Hz to 44.1 kHz (HWRM plays WAVs at 44.1 kHz
                                            regardless of their header, as with speech)
  data/sound/music/cataclysm/music_NN.lua   Relic Audio Tool sidecar, as Cataclysm Remastered's music has
kasfMusicPlay(n) plays stream n (cataclysm.exe FUN_00523480 indexes the stream table directly; n = 1102 picks
0-16 at random). The runtime side is K_497000 / K_498c10 in scripts/scar/cataclysmkas.lua.

Usage: build_music.py [--rate 44100] [--volume 0.7]
"""
import argparse
import glob
import os
import subprocess

DECOMP = r"C:\Modding\Cataclysm-decomp"
MOD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FFMPEG = r"C:\Modding\ffmpeg\bin\ffmpeg.exe"
SIDECAR = """-- This file is generated automatically by the Relic Audio Tool

version = 4

volume = 0.900000
randSampContainer = 0

"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=int, default=44100)
    ap.add_argument("--volume", type=float, default=0.7, help="gain (1.0 = as in Cataclysm; that played too loud)")
    a = ap.parse_args()
    out_dir = os.path.join(MOD, "data", "sound", "music", "cataclysm")
    os.makedirs(out_dir, exist_ok=True)
    tracks = sorted(glob.glob(os.path.join(DECOMP, "extracted", "audio", "music", "music_*.wav")))
    for src in tracks:
        name = os.path.splitext(os.path.basename(src))[0]
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-ar", str(a.rate),
                        "-filter:a", f"volume={a.volume}", os.path.join(out_dir, name + ".wav")], check=True)
        with open(os.path.join(out_dir, name + ".lua"), "w", newline="\n") as f:
            f.write(SIDECAR)
    print(f"{len(tracks)} music tracks -> {out_dir}")


if __name__ == "__main__":
    main()
