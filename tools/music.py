"""Render Warband's music to look at and listen to.

    uv run python tools/music_warband.py render DIR [--tracks a,b]   # WAV, spectrogram PNG and a stats table per track
    uv run python tools/music_warband.py sampler DIR [--seconds 12]  # an excerpt of every track in one WAV (M4A too when afconvert exists)

The spectrogram shows 40 Hz–12 kHz on a log axis over the whole track, with the
loudness envelope above it and a bar grid, so an arrangement can be checked at a
glance: where the drums enter, whether the melody sits above the pad, whether the
loop's seam is quiet.  The stats table gives loudness, crest factor, spectral
centroid, the share of energy below 120 Hz and above 6 kHz, and the seam jump.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from saga2d.synth import SAMPLE_RATE, write_wav  # noqa: E402
from warband import music  # noqa: E402


def spectrogram(clip: np.ndarray, *, width: int = 1600, height: int = 360, bars: int | None = None, bpm: float | None = None) -> Image.Image:
    mono = clip.mean(axis=1) if clip.ndim == 2 else clip
    frame, low, high = 4096, 40.0, 12000.0
    hop = max(1, (len(mono) - frame) // width)
    window = np.hanning(frame)
    freqs = np.fft.rfftfreq(frame, 1 / SAMPLE_RATE)
    rows = np.geomspace(low, high, height)
    columns = np.empty((height, width))
    for x in range(width):
        start = min(x * hop, len(mono) - frame)
        magnitude = np.abs(np.fft.rfft(mono[start:start + frame] * window))
        columns[:, x] = np.interp(rows, freqs, magnitude)
    db = 20 * np.log10(columns + 1e-9)
    top = db.max()
    shade = np.clip((db - (top - 70)) / 70, 0, 1)[::-1]  # low frequencies at the bottom
    rgb = np.stack([shade ** 0.8 * 255, shade ** 1.6 * 200 + shade * 30, np.sqrt(shade) * 120 + (1 - shade) * 20], axis=-1).astype(np.uint8)
    strip = 60
    image = Image.new("RGB", (width, height + strip), (12, 12, 16))
    image.paste(Image.fromarray(rgb), (0, strip))
    draw = ImageDraw.Draw(image)
    envelope = np.sqrt(np.convolve(mono ** 2, np.ones(2205) / 2205, mode="same"))
    step = len(envelope) / width
    for x in range(width):
        loudness = envelope[int(x * step)]
        h = int(min(strip - 4, loudness * strip * 4))
        draw.line([(x, strip - 2), (x, strip - 2 - h)], fill=(120, 200, 255))
    if bars and bpm:
        seconds_per_bar = 4 * 60 / bpm
        for bar in range(0, bars + 1, 8):
            x = int(bar * seconds_per_bar * SAMPLE_RATE / len(mono) * width)
            draw.line([(x, 0), (x, height + strip)], fill=(255, 255, 255) if bar % 32 == 0 else (110, 110, 130))
            draw.text((x + 3, 2), f"bar {bar}", fill=(230, 230, 230))
    for hz in (100, 250, 500, 1000, 2000, 4000, 8000):
        y = strip + height - int(np.log(hz / low) / np.log(high / low) * height)
        draw.line([(0, y), (24, y)], fill=(200, 200, 200))
        draw.text((28, y - 6), f"{hz}", fill=(200, 200, 200))
    return image


def stats(clip: np.ndarray) -> dict[str, float]:
    mono = clip.mean(axis=1)
    rms = float(np.sqrt(np.mean(mono ** 2)))
    spectrum = np.abs(np.fft.rfft(mono[: 2 ** 22])) ** 2
    freqs = np.fft.rfftfreq(min(len(mono), 2 ** 22), 1 / SAMPLE_RATE)
    total = spectrum.sum()
    return {
        "seconds": len(clip) / SAMPLE_RATE,
        "rms_db": 20 * np.log10(rms),
        "peak": float(np.abs(clip).max()),
        "crest_db": 20 * np.log10(np.abs(clip).max() / rms),
        "centroid_hz": float((freqs * spectrum).sum() / total),
        "low_share": float(spectrum[freqs < 120].sum() / total),
        "high_share": float(spectrum[freqs > 6000].sum() / total),
        "seam": float(np.abs(clip[0] - clip[-1]).max()),
        "max_step": float(np.abs(np.diff(clip, axis=0)).max()),
    }


def render(out: Path, names: list[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    print(f"{'track':10s} {'gen s':>6s} {'length':>7s} {'rms dB':>7s} {'peak':>5s} {'crest':>6s} {'centr':>6s} {'<120':>5s} {'>6k':>5s} {'seam':>6s} {'step':>5s}")
    for name in names:
        started = time.perf_counter()
        clip = music.TRACKS[name]()
        elapsed = time.perf_counter() - started
        write_wav(out / f"{name}.wav", clip)
        piece = music.PIECES[name]
        spectrogram(clip, bars=piece.bars, bpm=piece.bpm).save(out / f"{name}.png")
        s = stats(clip)
        print(f"{name:10s} {elapsed:6.2f} {s['seconds']:7.1f} {s['rms_db']:7.1f} {s['peak']:5.2f} {s['crest_db']:6.1f} {s['centroid_hz']:6.0f} "
              f"{s['low_share']:5.2f} {s['high_share']:5.3f} {s['seam']:6.3f} {s['max_step']:5.2f}")


def sampler(out: Path, seconds: float) -> None:
    out.mkdir(parents=True, exist_ok=True)
    pieces = []
    gap = np.zeros((int(0.8 * SAMPLE_RATE), 2))
    for name, make in music.TRACKS.items():
        clip = make()
        excerpt = clip[: int(seconds * SAMPLE_RATE)].copy() if music.PIECES[name].loop else clip
        fade = min(len(excerpt), int(0.5 * SAMPLE_RATE))
        excerpt[-fade:] *= np.linspace(1, 0, fade)[:, None]
        pieces += [excerpt, gap]
        print(f"{name:10s} starts at {sum(len(p) for p in pieces[:-2]) / SAMPLE_RATE:6.1f} s")
    wav = out / "warband-music-sampler.wav"
    write_wav(wav, np.concatenate(pieces))
    if shutil.which("afconvert"):
        m4a = wav.with_suffix(".m4a")
        subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", "160000", str(wav), str(m4a)], check=True)
        print(f"wrote {wav} and {m4a}")
    else:
        print(f"wrote {wav}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    render_cmd = commands.add_parser("render")
    render_cmd.add_argument("dir", type=Path)
    render_cmd.add_argument("--tracks", default=",".join(music.TRACKS), help="comma-separated track names")
    sampler_cmd = commands.add_parser("sampler")
    sampler_cmd.add_argument("dir", type=Path)
    sampler_cmd.add_argument("--seconds", type=float, default=12.0)
    args = parser.parse_args()
    if args.command == "render":
        render(args.dir, args.tracks.split(","))
    else:
        sampler(args.dir, args.seconds)


if __name__ == "__main__":
    main()
