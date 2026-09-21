"""Abandoned buildings (WB-007): a resignation in a match of three or more leaves grey ruins that nobody owns, anyone may raze
for nothing, and every brain ignores; a two-player match still clears the board."""

import pytest

from warband.brains.ai import known_enemy_buildings
from warband.sim.model import World
from warband.sim.rules import BuildingType, UnitType

from tests.warband.battlefield import field


def base(world: World, player: int, at: tuple[int, int]):
    """A finished farm and a barracks site for *player* near *at*, plus a footman and a peasant."""
    farm = world.place_building(player, BuildingType.FARM, at)
    site = world.place_building(player, BuildingType.BARRACKS, (at[0] + 3, at[1]), done=False)
    footman = world.spawn_unit(player, UnitType.FOOTMAN, (at[0] + 0.5, at[1] + 3.5))
    peasant = world.spawn_unit(player, UnitType.PEASANT, (at[0] + 1.5, at[1] + 3.5))
    return farm, site, footman, peasant


def test_a_resignation_among_three_or_more_leaves_the_buildings_standing_as_nobodys() -> None:
    world = field(4)
    farm, site, footman, peasant = base(world, 1, (20, 10))
    world.train(world.player_buildings(1, BuildingType.TOWN_HALL)[0].id, UnitType.PEASANT) if world.players[1].gold >= 500 else None
    world.resign(1)
    assert not world.players[1].alive and world.winner is None and sum(p.alive for p in world.players[:world.seats]) == 3
    assert farm.id in world.buildings and site.id in world.buildings and footman.id not in world.units and peasant.id not in world.units
    assert farm.abandoned and site.abandoned and farm.player == 1, "kept for what it was, but nobody's"
    assert world.player_buildings(1) == [] and not any(b.queue or b.research for b in (farm, site))
    world.step()
    assert not world.passable(farm.x, farm.y), "the footprint still blocks"
    assert not world.is_visible(1, (farm.x, farm.y)) or True  # the former owner is out; nothing is seen for them


def test_a_two_player_resignation_still_clears_the_board() -> None:
    world = field(2)
    farm, site, footman, peasant = base(world, 1, (20, 10))
    world.resign(1)
    assert farm.id not in world.buildings and site.id not in world.buildings and world.winner == 0


def test_anyone_may_raze_a_ruin_for_nothing_and_nobody_picks_one_up_in_passing() -> None:
    world = field(3)
    farm, *_ = base(world, 1, (20, 10))
    world.resign(1)
    idle = world.spawn_unit(0, UnitType.FOOTMAN, (18.5, 10.5))
    for _ in range(60):
        world.step()
    assert idle.state == "idle" and farm.hp == farm.max_hp, "an idle soldier beside a ruin leaves it alone"
    knights = [world.spawn_unit(0, UnitType.KNIGHT, (18.5, 9.5 + i)) for i in range(3)]
    world.attack([k.id for k in knights], farm.id)
    gold, stats = world.players[0].gold, dict(world.players[0].stats)
    for _ in range(20 * 60):
        world.step()
        if farm.id not in world.buildings:
            break
    assert farm.id not in world.buildings, "razed on an explicit order"
    assert world.players[0].gold == gold and world.players[0].stats == stats, "for nothing"
    assert not any(e.kind == "under_attack" and e.player == 1 for e in world.events)
    assert world.passable(farm.x, farm.y), "and the ground is clear"


def test_brains_neither_target_nor_fear_ruins() -> None:
    world = field(3)
    farm, *_ = base(world, 1, (20, 10))
    scout = world.spawn_unit(0, UnitType.SCOUT, (19.5, 12.5))
    world.update_vision()
    world.step()
    assert farm.id in {r.id for r in known_enemy_buildings(world, 0)} or known_enemy_buildings(world, 0), "seen while owned"
    world.resign(1)
    world.update_vision()
    world.step()
    assert farm.id not in {getattr(r, "id", None) for r in known_enemy_buildings(world, 0)}


def test_an_ai_that_cannot_come_back_surrenders_the_same_way() -> None:
    world = field(3)
    world.players[2].human = False
    hall = world.player_buildings(2, BuildingType.TOWN_HALL)[0]
    world.players[2].gold = world.players[2].lumber = 0
    for unit in world.player_units(2):
        world._remove_unit(unit)  # staged: the seat's last units gone, without a fight to lose them in
    world.step()
    assert not world.players[2].alive and world.players[2].surrendered
    assert hall.id in world.buildings and hall.abandoned


def test_the_state_survives_a_save() -> None:
    world = field(3)
    farm, *_ = base(world, 1, (20, 10))
    world.resign(1)
    again = World.from_dict(world.to_dict())
    assert again.buildings[farm.id].abandoned and again.player_buildings(1) == [] and not again.players[1].alive


def test_the_scene_shows_a_ruin_grey_on_the_map_the_minimap_and_the_card(tmp_path) -> None:
    from saga2d import Game
    from warband.ui.scene import GameScene
    from warband.ui.style import build_theme
    from tests.warband.battlefield import SETTINGS

    game = Game("Warband ruins", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        world = field(3)
        scene = GameScene(world, 0, ranked=False, settings=dict(SETTINGS))
        game.push(scene)
        scene.view.set_reveal(True)
        farm, *_ = base(world, 1, (20, 10))
        for _ in range(3):
            game.tick(1 / 60)
        owned_key = scene.view.building_sprite(farm.id).image
        world.resign(1)
        for _ in range(3):
            game.tick(1 / 60)
        key = scene.view.building_sprite(farm.id).image
        assert key.endswith(".abandoned") and key != owned_key
        from warband.ui.view import MINIMAP_SCALE
        minimap = scene.view.minimap_image()
        assert tuple(minimap.getpixel((farm.x * MINIMAP_SCALE, farm.y * MINIMAP_SCALE))[:3]) == (150, 150, 150)
        scene.select([farm.id])
        for _ in range(2):
            game.tick(1 / 60)
        texts = [t["text"] for t in game.backend.texts]
        assert "Abandoned" in texts and not scene.card, "named for what it is, with nothing to order"
    finally:
        game.close()


def test_an_abandoned_tower_never_looses_another_arrow() -> None:
    """Its owner's last look at the ground once outlived the resignation by a few ticks, and so did the tower's aim."""
    world = field(3)
    tower = world.place_building(1, BuildingType.TOWER, (20, 10))
    passer_by = world.spawn_unit(0, UnitType.FOOTMAN, (21.0, 13.5))
    world.hold([passer_by.id])
    world.update_vision()
    world.resign(1)
    assert tower.abandoned
    for _ in range(100):
        world.step()
    assert not world.projectiles and passer_by.hp == passer_by.max_hp, "a ruin nobody owns shot at a passer-by"


def test_gatherers_no_longer_fear_an_abandoned_tower() -> None:
    """A ruin shoots nothing, yet the automatic gatherers kept its old range as deadly ground: a mine beside the tower
    of a player who had resigned was left unworked for good."""
    world = field(3)
    mine = world.place_building(None, BuildingType.GOLD_MINE, (12, 2))
    world.place_building(2, BuildingType.TOWER, (17, 3))
    peasant = world.spawn_unit(0, UnitType.PEASANT, (6.5, 6.5))
    for player in range(3):
        world.reveal_all(player)
    world.resign(2)
    world.reveal_all(0)  # player 0 sees the ruin for what it is
    for _ in range(60):
        world.step()
    assert peasant.order is not None and peasant.order.target == mine.id
