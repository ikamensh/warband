"""Warband's sound bank: every event has an effect, the WAVs are sane, the loop is seamless."""

import wave
from pathlib import Path

import numpy as np
import pytest

from saga2d import Game
from warband import sound
from warband.sound import SoundBank


@pytest.fixture(scope="session")
def generated(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("warband")
    sound.synth.generate(root, sound.SOUND_VERSION, sound.SOUNDS, {sound.MUSIC: sound.march})
    return root


@pytest.fixture
def game():
    g = Game("Warband Sound", backend="mock")
    yield g
    g._teardown()


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as src:
        channels, width, rate, frames = src.getparams()[:4]
        data = np.frombuffer(src.readframes(frames), dtype="<i2").astype(float) / 32768
    return data.reshape(-1, channels), rate


def test_every_scene_event_has_an_effect_that_is_normalised_and_click_free(generated: Path) -> None:
    from warband.scene import GameScene  # noqa: F401  (the scene's sfx names are the EVENTS below)

    events = {"select", "command", "attack_command", "hit", "arrow", "death", "chop", "gold", "build_start", "built", "trained",
              "under_attack", "error", "button", "victory", "defeat", "destroyed"}
    assert events == set(sound.SOUNDS)
    for name in events:
        data, rate = read_wav(generated / "sounds" / f"{name}.wav")
        mono = data[:, 0]
        assert rate == sound.synth.SAMPLE_RATE and 0.03 <= len(mono) / rate <= 1.0, name
        assert 0.15 <= np.abs(mono).max() <= 0.95, name
        assert abs(mono[0]) < 0.01 and abs(mono[-1]) < 0.01, name
        assert np.abs(np.diff(mono)).max() < 0.5, name


def test_the_march_is_stereo_quiet_and_loops_seamlessly(generated: Path) -> None:
    data, rate = read_wav(generated / "music" / "march.wav")
    assert data.shape[1] == 2 and 40 <= len(data) / rate <= 46
    assert 0.3 <= np.abs(data).max() <= 0.6
    assert np.abs(data[-1] - data[0]).max() <= np.abs(np.diff(data, axis=0)).max()


def test_install_routes_scene_events_to_the_bank(game: Game, generated: Path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: generated.parent)
    bank = SoundBank(game, data_dir=generated)
    monkeypatch.setattr(sound, "sound_hook", lambda name: bank.play(name))
    sound.play_sound("hit")
    assert game.backend.sounds_played[-1]["handle"] == game.backend.load_sound(str(generated / "sounds" / "hit.wav"))
    bank.start_music()
    assert bank.music_playing == "march"
