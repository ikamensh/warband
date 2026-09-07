"""Write a labeled combat comparison and verify hidden, silent native playback.

    uv run python tools/verify_warband_audio.py /tmp/warband-audio
    uv run python tools/verify_warband_audio.py --preview-only

Native verification uses pyglet's silent driver, never the speakers. It checks
the actual player's start, natural end-of-source event, and resource release.
The display must be awake to capture the representative battle frame.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SAGA2D_SILENT"] = "1"
os.environ["SAGA2D_HEADLESS"] = "1"

import numpy as np

from saga2d import Game, fonts
from saga2d.synth import SAMPLE_RATE, mix, write_wav
from tools.native_frames import tick
from warband import combat_sound, sound
from warband.model import World
from warband.rules import BuildingType, Terrain, UnitType
from warband.scene import GameScene
from warband.style import build_theme


def comparison(output: Path) -> dict:
    """Compare materials first, then weapon weight, repeated takes, and layering."""
    showcases = [f"sword_{material}" for material in combat_sound.MATERIALS]
    showcases += ["axe_wood", "spear_flesh", "lance_armor", "arrow_wood", "stone_stone"]
    clips, cues = [], []
    when = 0.25

    def add(name: str, take: int, start: float, section: str) -> float:
        # Match SoundBank's impact gain, retaining the differences between weapons.
        clip = combat_sound.SOUNDS[f"{name}_{take}"]() * 0.65
        clips.append((start, clip))
        end = start + len(clip) / SAMPLE_RATE
        cues.append({"start": round(start, 3), "end": round(end, 3),
                     "section": section, "sound": name, "take": take + 1})
        return end

    for name in showcases:
        for take in range(combat_sound.VARIANTS):
            when = add(name, take, when, "comparison") + 0.20
        when += 0.35

    skirmish_start = when + 0.35
    skirmish = ["sword_armor", "arrow_flesh", "sword_flesh", "axe_wood", "lance_armor", "stone_wood",
                "sword_armor", "spear_flesh", "arrow_armor", "sword_stone", "axe_flesh", "lance_wood",
                "stone_stone", "sword_armor", "arrow_wood", "spear_armor", "sword_flesh", "lance_flesh"]
    for index, name in enumerate(skirmish):
        add(name, index % combat_sound.VARIANTS, skirmish_start + index * 0.16, "mixed skirmish")
    samples = mix(*clips)
    gain = min(1.0, 0.90 / float(np.abs(samples).max()))
    samples = np.pad(samples * gain, (0, SAMPLE_RATE // 4))
    assert np.isfinite(samples).all() and 0 < np.abs(samples).max() <= 0.90
    write_wav(output / "comparison.wav", samples)
    report = {"sample_rate": SAMPLE_RATE, "seconds": len(samples) / SAMPLE_RATE,
              "peak": float(np.abs(samples).max()), "mix_gain": gain, "cues": cues}
    lines = ["Warband combat sound comparison", "Times refer to comparison.wav; takes are numbered 1–3.",
             "Weapon/material clips use the game's 65% impact gain, without playback pitch variation.", ""]
    lines += [f"{cue['start']:06.2f}–{cue['end']:06.2f}  {cue['section']}: "
              f"{cue['sound'].replace('_', ' / ')} · take {cue['take']}" for cue in cues]
    (output / "comparison.txt").write_text("\n".join(lines) + "\n")
    (output / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def battle_scene() -> tuple[GameScene, dict[int, int]]:
    """A small real fight with steel, arrows, siege, armor, bodies and buildings."""
    world = World(28, 22, [[Terrain.GRASS] * 28 for _ in range(22)], 2, rng=random.Random(7))
    for player in world.players:
        player.human = True
    world.place_building(0, BuildingType.TOWN_HALL, (2, 2))
    world.place_building(1, BuildingType.TOWN_HALL, (23, 17))
    tower = world.place_building(1, BuildingType.TOWER, (17, 13))
    farm = world.place_building(1, BuildingType.FARM, (17, 8))
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (12.5, 10.5))
    enemy = world.spawn_unit(1, UnitType.FOOTMAN, (13.3, 10.5))
    archer = world.spawn_unit(0, UnitType.ARCHER, (10.5, 9.5))
    catapult = world.spawn_unit(0, UnitType.CATAPULT, (12.5, 14.5))
    worker = world.spawn_unit(0, UnitType.PEASANT, (16.5, 9.5))
    knight = world.spawn_unit(0, UnitType.KNIGHT, (14.5, 7.5))
    peasant = world.spawn_unit(1, UnitType.PEASANT, (15.3, 7.5))
    for attacker, target in ((footman, enemy), (enemy, footman), (archer, enemy),
                             (catapult, tower), (worker, farm), (knight, peasant)):
        world.attack([attacker.id], target.id)
    world.update_vision()
    scene = GameScene(world, 7, settings={"tutorial": False, "edge_scroll": False, "music": 0.0})
    initial_hp = {entity.id: entity.hp for entity in [*world.units.values(), *world.buildings.values()]}
    return scene, initial_hp


def verify_native(output: Path) -> dict:
    """Exercise the sound bank and World→GameScene→bank route on real pyglet."""
    import pyglet

    game = Game("Warband audio verification", backend="pyglet", visible=False,
                resolution=(1280, 800), theme=build_theme(), save_dir=output / "saves")
    backend = game.backend
    previous_hooks = sound.sound_hook, sound.volume_hook, sound.music_hook
    records, ended = [], set()
    try:
        bank = sound.SoundBank(game, data_dir=output / "bank")
        driver = pyglet.media.get_audio_driver()
        assert "silent" in type(driver).__module__, "Native verification must use the silent audio driver"
        assert not backend.window.visible, "Native verification must keep the window hidden"

        def route(name: str) -> None:
            # Inspect native handles here because a recorded play call cannot prove EOS/cleanup.
            before = set(backend._players)
            bank.play(name)
            created = set(backend._players) - before
            assert len(created) == 1, f"{name}: expected one native player, got {created}"
            player_id = created.pop()
            player = backend._players[player_id]
            assert player.playing and backend.is_player_playing(player_id), f"{name}: player did not start"
            player.push_handlers(on_eos=lambda ident=player_id: ended.add(ident))
            records.append({"sound": name, "player_id": player_id, "pitch": player.pitch, "volume": player.volume})

        def drain() -> None:
            deadline = time.monotonic() + 2.0
            while backend._players and time.monotonic() < deadline:
                # dt=None also services pyglet's clock, which delivers silent-driver EOS.
                tick(game, dt=None)
            assert not backend._players, f"Native sound players did not finish: {list(backend._players)}"
            assert not backend._sound_players, "Finished sound handles were retained"
            assert {record["player_id"] for record in records} <= ended, "A natural EOS event was missing"

        for name in sorted(sound.IMPACTS):
            route(name)
        drain()

        sound.sound_hook, sound.volume_hook, sound.music_hook = route, bank.set_volume, None
        fonts.load(game)
        scene, initial_hp = battle_scene()
        game.push(scene)
        # Only render the units used here; warming every unused roster image is unrelated to audio.
        scene._warm = None
        scene.effects.clear()
        scene.camera.center_on(14 * 32, 10.5 * 32)
        scene.select([u.id for u in scene.world.player_units(0) if not u.is_worker])
        scene.recent_sounds.clear()
        deadline = time.monotonic() + 0.85
        while time.monotonic() < deadline:
            tick(game, dt=None)
        scene.paused = True
        heard = list(scene.recent_sounds)
        assert len(set(heard) & sound.IMPACTS) >= 3, f"Representative battle lacked impact variety: {heard}"
        damage = {ident: hp - (entity.hp if (entity := scene.world.entity(ident)) is not None else 0)
                  for ident, hp in initial_hp.items()}
        assert any(amount > 0 for amount in damage.values()), "Scene did not simulate combat"
        backend.capture_frame().save(output / "battle.png")
        drain()
        natural_count = len(records)
        route("stone_stone")  # Closing must also release an effect that is still playing.
        report = {"driver": type(driver).__module__, "impact_families": sorted(sound.IMPACTS),
                  "scene_sounds": heard, "damage": damage, "native_plays": records,
                  "natural_eos_count": natural_count, "natural_players_released": True}
    finally:
        sound.sound_hook, sound.volume_hook, sound.music_hook = previous_hooks
        game.close()
    assert not backend._players and not backend._sound_players and backend.window is None
    report["teardown_released_active_player"] = True
    (output / "native.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?", default=Path("/tmp/warband-audio"))
    parser.add_argument("--preview-only", action="store_true", help="write audio and its cue sheet without opening a native window")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = comparison(output)
    print(f"Wrote {output / 'comparison.wav'} ({report['seconds']:.1f}s); labels in comparison.txt and comparison.json")
    if not args.preview_only:
        native = verify_native(output)
        print(f"Verified {len(native['impact_families'])} native impact families, scene combat, EOS and teardown; {output / 'battle.png'}")


if __name__ == "__main__":
    main()
