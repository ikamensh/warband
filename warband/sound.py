"""Procedural sound for Warband: effects and music synthesised with :mod:`sagaforge.synth`
and cached under ``~/.warband``.

The scene calls :func:`play_sound` with an event name and :func:`play_music` with a mood;
``__main__`` points the hooks at a :class:`SoundBank` so they are heard, while tests leave
them ``None``.  Combat uses layered weapon/material Foley (:mod:`warband.combat_sound`);
a player's own cues come in their race's voice (:mod:`warband.voices`); each race has a
suite of music (:mod:`warband.music`) that a :class:`~warband.music.Director` plays by mood.

Effects are generated before the first window opens (a second or two).  The music, fifteen
pieces and half a minute of synthesis, is composed in a background thread while the title
shows, the title's own piece first; a piece wanted before it is ready starts, with its
fade, the moment it is.  A new :data:`SOUND_VERSION` discards the whole cache.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import os
from pathlib import Path
import random
import threading
import time

import numpy as np

from saga2d import Game
from sagaforge.synth import BRASS, DARK, GLASS, level, mix, noise, thump, tone, write_wav
from warband import combat_sound, music, voices
from warband.model import Event
from warband.music import Director
from warband.rules import BuildingType, Race, UnitType

Generator = Callable[[], np.ndarray]
IMPACTS = frozenset(f"{weapon}_{material}" for weapon in combat_sound.WEAPONS for material in combat_sound.MATERIALS)

_WEAPONS = {
    UnitType.PEASANT.value: "axe", UnitType.FOOTMAN.value: "sword",
    UnitType.SCOUT.value: "spear", UnitType.KNIGHT.value: "lance",
    UnitType.ARCHER.value: "arrow", UnitType.CATAPULT.value: "stone",
    BuildingType.TOWER.value: "arrow",
}
#: Where a race arms a role differently: orc grunts and axethrowers swing axes and the ogre a club,
#: dwarven ironguards carry axes and bear riders war hammers.  Every other role keeps the common Foley.
_RACE_WEAPONS = {
    Race.ORC: {UnitType.FOOTMAN.value: "axe", UnitType.ARCHER.value: "axe", UnitType.KNIGHT.value: "hammer"},
    Race.DWARF: {UnitType.FOOTMAN.value: "axe", UnitType.KNIGHT.value: "hammer"},
}
_BUILDING_MATERIALS = {
    BuildingType.TOWN_HALL.value: "stone", BuildingType.TOWER.value: "stone",
    BuildingType.BLACKSMITH.value: "stone", BuildingType.CHURCH.value: "stone",
    BuildingType.FARM.value: "wood", BuildingType.BARRACKS.value: "wood",
    BuildingType.LUMBER_MILL.value: "wood", BuildingType.STABLES.value: "wood",
    BuildingType.WORKSHOP.value: "wood",
}


def impact_sound(event: Event, race: Race = Race.HUMAN) -> str:
    """Choose an impact from strike-time facts, even after the victim has died; *race* is the striker's."""
    if event.source_type == event.target_type == "unknown":
        return "impact"  # an explicitly identified older multiplayer event schema
    if event.target_type in _BUILDING_MATERIALS:
        material = _BUILDING_MATERIALS[event.target_type] if event.target_complete else "wood"
    elif UnitType(event.target_type) is UnitType.CATAPULT:
        material = "wood"
    else:
        material = "armor" if event.target_armor > 0 else "flesh"
    weapon = _RACE_WEAPONS.get(race, {}).get(event.source_type) or _WEAPONS[event.source_type]
    return f"{weapon}_{material}"


def sound_files(data_dir: Path, sounds: Mapping[str, Generator], music: Mapping[str, Generator]) -> list[Path]:
    """Every WAV a bank with these generators expects under *data_dir*."""
    return [data_dir / "sounds" / f"{name}.wav" for name in sounds] + [data_dir / "music" / f"{name}.wav" for name in music]


def generate(data_dir: Path, version: str, sounds: Mapping[str, Generator], music: Mapping[str, Generator]) -> None:
    """Synthesise every effect and track into *data_dir*, overwriting; the
    VERSION marker is written last so an interrupted run regenerates."""
    for name, make in sounds.items():
        write_wav(data_dir / "sounds" / f"{name}.wav", make())
    for name, make in music.items():
        write_wav(data_dir / "music" / f"{name}.wav", make())
    (data_dir / "sounds" / "VERSION").write_text(version)


class SynthBank:
    """A game's sounds, generated on first use and played through its ``game.audio``.

    Parameters:
        game:       The game whose audio manager plays everything (so fades follow its clock).
        data_dir:   Where the WAVs are cached (``~/.<game>`` is the usual place).
        version:    Bump after changing a generator; a different marker regenerates everything.
        sounds:     Effect name → generator; all generated before the bank is usable.
        music:      Track name → generator (loops; stereo welcome).  Tracks are composed on
                    demand, or ahead of time by a background thread when *compose* names them.
        aliases:    Extra event names mapped onto effects.
        compose:    Track names to compose in the background, in that order.
    """

    def __init__(
        self, game: Game, data_dir: Path | str, *, version: str, sounds: Mapping[str, Generator],
        music: Mapping[str, Generator] | None = None, aliases: Mapping[str, str] | None = None,
        compose: Iterable[str] = (),
    ) -> None:
        self.data_dir = Path(data_dir).expanduser()
        self.version = version
        self.sounds = dict(sounds)
        self.tracks = dict(music or {})
        self.aliases = dict(aliases or {})
        self._audio = game.audio
        self._rng = random.Random(0)
        self._lock = threading.Lock()  # held while a track is composed
        self._queue_lock = threading.Lock()  # held only to reorder or pop the composer's queue
        self._error: BaseException | None = None
        marker = self.data_dir / "sounds" / "VERSION"
        if not (marker.exists() and marker.read_text() == version and all(path.exists() for path in sound_files(self.data_dir, self.sounds, {}))):
            for stale in (self.data_dir / "music").glob("*.wav"):
                stale.unlink()
            for name, make in self.sounds.items():
                write_wav(self.data_dir / "sounds" / f"{name}.wav", make())
            marker.write_text(version)
        self._ready = {name for name in self.tracks if self.track_path(name).exists()}
        self._queue = [name for name in compose if name not in self._ready]
        for name in self._queue:
            if name not in self.tracks:
                raise KeyError(f"Unknown track {name!r}. Tracks: {', '.join(self.tracks)}")
        self._thread = threading.Thread(target=self._compose, name="compose-music", daemon=True) if self._queue else None
        if self._thread is not None:
            self._thread.start()

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self.sounds)

    def track_path(self, name: str) -> Path:
        return self.data_dir / "music" / f"{name}.wav"

    @property
    def ready(self) -> frozenset[str]:
        """Tracks whose WAV is complete on disk."""
        return frozenset(self._ready)

    def wait(self, timeout: float | None = None) -> None:
        """Block until the background composition finishes; raises what it raised."""
        if self._thread is not None:
            self._thread.join(timeout)
        self._check()

    def prioritize(self, names: Iterable[str]) -> None:
        """Move *names* (those still queued, in this order) to the front of the composer's queue."""
        wanted = [name for name in names if name in self._queue]
        with self._queue_lock:
            self._queue[:] = wanted + [name for name in self._queue if name not in wanted]

    def _compose(self) -> None:
        try:
            while True:
                with self._queue_lock:
                    if not self._queue:
                        return
                    name = self._queue.pop(0)
                self._ensure(name)
        except BaseException as exc:  # surfaced on the game thread by _check
            self._error = exc

    def _check(self) -> None:
        if self._error is not None:
            error, self._error = self._error, None
            raise RuntimeError("Composing music failed in the background") from error

    def _ensure(self, name: str) -> None:
        """Compose *name* now unless it is ready; the file appears whole or not at all."""
        if name in self._ready:  # never wait behind the composer for a track that is already there
            return
        with self._lock:
            if name in self._ready:
                return
            path = self.track_path(name)
            partial = path.with_name(f"{path.stem}.partial.wav")
            write_wav(partial, self.tracks[name]())
            os.replace(partial, path)
            self._ready.add(name)

    def play(self, name: str, *, pitch_variation: float = 0.0, volume: float = 1.0) -> None:
        """Play effect *name*.  *pitch_variation* 0.05 shifts the pitch by up
        to ±5 % so a repeated effect does not sound stamped out."""
        name = self.aliases.get(name, name)
        if name not in self.sounds:
            raise KeyError(f"Unknown sound {name!r}. Sounds: {', '.join(self.sounds)}")
        pitch = 1.0 + self._rng.uniform(-pitch_variation, pitch_variation) if pitch_variation else 1.0
        self._audio.play_sound(str(self.data_dir / "sounds" / f"{name}.wav"), pitch=pitch, volume=volume)

    def start_music(self, name: str, *, loop: bool = True, fade: float = 0.0) -> None:
        """Start a track, composing it first if it is not ready; a no-op while it is already playing."""
        if name not in self.tracks:
            raise KeyError(f"Unknown track {name!r}. Tracks: {', '.join(self.tracks)}")
        self._check()
        self._ensure(name)
        if self.music_playing != name:
            self._audio.play_music(str(self.track_path(name)), loop=loop, fade=fade)

    def stop_music(self, fade: float = 0.0) -> None:
        self._audio.stop_music(fade=fade)

    @property
    def music_playing(self) -> str | None:
        playing = self._audio.music_name
        return None if playing is None else Path(playing).stem

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


SOUND_VERSION = "5"
MUSIC = music.TRACKS

#: ``play_sound(name)`` forwards here when set; ``None`` is silent.
sound_hook: Callable[[str], None] | None = None
volume_hook: Callable[[str, float], None] | None = None
#: ``play_music(mood, race)`` forwards here when set: ``"title"``, ``"peace"``/``"battle"`` with the
#: player's race, or ``"victory"``/``"defeat"`` once.
music_hook: Callable[[str, Race | None], None] | None = None


def play_sound(name: str) -> None:
    if sound_hook is not None:
        sound_hook(name)


def play_music(mood: str, race: Race | None = None) -> None:
    if music_hook is not None:
        music_hook(mood, race)


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
    **voices.SOUNDS,
}

# -- Bank --------------------------------------------------------------------

#: The order the background composer works in: the title first, then each race's suite with the
#: peaceful opener and the battle piece before the second peaceful piece, then the endings.
COMPOSE_ORDER = (music.TITLE_TRACK, *(track for suite in music.SUITES.values() for track in (suite.peace[0], suite.battle, *suite.peace[1:])),
                 *music.STINGERS)


class SoundBank(SynthBank):
    """Warband's sounds; *data_dir* defaults to ``~/.warband``.  With *compose* the music is
    composed in the background in :data:`COMPOSE_ORDER`; without it, on demand."""

    def __init__(self, game: Game, data_dir: Path | str | None = None, *, compose: bool = False) -> None:
        super().__init__(game, data_dir if data_dir is not None else Path.home() / ".warband", version=SOUND_VERSION,
                         sounds=SOUNDS, music=MUSIC, compose=COMPOSE_ORDER if compose else ())
        self._last_take: dict[str, int] = {}
        self._director = Director()
        self._pending: music.Choice | None = None
        self._started = 0.0

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

    def start_music(self, name: str, *, loop: bool = True, fade: float = 0.0) -> None:
        if self.music_playing != name:
            self._started = time.monotonic()
        super().start_music(name, loop=loop, fade=fade)

    def music(self, mood: str, race: Race | None = None) -> None:
        """Ask the director what *mood* needs and start it when its track is ready."""
        choice = self._director.choose(mood, race, time.monotonic(), self.music_playing, self._started)
        if choice is not None:
            self._pending = choice
            if race is not None:  # the player's own suite comes next, whatever the composer was on
                suite = music.SUITES[race]
                self.prioritize((suite.peace[0], suite.battle, *suite.peace[1:]))
        self.poll()

    def poll(self) -> None:
        """Start a wanted track once it is ready; with no composer at work, compose it now."""
        self._check()
        if self._pending is None:
            return
        composing = self._thread is not None and self._thread.is_alive()
        if self._pending.track in self._ready or not composing:
            choice, self._pending = self._pending, None
            self.start_music(choice.track, loop=choice.loop, fade=choice.fade)


def install(game: Game) -> SoundBank:
    """Create the bank, route the game's sound and music events to it and compose the music in the background."""
    global sound_hook, volume_hook, music_hook
    bank = SoundBank(game, compose=True)
    sound_hook = bank.play
    volume_hook = bank.set_volume
    music_hook = bank.music
    game.every(0.25, bank.poll)
    return bank
