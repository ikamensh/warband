"""Procedural sound for Warband: effects and a marching loop synthesised
with :mod:`saga2d.synth` on first run and cached under ``~/.warband``.

The scene calls :func:`play_sound` with an event name; ``__main__`` points
:data:`sound_hook` at a :class:`SoundBank` so it is heard, while tests
leave it ``None``. Combat uses layered weapon/material Foley; routine
deliveries stay silent. Alarms are brass and the music is a slow drum
march under an A-minor drone.
"""

from __future__ import annotations

import random
from pathlib import Path
from collections.abc import Callable, Mapping

import numpy as np

from saga2d import AssetManager, AudioManager, Game, synth
from saga2d.synth import BELL, BRASS, DARK, GLASS, hz, level, mix, noise, pan, thump, tone, write_wav
from saga2d.synth import seconds as sample_times
from warband import combat_sound
from warband.model import Event
from warband.rules import BuildingType, UnitType

Generator = Callable[[], np.ndarray]
IMPACTS = frozenset(f"{weapon}_{material}" for weapon in combat_sound.WEAPONS for material in combat_sound.MATERIALS)

_WEAPONS = {
    UnitType.PEASANT.value: "axe", UnitType.FOOTMAN.value: "sword",
    UnitType.SCOUT.value: "spear", UnitType.KNIGHT.value: "lance",
    UnitType.ARCHER.value: "arrow", UnitType.CATAPULT.value: "stone",
    BuildingType.TOWER.value: "arrow",
}
_BUILDING_MATERIALS = {
    BuildingType.TOWN_HALL.value: "stone", BuildingType.TOWER.value: "stone",
    BuildingType.BLACKSMITH.value: "stone", BuildingType.CHURCH.value: "stone",
    BuildingType.FARM.value: "wood", BuildingType.BARRACKS.value: "wood",
    BuildingType.LUMBER_MILL.value: "wood", BuildingType.STABLES.value: "wood",
    BuildingType.WORKSHOP.value: "wood",
}


def impact_sound(event: Event) -> str:
    """Choose an impact from strike-time facts, even after the victim has died."""
    if event.source_type == event.target_type == "unknown":
        return "impact"  # an explicitly identified older multiplayer event schema
    if event.target_type in _BUILDING_MATERIALS:
        material = _BUILDING_MATERIALS[event.target_type] if event.target_complete else "wood"
    elif UnitType(event.target_type) is UnitType.CATAPULT:
        material = "wood"
    else:
        material = "armor" if event.target_armor > 0 else "flesh"
    return f"{_WEAPONS[event.source_type]}_{material}"


def sound_files(data_dir: Path, sounds: Mapping[str, Generator], music: Mapping[str, Generator]) -> list[Path]:
    """Every WAV a bank with these generators expects under *data_dir*."""
    return [data_dir / "sounds" / f"{name}.wav" for name in sounds] + [data_dir / "music" / f"{name}.wav" for name in music]


def is_generated(data_dir: Path, version: str, sounds: Mapping[str, Generator], music: Mapping[str, Generator]) -> bool:
    marker = data_dir / "sounds" / "VERSION"
    return marker.exists() and marker.read_text() == version and all(path.exists() for path in sound_files(data_dir, sounds, music))


def generate(data_dir: Path, version: str, sounds: Mapping[str, Generator], music: Mapping[str, Generator]) -> None:
    """Synthesise every effect and track into *data_dir*, overwriting; the
    VERSION marker is written last so an interrupted run regenerates."""
    for name, make in sounds.items():
        write_wav(data_dir / "sounds" / f"{name}.wav", make())
    for name, make in music.items():
        write_wav(data_dir / "music" / f"{name}.wav", make())
    (data_dir / "sounds" / "VERSION").write_text(version)


class SynthBank:
    """A game's sounds, generated on first use and played through its own :class:`AudioManager`.

    Parameters:
        game:     The game whose backend plays the audio.
        data_dir: Where the WAVs are cached (``~/.<game>`` is the usual place).
        version:  Bump after changing a generator; a different marker regenerates everything.
        sounds:   Effect name → generator.
        music:    Track name → generator (loops; stereo welcome).
        aliases:  Extra event names mapped onto effects.
    """

    def __init__(
        self, game: Game, data_dir: Path | str, *, version: str, sounds: Mapping[str, Generator],
        music: Mapping[str, Generator] | None = None, aliases: Mapping[str, str] | None = None,
    ) -> None:
        self.data_dir = Path(data_dir).expanduser()
        self.version = version
        self.sounds = dict(sounds)
        self.music = dict(music or {})
        self.aliases = dict(aliases or {})
        if not is_generated(self.data_dir, version, self.sounds, self.music):
            generate(self.data_dir, version, self.sounds, self.music)
        self._audio = AudioManager(game.backend, AssetManager(game.backend, base_path=self.data_dir))
        self._rng = random.Random(0)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self.sounds)

    def play(self, name: str, *, pitch_variation: float = 0.0, volume: float = 1.0) -> None:
        """Play effect *name*.  *pitch_variation* 0.05 shifts the pitch by up
        to ±5 % so a repeated effect does not sound stamped out."""
        name = self.aliases.get(name, name)
        if name not in self.sounds:
            raise KeyError(f"Unknown sound {name!r}. Sounds: {', '.join(self.sounds)}")
        pitch = 1.0 + self._rng.uniform(-pitch_variation, pitch_variation) if pitch_variation else 1.0
        self._audio.play_sound(name, pitch=pitch, volume=volume)

    def start_music(self, name: str) -> None:
        """Start a track looping; a no-op while that track is already playing."""
        if name not in self.music:
            raise KeyError(f"Unknown track {name!r}. Tracks: {', '.join(self.music)}")
        if self._audio.music_name != name:
            self._audio.play_music(name, loop=True)

    def stop_music(self) -> None:
        self._audio.stop_music()

    @property
    def music_playing(self) -> str | None:
        return self._audio.music_name

    def set_volume(self, channel: str, level: float) -> None:
        """*channel* is ``"master"``, ``"music"`` or ``"sfx"``; *level* 0–1."""
        self._audio.set_volume(channel, level)

    def get_volume(self, channel: str) -> float:
        return self._audio.get_volume(channel)

    @property
    def muted(self) -> bool:
        return self._audio.muted

    @muted.setter
    def muted(self, value: bool) -> None:
        self._audio.muted = value


SOUND_VERSION = "3"
MUSIC = "march"
TRACKS = ("march", "vigil")

#: ``play_sound(name)`` forwards here when set; ``None`` is silent.
sound_hook: Callable[[str], None] | None = None
volume_hook: Callable[[str, float], None] | None = None


def play_sound(name: str) -> None:
    if sound_hook is not None:
        sound_hook(name)


def apply_volumes(music: float, sfx: float) -> None:
    if volume_hook is not None:
        volume_hook("music", music)
        volume_hook("sfx", sfx)


# -- Effects (mono, 50–700 ms, A minor) ----------------------------------------


def select() -> np.ndarray:
    return level(mix(tone("E5", 0.08, tau=0.04), (0.05, tone("A5", 0.12, tau=0.06))), 0.5)


def command() -> np.ndarray:
    """A short affirmative: two rising blips."""
    return level(mix(tone("A4", 0.07, tau=0.035, partials=GLASS), (0.06, tone("C5", 0.1, tau=0.05, partials=GLASS))), 0.5)


def attack_command() -> np.ndarray:
    """Harsher: a low pluck and a snare-like rasp."""
    return level(mix(tone("A3", 0.16, tau=0.07, partials=DARK), noise(0.06, 900, 5000, tau=0.02, seed=3) * 0.6), 0.6)


def button() -> np.ndarray:
    return level(mix(noise(0.03, 1800, 7000, tau=0.01, seed=1) * 0.5, tone("A5", 0.05, tau=0.018)), 0.45)


def error() -> np.ndarray:
    return level(mix(tone("C4", 0.12, attack=0.01, tau=0.06, partials=DARK), (0.1, tone("A3", 0.16, attack=0.01, tau=0.08, partials=DARK))), 0.45)


def death() -> np.ndarray:
    """A body falling with cloth and equipment settling, without a musical cue."""
    return level(mix(
        noise(0.16, 180, 1400, attack=0.03, tau=0.055, seed=30) * 0.4,
        (0.06, thump(140, 48, 0.28, attack=0.008, tau=0.065)),
        (0.08, noise(0.23, 90, 750, attack=0.008, tau=0.07, seed=31) * 0.65),
        (0.14, noise(0.16, 800, 3000, tau=0.035, seed=32) * 0.12),
    ), 0.6)


def impact() -> np.ndarray:
    """Neutral contact for servers that supply no weapon or material information."""
    return level(mix(thump(180, 70, 0.14, tau=0.04), noise(0.1, 250, 2400, tau=0.025, seed=22) * 0.6), 0.6)


def chop() -> np.ndarray:
    """An axe biting wood."""
    return level(mix(thump(240, 110, 0.07, tau=0.025), noise(0.09, 300, 2500, tau=0.03, seed=40) * 0.8), 0.7)


def build_start() -> np.ndarray:
    """Hammer taps."""
    return level(mix(*[(i * 0.11, mix(noise(0.05, 1000, 5000, tau=0.014, seed=50 + i) * 0.7, thump(400, 180, 0.05, tau=0.02) * 0.5)) for i in range(3)]), 0.6)


def built() -> np.ndarray:
    """A short rising fanfare in A."""
    layers = [(start, tone(note, 0.22, tau=0.1, partials=GLASS)) for note, start in (("A4", 0.0), ("C5", 0.09), ("E5", 0.18))]
    layers.append((0.27, tone("A5", 0.3, attack=0.01, tau=0.18, partials=GLASS) * 0.8))
    return level(mix(*layers), 0.7)


def trained() -> np.ndarray:
    """Ready: a two-note call."""
    return level(mix(tone("E5", 0.14, attack=0.01, tau=0.08, partials=BRASS) * 0.6, (0.12, tone("A5", 0.22, attack=0.01, tau=0.12, partials=BRASS) * 0.6)), 0.55)


def under_attack() -> np.ndarray:
    """A horn: low fifth, held."""
    return level(mix(tone("A3", 0.6, attack=0.05, tau=0.4, partials=BRASS), tone("E4", 0.6, attack=0.06, tau=0.35, partials=BRASS) * 0.7), 0.7)


def destroyed() -> np.ndarray:
    """Timber and stone coming down."""
    return level(mix(
        thump(120, 35, 0.5, tau=0.18),
        noise(0.45, 80, 900, attack=0.02, tau=0.16, seed=60),
        (0.08, noise(0.3, 400, 3000, attack=0.01, tau=0.1, seed=61) * 0.5),
    ), 0.85)


def victory() -> np.ndarray:
    layers = [(start, tone(note, 0.24, tau=0.1, partials=BRASS) * 0.7) for note, start in (("A4", 0.0), ("C5", 0.1), ("E5", 0.2), ("A5", 0.3))]
    layers += [(0.42, tone(note, 0.4, attack=0.02, tau=0.24, partials=BRASS) * gain) for note, gain in (("A4", 0.5), ("C5", 0.45), ("E5", 0.45), ("A5", 0.4))]
    return level(mix(*layers), 0.85)


def defeat() -> np.ndarray:
    return level(mix(
        tone("E4", 0.3, attack=0.02, tau=0.15, partials=DARK),
        (0.2, tone("D#4", 0.3, attack=0.02, tau=0.15, partials=DARK)),
        (0.4, tone("A3", 0.4, attack=0.02, tau=0.2, partials=DARK)),
        noise(0.6, 70, 350, attack=0.15, tau=0.2, seed=80) * 0.3,
    ), 0.65)


SOUNDS: dict[str, Callable[[], np.ndarray]] = {
    "select": select, "command": command, "attack_command": attack_command, "button": button, "error": error,
    "impact": impact, "death": death, "chop": chop, "build_start": build_start, "built": built,
    "trained": trained, "under_attack": under_attack, "destroyed": destroyed, "victory": victory, "defeat": defeat,
    **combat_sound.SOUNDS,
}

# -- Music -------------------------------------------------------------------

BPM = 88
BEAT = 60 / BPM
BAR = 4 * BEAT
BARS = 16
LOOP_SECONDS = BARS * BAR
_DRONE: tuple[tuple[int, tuple[str, ...]], ...] = (  # (bars, chord)
    (4, ("A2", "E3", "A3", "C4")), (2, ("F2", "C3", "F3", "A3")), (2, ("G2", "D3", "G3", "B3")),
    (4, ("A2", "E3", "A3", "C4")), (2, ("D3", "A3", "D4", "F4")), (2, ("E2", "B2", "E3", "G#3")),
)


def _add_wrapped(out: np.ndarray, clip: np.ndarray, start_seconds: float) -> None:
    n = len(out)
    start = int(round(start_seconds * synth.SAMPLE_RATE)) % n
    first = min(len(clip), n - start)
    out[start:start + first] += clip[:first]
    out[:len(clip) - first] += clip[first:]


def _drone(chord: tuple[str, ...], length: float) -> np.ndarray:
    t = sample_times(length)
    fade = 1.2
    env = np.sin(np.minimum(1.0, t / fade) * np.pi / 2) * np.sin(np.minimum(1.0, (length - t) / fade) * np.pi / 2)
    out = np.zeros((len(t), 2))
    for note in chord:
        freq = hz(note)
        for channel, detune in ((0, 1.002), (1, 0.998)):
            out[:, channel] += np.sin(2 * np.pi * freq * detune * t) + 0.3 * np.sin(2 * np.pi * freq * 2 * detune * t)
    return out * (env / len(chord))[:, None]


def march() -> np.ndarray:
    """A slow drum march under a detuned drone, with a sparse horn line."""
    n = int(round(LOOP_SECONDS * synth.SAMPLE_RATE))
    out = np.zeros((n, 2))
    rng = random.Random(3)
    start = 0.0
    for bars, chord in _DRONE:
        length = bars * BAR
        _add_wrapped(out, 0.5 * _drone(chord, length + 1.2), start - 0.6)
        start += length
    kick = thump(110, 45, 0.25, tau=0.09)
    snare = mix(noise(0.14, 600, 4000, tau=0.045, seed=90), thump(200, 120, 0.08, tau=0.03) * 0.5)
    for beat in range(BARS * 4):
        when = beat * BEAT
        if beat % 4 in (0, 2):
            _add_wrapped(out, pan(kick * 0.9, 0.0), when)
        if beat % 4 == 2 or (beat % 8 == 7 and rng.random() < 0.7):
            _add_wrapped(out, pan(snare * 0.35, 0.3), when)
        if beat % 8 == 7:
            _add_wrapped(out, pan(snare * 0.2, -0.3), when + BEAT / 2)
    horn_line = (("E4", 0), ("A4", 3), ("C5", 6), ("B4", 7), ("A4", 9), ("G4", 11), ("E4", 12))
    for note, bar in horn_line:
        clip = tone(note, 1.6, attack=0.08, tau=0.9, partials=BRASS) * 0.22
        _add_wrapped(out, pan(clip, 0.15 * (-1) ** bar), bar * BAR)
    swell = 0.9 + 0.1 * np.sin(2 * np.pi * sample_times(LOOP_SECONDS) / (LOOP_SECONDS / 2))
    return level(out * swell[:, None], 0.45)


_VIGIL: tuple[tuple[int, tuple[str, ...]], ...] = (
    (4, ("D3", "A3", "D4", "F4")), (4, ("A#2", "F3", "A#3", "D4")), (4, ("C3", "G3", "C4", "E4")), (4, ("D3", "A3", "D4", "F4")),
)


def vigil() -> np.ndarray:
    """The quieter track: a slow D-minor drone with a bell every few bars and no drums — the night watch."""
    n = int(round(LOOP_SECONDS * synth.SAMPLE_RATE))
    out = np.zeros((n, 2))
    start = 0.0
    for bars, chord in _VIGIL:
        length = bars * BAR
        _add_wrapped(out, 0.55 * _drone(chord, length + 1.2), start - 0.6)
        start += length
    rng = random.Random(11)
    for bar in range(BARS):
        if bar % 2 == 0:
            note = rng.choice(("D5", "F5", "A5", "D6"))
            _add_wrapped(out, pan(tone(note, 2.2, attack=0.02, tau=1.1, partials=BELL) * 0.16, rng.uniform(-0.5, 0.5)), bar * BAR + rng.uniform(0, BEAT))
    swell = 0.85 + 0.15 * np.sin(2 * np.pi * sample_times(LOOP_SECONDS) / (LOOP_SECONDS / 3))
    return level(out * swell[:, None], 0.4)


# -- Bank --------------------------------------------------------------------


class SoundBank(SynthBank):
    """Warband's sounds; *data_dir* defaults to ``~/.warband``."""

    def __init__(self, game: Game, data_dir: Path | str | None = None) -> None:
        super().__init__(game, data_dir if data_dir is not None else Path.home() / ".warband", version=SOUND_VERSION,
                         sounds=SOUNDS, music={"march": march, "vigil": vigil})
        self._last_take: dict[str, int] = {}

    def play(self, name: str, *, pitch_variation: float = 0.0, volume: float = 1.0) -> None:
        if name in IMPACTS:
            choices = [take for take in range(combat_sound.VARIANTS) if take != self._last_take.get(name)]
            take = self._rng.choice(choices)
            self._last_take[name] = take
            name = f"{name}_{take}"
            pitch_variation = pitch_variation or 0.045
            volume *= 0.65
        elif name in ("chop", "death"):
            pitch_variation = pitch_variation or 0.05
            volume *= 0.25 if name == "chop" else 0.4
        elif name == "impact":
            pitch_variation = pitch_variation or 0.045
            volume *= 0.65
        super().play(name, pitch_variation=pitch_variation, volume=volume)

    def start_music(self, name: str = MUSIC) -> None:  # type: ignore[override]
        super().start_music(name)


#: ``play_music(name)`` forwards here when set; the match alternates the tracks.
music_hook: Callable[[str], None] | None = None


def play_music(name: str) -> None:
    if music_hook is not None:
        music_hook(name)


def install(game: Game) -> SoundBank:
    """Create the bank, route the game's sound and music events to it and start the music."""
    global sound_hook, volume_hook, music_hook
    bank = SoundBank(game)
    sound_hook = bank.play
    volume_hook = bank.set_volume
    music_hook = bank.start_music
    bank.start_music()
    return bank
