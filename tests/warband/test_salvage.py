"""Salvage: a peasant tears a building apart and carries the materials home.

Repair run backwards.  A ruin nobody holds comes apart at the rate one is mended at and the automatic worker
policy picks one up by itself; a building someone still holds resists, comes apart at a quarter of that, and
raises its owner's alarm exactly as a blow does.  What comes back is a quarter of the price, drawn as gold or
lumber from the world's own random stream so a replay reproduces it to the coin.
"""

import json
import random

import pytest

from warband.records.replay import Playback, Replay, digest
from warband.sim.model import RuleError, Salvage, World
from warband.sim.rules import (
    SALVAGE_CHUNK, SALVAGE_HELD_RATE, SALVAGE_RATE, SALVAGE_SHARE, SIM_DT, BUILDINGS, BuildingType, Difficulty, Resource,
    Terrain, UnitType, salvage_resource, salvage_yield,
)

from tests.warband.battlefield import field


def ruined(world: World, owner: int = 1, at: tuple[int, int] = (20, 10), kind: BuildingType = BuildingType.FARM):
    """*owner*'s building at *at*, left as a ruin by their resignation (which needs three seats to leave one)."""
    building = world.place_building(owner, kind, at)
    world.resign(owner)
    assert building.abandoned
    return building


def salvager(world: World, at: tuple[float, float] = (18.5, 10.5), player: int = 0):
    peasant = world.spawn_unit(player, UnitType.PEASANT, at)
    world.reveal_all(player)
    world.players[player].gold = world.players[player].lumber = 0
    return peasant


def purse(world: World, player: int = 0) -> int:
    return world.players[player].gold + world.players[player].lumber


def run(world: World, seconds: float, until=None) -> None:
    for _ in range(int(seconds / SIM_DT)):
        world.step()
        world.take_events()
        if until is not None and until():
            return


# -- What it is worth ---------------------------------------------------------------------------------------------


def test_a_full_salvage_returns_the_share_of_the_price_and_no_more() -> None:
    world = field(3)
    farm = ruined(world)
    peasant = salvager(world)
    world.salvage([peasant.id], farm.id)
    run(world, 120.0, until=lambda: farm.id not in world.buildings)
    price = BUILDINGS[BuildingType.FARM].cost
    assert farm.id not in world.buildings, "the farm came apart"
    assert purse(world) == int((price.gold + price.lumber) * SALVAGE_SHARE) == 187
    assert world.players[0].gold and world.players[0].lumber, "a farm of gold and lumber gives up both"


def test_the_payout_does_not_drift_with_how_many_chunks_it_is_torn_out_in() -> None:
    """The running-total trick repair_cost uses: a whole salvage is worth the same as its pieces added up."""
    info = BUILDINGS[BuildingType.TOWN_HALL]
    whole = salvage_yield(info, info.hp, 0, info.hp)
    pieces = sum(salvage_yield(info, info.hp - SALVAGE_CHUNK * i, info.hp - SALVAGE_CHUNK * (i + 1), info.hp)
                 for i in range(info.hp // SALVAGE_CHUNK))
    assert whole == pieces == int((info.cost.gold + info.cost.lumber) * SALVAGE_SHARE)


def test_a_building_already_beaten_down_holds_almost_nothing() -> None:
    """Value somebody else's blows broke is value nobody gets back: the prize is a ruin still standing whole."""
    world = field(3)
    farm = ruined(world)
    farm.hp = 40  # staged: a tenth of its hit points left, as a siege would have left it
    peasant = salvager(world)
    world.salvage([peasant.id], farm.id)
    run(world, 60.0, until=lambda: farm.id not in world.buildings)
    assert farm.id not in world.buildings
    # 187 for the whole farm, less the 168 the first 360 hit points were worth: nineteen for the tenth left.
    assert purse(world) == 19


def test_the_draw_is_weighted_by_what_the_building_is_made_of() -> None:
    farm = BUILDINGS[BuildingType.FARM]  # 500 gold, 250 lumber: gold two draws in three
    assert [salvage_resource(farm, roll) for roll in (0.0, 0.66, 0.67, 0.99)] == \
           [Resource.GOLD, Resource.GOLD, Resource.LUMBER, Resource.LUMBER]
    tower = BUILDINGS[BuildingType.TOWER]  # 700 gold, 250 lumber
    assert sum(salvage_resource(tower, i / 1000) is Resource.GOLD for i in range(1000)) == 737


def test_the_same_seed_pays_out_the_same_way() -> None:
    """The draw comes from World.rng, the stream a save keeps and a replay restores: two worlds built the same
    way split the payout between gold and lumber identically, and a third with another seed need not."""
    def played(seed: int) -> tuple[int, int]:
        world = field(3)
        world.rng = random.Random(seed)
        farm = ruined(world)
        peasant = salvager(world)
        world.salvage([peasant.id], farm.id)
        run(world, 120.0, until=lambda: farm.id not in world.buildings)
        return world.players[0].gold, world.players[0].lumber

    assert played(5) == played(5)
    assert played(5) != played(9), "and it really is drawn, not fixed"


def test_the_payout_survives_a_save_in_the_middle() -> None:
    world = field(3)
    farm = ruined(world)
    peasant = salvager(world)
    world.salvage([peasant.id], farm.id)
    run(world, 20.0)
    assert isinstance(peasant.order, Salvage) and 0 < farm.hp < farm.max_hp
    again = World.from_dict(world.to_dict())
    assert isinstance(again.units[peasant.id].order, Salvage)
    for w in (world, again):
        run(w, 120.0, until=lambda w=w: farm.id not in w.buildings)
    assert (world.players[0].gold, world.players[0].lumber) == (again.players[0].gold, again.players[0].lumber)


# -- A building someone still holds -------------------------------------------------------------------------------


def test_a_held_building_comes_apart_slowly_and_raises_its_owners_alarm() -> None:
    """A building dissolving in silence would be the worst kind of surprise, so its owner hears the same
    "under attack" they hear for a blow; and it resists, so a peasant crew is never a siege train."""
    world = field(2)
    farm = world.place_building(1, BuildingType.FARM, (20, 10))
    peasant = salvager(world)
    world.salvage([peasant.id], farm.id)
    run(world, 30.0)
    torn = farm.max_hp - farm.hp
    assert 0 < torn <= SALVAGE_HELD_RATE * 30.0, "no faster than a held building gives way"
    assert torn < SALVAGE_RATE * 30.0 / 3, "and far slower than a ruin"
    assert world.players[1].last_hit > 0 and world.players[1].last_alert > 0
    assert purse(world) == salvage_yield(farm.info, farm.max_hp, farm.hp, farm.max_hp)


def test_a_ruin_comes_apart_faster_than_a_building_someone_holds() -> None:
    def torn(owner_resigns: bool) -> int:
        world = field(3)
        farm = ruined(world) if owner_resigns else world.place_building(1, BuildingType.FARM, (20, 10))
        peasant = salvager(world)
        world.salvage([peasant.id], farm.id)
        run(world, 30.0)
        return farm.max_hp - farm.hp

    assert torn(True) >= 3 * torn(False)


def test_nobody_is_alarmed_by_a_ruin_coming_apart() -> None:
    world = field(3)
    farm = ruined(world)
    peasant = salvager(world)
    world.salvage([peasant.id], farm.id)
    run(world, 40.0)
    assert not any(event.kind == "under_attack" for event in world.events)
    assert world.players[1].last_alert < 0, "its former owner is out of the match and hears nothing"


def test_salvaging_a_held_building_down_razes_it_and_counts_as_razing_it() -> None:
    world = field(2)
    farm = world.place_building(1, BuildingType.FARM, (20, 10))
    farm.hp = 20  # staged: two chunks left, so a peasant can finish it inside a test
    peasant = salvager(world)
    world.salvage([peasant.id], farm.id)
    run(world, 40.0, until=lambda: farm.id not in world.buildings)
    assert farm.id not in world.buildings
    assert world.players[0].stats["buildings_razed"] == 1
    assert world.players[0].stats["destroyed_value"] == farm.info.cost.gold + farm.info.cost.lumber
    assert world.players[1].stats["buildings_lost"] == 1
    assert peasant.order is None and peasant.state == "idle", "and the peasant is free again"


def test_razing_a_ruin_by_salvage_counts_for_nothing_but_the_materials() -> None:
    world = field(3)
    farm = ruined(world)
    peasant = salvager(world)
    world.salvage([peasant.id], farm.id)
    run(world, 120.0, until=lambda: farm.id not in world.buildings)
    assert world.players[0].stats["buildings_razed"] == 0 and world.players[0].stats["destroyed_value"] == 0
    assert purse(world) == 187


# -- What it refuses ----------------------------------------------------------------------------------------------


def test_your_own_buildings_are_not_yours_to_salvage() -> None:
    """Deliberately: a right-click on your own building already means Repair, and a mis-click that dissolved a
    hall would be unforgivable.  Nothing about the mechanic needs it — a refund loop least of all."""
    world = field(2)
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    peasant = salvager(world, (5.5, 5.5))
    with pytest.raises(RuleError, match="ruins and rival buildings"):
        world.salvage([peasant.id], hall.id)


def test_a_site_and_a_gold_mine_are_refused() -> None:
    world = field(2)
    site = world.place_building(1, BuildingType.BARRACKS, (20, 10), done=False)
    mine = world.place_building(None, BuildingType.GOLD_MINE, (10, 10))
    peasant = salvager(world)
    with pytest.raises(RuleError, match="nothing in a site"):
        world.salvage([peasant.id], site.id)
    with pytest.raises(RuleError, match="gold mine"):
        world.salvage([peasant.id], mine.id)


def test_only_peasants_salvage() -> None:
    world = field(2)
    farm = world.place_building(1, BuildingType.FARM, (20, 10))
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (18.5, 10.5))
    with pytest.raises(RuleError, match="Only peasants"):
        world.salvage([footman.id], farm.id)
    with pytest.raises(RuleError, match="No such building"):
        world.salvage([salvager(world).id], 9999)


def test_a_worker_whose_target_vanishes_goes_back_to_being_idle() -> None:
    world = field(3)
    farm = ruined(world)
    peasant = salvager(world)
    world.salvage([peasant.id], farm.id)
    run(world, 5.0)
    world._remove_building(farm, reason="destroyed")  # staged: somebody else razed it while the peasant walked
    run(world, 2.0)
    assert peasant.order is None


# -- Through a right-click ----------------------------------------------------------------------------------------


def test_a_right_click_on_a_ruin_sets_the_peasants_salvaging_and_the_soldiers_razing() -> None:
    world = field(3)
    farm = ruined(world)
    peasant = salvager(world)
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (17.5, 10.5))
    assert world.smart([peasant.id, footman.id], farm.center) == "salvage"
    assert isinstance(peasant.order, Salvage)
    assert type(footman.order).__name__ == "Attack", "a soldier has no crowbar; it razes the ruin as before"


def test_a_right_click_on_a_ruin_with_an_unarmed_flyer_along_sends_it_to_look() -> None:
    """The flying machine has no weapon to raze with: it goes along, and the peasant's salvage is not left half given
    by a refusal (the attack it was once handed said no after the peasant had set out)."""
    world = field(3)
    farm = ruined(world)
    peasant = salvager(world)
    flyer = world.spawn_unit(0, UnitType.FLYING_MACHINE, (17.5, 10.5))
    assert world.smart([peasant.id, flyer.id], farm.center) == "salvage"
    assert isinstance(peasant.order, Salvage) and type(flyer.order).__name__ == "Move"


def test_a_right_click_on_a_rivals_standing_building_still_means_attack() -> None:
    """Salvaging one is slow and dangerous: it is an armed choice, never what a click meant to be an attack does."""
    world = field(2)
    farm = world.place_building(1, BuildingType.FARM, (20, 10))
    peasant = salvager(world)
    assert world.smart([peasant.id], farm.center) == "attack"


# -- The automatic worker policy ----------------------------------------------------------------------------------


def crew(world: World, count: int, at: tuple[float, float] = (4.5, 6.5)) -> list:
    return [world.spawn_unit(0, UnitType.PEASANT, (at[0] + i, at[1])) for i in range(count)]


def test_a_spare_hand_takes_a_nearby_ruin_apart_without_being_told() -> None:
    world = field(3)
    farm = ruined(world, at=(8, 4))
    peasants = crew(world, 6)
    world.reveal_all(0)
    run(world, 30.0)
    salvaging = [p for p in peasants if isinstance(p.order, Salvage)]
    assert len(salvaging) == 1, "one hand and no more: the mine and the trees keep their crews"
    assert farm.hp < farm.max_hp and purse(world) > 0


def test_a_parked_worker_is_left_alone() -> None:
    """Stop and Hold put a peasant off automatic work; a ruin next door does not call it back."""
    world = field(3)
    ruined(world, at=(8, 4))
    peasants = crew(world, 6)
    world.reveal_all(0)
    world.stop([peasants[0].id, peasants[1].id, peasants[2].id])
    world.hold([peasants[3].id, peasants[4].id, peasants[5].id])
    assert not any(p.auto_work for p in peasants)
    run(world, 30.0)
    assert not any(isinstance(p.order, Salvage) for p in peasants)


def test_a_small_crew_keeps_every_hand_on_the_resources() -> None:
    world = field(3)
    ruined(world, at=(8, 4))
    peasants = crew(world, 3)
    world.reveal_all(0)
    run(world, 30.0)
    assert not any(isinstance(p.order, Salvage) for p in peasants)


def test_a_ruin_in_the_fog_is_still_remembered_as_one() -> None:
    """The policy chooses from what the player remembers, as it chooses a mine: a ruin seen once and since lost to
    the fog is still a ruin, and KnownBuilding.ruin is what carries that."""
    world = field(3)
    farm = ruined(world, at=(12, 8))  # out of the hall's own sight, and nobody else's
    peasants = crew(world, 6, at=(25.5, 25.5))  # far away: the ruin is only ever seen by the one reveal below
    world.reveal_all(0)
    world.update_vision()
    assert not world.is_visible(0, (12, 8)), "and out of sight again at once"
    assert world.worker_knowledge[0].buildings[farm.id].ruin
    run(world, 30.0)
    assert sum(isinstance(p.order, Salvage) for p in peasants) == 1


def test_a_ruin_across_the_map_is_not_the_policys_to_fetch() -> None:
    world = field(3)
    far = ruined(world, at=(33, 20))  # the far corner, well past SALVAGE_REACH from player 0's hall
    peasants = crew(world, 8)
    world.reveal_all(0)
    run(world, 30.0)
    assert not any(isinstance(p.order, Salvage) for p in peasants)
    assert far.hp == far.max_hp


def test_the_hand_comes_back_to_the_resources_once_the_ruin_is_gone() -> None:
    world = field(3)
    farm = ruined(world, at=(8, 4))
    farm.hp = 20  # staged: nearly picked apart already, so the test does not play a whole minute
    peasants = crew(world, 6)
    world.reveal_all(0)
    run(world, 30.0, until=lambda: farm.id not in world.buildings)
    assert farm.id not in world.buildings
    run(world, 3.0)
    assert not any(isinstance(p.order, Salvage) for p in peasants)


# -- Replay -------------------------------------------------------------------------------------------------------


def test_a_salvage_replays_to_the_bit() -> None:
    """The payout is drawn from the world's random stream, so a replay that fell out of step with it would end
    with a different purse: this is what holds the draw to World.rng."""
    world = World(40, 30, [[Terrain.GRASS] * 40 for _ in range(30)], 3, rng=random.Random(4))
    for player, at in enumerate(((1, 1), (20, 10), (34, 25))):
        world.place_building(player, BuildingType.TOWN_HALL, at)
        world.spawn_unit(player, UnitType.PEASANT, (at[0] + 0.5, at[1] + 4.5))
    farm = world.place_building(1, BuildingType.FARM, (16, 10))
    world.reveal_all(0)
    replay = Replay.begin(world, seed=4, difficulty=Difficulty.EASY, human=0)
    world.resign(1)
    peasant = world.player_units(0)[0]
    world.salvage([peasant.id], farm.id)
    run(world, 60.0)
    assert purse(world) > world.players[0].gold - 1000, "the salvage paid into the purse"
    assert "salvage" in [row[1] for row in replay.orders]
    replay.finish(world, "victory")
    playback = Playback(Replay.from_dict(json.loads(json.dumps(replay.to_dict()))))
    playback.run()
    assert playback.faithful and digest(playback.world) == digest(world)
