"""A match freezes its long-lived objects out of the garbage collector once its warm-up is over."""

import gc

from warband import mapgen
from warband.scene import GameScene


def test_a_match_freezes_its_world_and_sprites_once_warmed_up(game, tmp_path):
    """Full collections walk every tracked object: in a 150-unit battle they took 26 ms every two seconds
    and grew with the match (tools/perf.py).  The world, sprites and images built for the match are
    long-lived, so they are frozen out of the scans once the unit images are warm."""
    gc.unfreeze()  # whatever an earlier test left frozen
    scene = GameScene(mapgen.generate(seed=3, players=2), 3)
    game.push(scene)
    for _ in range(400):
        game.tick(1 / 60)
        if gc.get_freeze_count():
            break
    assert gc.get_freeze_count() > 0, "the warm-up ended without freezing the match"
    assert scene.world.time > 0  # the match runs on regardless


def test_the_next_match_thaws_the_previous_one(game):
    """A frozen object is never collected; each match's freeze first thaws and buries what the last one froze."""
    gc.unfreeze()
    first = GameScene(mapgen.generate(seed=3, players=2), 3)
    game.push(first)
    for _ in range(400):
        game.tick(1 / 60)
        if gc.get_freeze_count():
            break
    frozen_by_first = gc.get_freeze_count()
    assert frozen_by_first > 0
    game.pop()
    del first
    game.push(GameScene(mapgen.generate(seed=4, players=2), 4))
    for _ in range(400):
        game.tick(1 / 60)
        if gc.get_freeze_count() != frozen_by_first:
            break
    assert 0 < gc.get_freeze_count() != frozen_by_first, "the second match froze on top of the first"
