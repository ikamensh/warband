"""Warband's sound bank: every event has an effect, the WAVs are sane, the loop is seamless."""

import wave
from pathlib import Path

import numpy as np
import pytest

from saga2d import Game, synth
from saga2d.synth import pan, tone
from warband import sound
from warband.sound import SoundBank


@pytest.fixture(scope="session")
def generated(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("warband")
    sound.generate(root, sound.SOUND_VERSION, sound.SOUNDS, sound.MUSIC)
    return root


@pytest.fixture
def game():
    g = Game("Warband Sound", backend="mock")
    yield g
    g._teardown()


@pytest.fixture
def backend(game):
    return game.backend


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as src:
        channels, width, rate, frames = src.getparams()[:4]
        data = np.frombuffer(src.readframes(frames), dtype="<i2").astype(float) / 32768
    return data.reshape(-1, channels), rate


def test_every_scene_event_has_an_effect_that_is_normalised_and_click_free(generated: Path) -> None:
    for name in sound.SOUNDS:
        data, rate = read_wav(generated / "sounds" / f"{name}.wav")
        mono = data[:, 0]
        assert rate == synth.SAMPLE_RATE and 0.03 <= len(mono) / rate <= 1.0, name
        assert 0.15 <= np.abs(mono).max() <= 0.95, name
        assert abs(mono[0]) < 0.01 and abs(mono[-1]) < 0.01, name
        assert np.abs(np.diff(mono)).max() < 0.5, name


@pytest.mark.parametrize("track", sorted(sound.MUSIC))
def test_the_tracks_are_stereo_quiet_and_loop_seamlessly(generated: Path, track: str) -> None:
    data, rate = read_wav(generated / "music" / f"{track}.wav")
    assert data.shape[1] == 2 and 40 <= len(data) / rate <= 46
    assert 0.3 <= np.abs(data).max() <= 0.6
    assert np.abs(data[-1] - data[0]).max() <= np.abs(np.diff(data, axis=0)).max()


def test_install_routes_scene_events_to_the_bank(game: Game, generated: Path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: generated.parent)
    bank = SoundBank(game, data_dir=generated)
    monkeypatch.setattr(sound, "sound_hook", lambda name: bank.play(name))
    sound.play_sound("command")
    assert game.backend.sounds_played[-1]["handle"] == game.backend.load_sound(str(generated / "sounds" / "command.wav"))
    bank.start_music()
    assert bank.music_playing == "vigil"  # the title's night watch; a match starts its race's march


def test_combat_playback_varies_takes_and_respects_sfx_volume(game, generated):
    """Repeated blows use different samples, with room in the mix for alerts."""
    bank = SoundBank(game, data_dir=generated)
    bank.set_volume("sfx", 0.4)
    for _ in range(12):
        bank.play("sword_armor")
    plays = game.backend.sounds_played
    handles = [p["handle"] for p in plays]
    assert len(set(handles)) >= 3
    assert all(a != b for a, b in zip(handles, handles[1:]))
    assert all(0 < p["volume"] < 0.4 and 0.93 <= p["pitch"] <= 1.07 for p in plays)
    bank.muted = True
    count = len(plays)
    bank.play("sword_armor")
    assert len(plays) == count
    assert all(p["volume"] == 0 for p in game.backend.sounds_playing.values())


def test_bank_generates_once_regenerates_on_a_new_version_and_plays(game: Game, backend, tmp_path: Path) -> None:
    sounds = {"ping": lambda: tone("A5", 0.05), "pong": lambda: tone("E5", 0.05)}
    music = {"loop": lambda: pan(tone("A3", 0.3), 0.0)}
    bank = sound.SynthBank(game, tmp_path, version="1", sounds=sounds, music=music, aliases={"click": "ping"})
    files = sound.sound_files(tmp_path, sounds, music)
    assert all(f.exists() for f in files) and (tmp_path / "sounds" / "VERSION").read_text() == "1"
    stamps = {f: f.stat().st_mtime_ns for f in files}
    sound.SynthBank(game, tmp_path, version="1", sounds=sounds, music=music)
    assert {f: f.stat().st_mtime_ns for f in files} == stamps
    bank.play("click", pitch_variation=0.1)
    assert backend.sounds_played[-1]["handle"] == backend.load_sound(str(tmp_path / "sounds" / "ping.wav"))
    assert 0.9 <= backend.sounds_played[-1]["pitch"] <= 1.1
    with pytest.raises(KeyError, match="Unknown sound"):
        bank.play("bang")
    bank.start_music("loop")
    bank.start_music("loop")
    assert bank.music_playing == "loop" and backend.music_playing is not None
    with pytest.raises(KeyError, match="Unknown track"):
        bank.start_music("nope")
    bank.stop_music()
    assert bank.music_playing is None
    (tmp_path / "sounds" / "ping.wav").write_bytes(b"stale")
    sound.SynthBank(game, tmp_path, version="2", sounds=sounds, music=music)
    assert (tmp_path / "sounds" / "VERSION").read_text() == "2" and (tmp_path / "sounds" / "ping.wav").stat().st_size > 100
