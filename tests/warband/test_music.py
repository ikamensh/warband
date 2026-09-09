"""Warband's music: every race has a suite, every piece renders as a balanced loop, the
director plays the right piece for the mood, and the match's mood follows its fighting."""

import random
import threading

import numpy as np
import pytest

from saga2d import Game
from saga2d.synth import SAMPLE_RATE, pan, tone
from warband import music, sound
from warband.instruments import bell
from warband.model import World
from warband.music import PIECES, STINGERS, SUITES, TITLE_TRACK, Choice, Director, Key, Score
from warband.rules import BuildingType, Race, Terrain, UnitType
from warband.scene import GameScene
from warband.style import build_theme


def test_every_race_has_two_peaceful_pieces_and_a_battle_piece_and_all_are_catalogued() -> None:
    assert set(SUITES) == set(Race)
    named = {TITLE_TRACK, *STINGERS}
    for suite in SUITES.values():
        assert len(suite.peace) == 2 and suite.battle not in suite.peace
        named |= {*suite.peace, suite.battle}
    assert named == set(PIECES) == set(music.TRACKS) == set(sound.MUSIC) and len(named) == 15
    assert all(PIECES[name].loop for name in named - set(STINGERS)) and not any(PIECES[name].loop for name in STINGERS)


def test_keys_follow_their_modes() -> None:
    assert Key("A2", "aeolian").midi(0) == 45 and Key("A2", "aeolian").midi(7) == 57
    assert [Key("D3", "lydian").midi(d) for d in range(8)] == [50, 52, 54, 56, 57, 59, 61, 62]
    assert Key("D2", "phrygian").midi(1) == 39 and Key("D2", "phrygian").midi(-1) == 36
    assert Key("A3", "ionian").hz(0) == pytest.approx(220.0)


def test_a_score_wraps_a_loop_and_cuts_a_one_shot_at_its_tail() -> None:
    loop = Score(120, 1)
    loop.add(np.ones(SAMPLE_RATE), 3.5)  # a second-long clip starting a quarter second before the end
    assert loop.out.shape == (2 * SAMPLE_RATE, 2)
    assert loop.out[-1, 0] == pytest.approx(np.cos(np.pi / 4)) and loop.out[0, 0] == pytest.approx(np.cos(np.pi / 4))
    assert loop.out[SAMPLE_RATE, 0] == 0
    shot = Score(120, 1, loop=False, tail=0.5)
    shot.add(np.ones(SAMPLE_RATE), 3.5)
    assert shot.out.shape == (int(2.5 * SAMPLE_RATE), 2) and shot.out[-1, 0] > 0 and shot.out[0, 0] == 0
    first = loop.note(bell, 440.0, 0.1, 1)
    assert loop.note(bell, 440.0, 0.1, 1) is first and loop.note(bell, 440.0, 0.1, 2) is not first


@pytest.mark.parametrize("name", sorted(PIECES))
def test_each_piece_renders_balanced_stereo_at_a_common_loudness(name: str) -> None:
    """Finite, stereo, the catalogued length, one loudness for all, no sub-bass takeover, a quiet seam."""
    piece = PIECES[name]
    clip = piece.render()
    assert clip.shape == (round(piece.seconds * SAMPLE_RATE), 2) and np.all(np.isfinite(clip))
    assert 0.4 <= np.abs(clip).max() <= 0.8
    mono = clip.mean(axis=1)
    assert -21 <= 20 * np.log10(np.sqrt(np.mean(mono ** 2))) <= -13
    spectrum = np.abs(np.fft.rfft(mono[: 2 ** 21])) ** 2
    freqs = np.fft.rfftfreq(min(len(mono), 2 ** 21), 1 / SAMPLE_RATE)
    assert spectrum[freqs < 120].sum() / spectrum.sum() < 0.6
    assert np.corrcoef(clip[:, 0], clip[:, 1])[0, 1] < 0.995  # a real stereo image, not a doubled mono
    if piece.loop:
        assert np.abs(clip[0] - clip[-1]).max() <= np.abs(np.diff(clip, axis=0)).max()
    else:
        assert np.abs(clip[-SAMPLE_RATE // 10:]).max() < 0.01


def test_the_director_plays_the_title_then_peace_battle_and_an_ending_once() -> None:
    d = Director()
    assert d.choose("title", None, 0.0, None, 0.0) == Choice(TITLE_TRACK, 1.0, True)
    assert d.choose("title", None, 1.0, TITLE_TRACK, 0.0) is None
    assert d.choose("peace", Race.ELF, 5.0, TITLE_TRACK, 0.0) == Choice("moonlight", 3.0, True)
    assert d.choose("peace", Race.ELF, 6.0, "moonlight", 5.0) is None
    assert d.choose("battle", Race.ELF, 9.0, "moonlight", 5.0) == Choice("wildhunt", 1.5, True)
    assert d.choose("battle", Race.ELF, 10.0, "wildhunt", 9.0) is None
    assert d.choose("peace", Race.ELF, 15.0, "wildhunt", 9.0) is None  # a battle piece holds for a while
    assert d.choose("peace", Race.ELF, 22.0, "wildhunt", 9.0) == Choice("moonlight", 3.0, True)
    assert d.choose("victory", None, 30.0, "moonlight", 22.0) == Choice("victory", 1.0, False)
    assert d.choose("victory", None, 31.0, "victory", 30.0) is None
    assert d.choose("victory", None, 60.0, None, 30.0) is None  # played once; silence after
    assert d.choose("defeat", None, 61.0, None, 30.0) == Choice("defeat", 0.5, False)
    with pytest.raises(ValueError, match="race"):
        d.choose("peace", None, 0.0, None, 0.0)
    with pytest.raises(ValueError, match="mood"):
        d.choose("panic", Race.ORC, 0.0, None, 0.0)


def test_peaceful_pieces_alternate_at_their_loop_points_with_a_long_crossfade() -> None:
    d = Director()
    first = d.choose("peace", Race.DWARF, 0.0, None, 0.0)
    assert first == Choice("deepforge", 1.0, True)
    length = PIECES["deepforge"].seconds
    assert d.choose("peace", Race.DWARF, length - 1, "deepforge", 0.0) is None
    assert d.choose("peace", Race.DWARF, length + 0.1, "deepforge", 0.0) == Choice("stonehall", 4.0, True)
    later = length + 0.1 + PIECES["stonehall"].seconds
    assert d.choose("peace", Race.DWARF, later, "stonehall", length + 0.1) == Choice("deepforge", 4.0, True)
    # A battle in between resumes with the variant that was due, not always the first.
    d.choose("battle", Race.DWARF, later + 5, "deepforge", later)
    assert d.choose("peace", Race.DWARF, later + 30, "ironwall", later + 5) == Choice("deepforge", 3.0, True)
    assert d.choose("peace", Race.HUMAN, 0.0, None, 0.0) == Choice("hearth", 1.0, True)


@pytest.fixture
def game(tmp_path):
    g = Game("Warband music", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    yield g
    g._teardown()


def test_a_match_asks_for_battle_music_while_its_forces_fight_and_peace_when_they_stop(game, monkeypatch) -> None:
    asked: list[tuple[str, Race | None]] = []
    monkeypatch.setattr(sound, "music_hook", lambda mood, race: asked.append((mood, race)))
    world = World(32, 24, [[Terrain.GRASS] * 32 for _ in range(24)], 2, rng=random.Random(1), races=(Race.ORC, Race.HUMAN))
    world.place_building(0, BuildingType.TOWN_HALL, (4, 4))
    world.place_building(1, BuildingType.TOWN_HALL, (25, 18))
    scene = GameScene(world, seed=1, settings={"tutorial": False})
    scene.brains = []
    game.push(scene)
    game.tick(0.1)
    assert asked[-1] == ("peace", Race.ORC) and scene.mood == "peace"
    for x in (10.5, 11.5, 12.5):
        world.spawn_unit(0, UnitType.FOOTMAN, (x, 10.5))
    victim = world.spawn_unit(1, UnitType.KNIGHT, (11.5, 11.5))
    world.hold([victim.id])
    world.attack([u.id for u in world.player_units(0)], victim.id)
    for _ in range(30):
        game.tick(0.1)
    assert scene.mood == "battle" and asked[-1] == ("battle", Race.ORC)
    world.move([u.id for u in world.player_units(0)], (3.5, 3.5))
    for _ in range(140):
        game.tick(0.1)
    assert scene.mood == "peace" and asked[-1] == ("peace", Race.ORC)


def test_a_bank_composes_music_in_the_background_and_plays_a_wanted_track_once_ready(game, tmp_path) -> None:
    gate = threading.Event()

    def slow_loop() -> np.ndarray:
        gate.wait(5)
        return pan(tone("A3", 0.3), 0.0)

    sounds = {"ping": lambda: tone("A5", 0.05)}
    tracks = {"quick": lambda: pan(tone("E3", 0.3), 0.0), "slow": slow_loop,
              "second": lambda: pan(tone("C3", 0.3), 0.0), "third": lambda: pan(tone("G3", 0.3), 0.0)}
    bank = sound.SynthBank(game, tmp_path, version="1", sounds=sounds, music=tracks, compose=("quick", "slow", "second", "third"))
    deadline = threading.Event()
    while "quick" not in bank.ready and not deadline.wait(0.01):
        pass
    assert "quick" in bank.ready and "slow" not in bank.ready
    assert not (tmp_path / "music" / "slow.wav").exists()
    bank.start_music("quick")  # ready, so it starts without waiting behind the composer, which is inside "slow"
    assert bank.music_playing == "quick"
    bank.prioritize(("third",))  # the queue behind the track in progress is reordered
    gate.set()
    bank.wait()
    assert bank.ready == set(tracks) and (tmp_path / "music" / "slow.wav").exists()
    stamp = lambda name: (tmp_path / "music" / f"{name}.wav").stat().st_mtime_ns  # noqa: E731
    assert stamp("slow") < stamp("third") < stamp("second")
    bank.start_music("slow", fade=1.0)
    assert bank.music_playing == "slow" and len(game.backend.music_players) == 2
    game.tick(1.5)
    assert len(game.backend.music_players) == 1
    with pytest.raises(KeyError, match="Unknown track"):
        sound.SynthBank(game, tmp_path, version="1", sounds=sounds, music=tracks, compose=("nope",))


def test_a_failing_composition_is_reported_on_the_game_thread(game, tmp_path) -> None:
    def broken() -> np.ndarray:
        raise ValueError("no such chord")

    bank = sound.SynthBank(game, tmp_path, version="1", sounds={"ping": lambda: tone("A5", 0.05)}, music={"bad": broken}, compose=("bad",))
    with pytest.raises(RuntimeError, match="Composing music failed") as caught:
        bank.wait()
    assert isinstance(caught.value.__cause__, ValueError)


def test_warbands_bank_moves_between_moods_with_crossfades(game, tmp_path, monkeypatch) -> None:
    """The real director over a tiny catalogue: the title, a race's peace piece, its battle piece, and an ending that ends."""
    tiny = {name: (lambda n=name: pan(tone("A3", 0.2), 0.0)) for name in PIECES}
    monkeypatch.setattr(sound, "MUSIC", tiny)
    bank = sound.SoundBank(game, tmp_path)
    bank.music("title")
    assert bank.music_playing == TITLE_TRACK
    bank.music("peace", Race.HUMAN)
    assert bank.music_playing == "hearth" and len(game.backend.music_players) == 2  # the title fades under the march
    game.tick(3.5)
    assert len(game.backend.music_players) == 1
    bank.music("battle", Race.HUMAN)
    assert bank.music_playing == "clash"
    bank.music("victory")
    assert bank.music_playing == "victory" and game.backend.music_players[-1]["loop"] is False
    game.tick(1.5)  # the battle piece has faded under the fanfare
    (player_id,) = [pid for pid in game.backend._music_players]
    game.backend.stop_player(player_id)  # the ending runs out
    game.tick(1 / 60)
    bank.music("victory")
    assert bank.music_playing is None and game.backend.music_players == []
