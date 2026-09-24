"""An order the rules refuse leaves no trace.

The online authority gives orders straight to the running world, and a group order that stopped halfway
(the first peasants sent to the mine, then a footman refused) would leave a match no player asked for.
So every order checks all it has to check before it changes anything, and says no with a RuleError:
never with an exception the server would take for a crash.
"""
import pytest

from warband.sim.model import RuleError, World
from warband.sim.rules import BuildingType, Terrain, UnitType, Upgrade


def scenario():
    """Open grass with a wood, two halls, a mine, a site, and a squad each: enough for every order to be refused on."""
    terrain = [[Terrain.GRASS] * 40 for _ in range(30)]
    for y in range(12, 16):
        terrain[y][20] = Terrain.TREES
    world = World(40, 30, terrain, 2)
    hall = world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    their_hall = world.place_building(1, BuildingType.TOWN_HALL, (34, 25))
    mine = world.place_building(None, BuildingType.GOLD_MINE, (10, 10))
    seam = world.place_building(None, BuildingType.GOLD_SEAM, (24, 10))
    smith = world.place_building(0, BuildingType.BLACKSMITH, (14, 1))
    site = world.place_building(0, BuildingType.FARM, (6, 6), done=False)
    their_site = world.place_building(1, BuildingType.BARRACKS, (30, 22), done=False)
    peasant = world.spawn_unit(0, UnitType.PEASANT, (5.5, 5.5))
    footman = world.spawn_unit(0, UnitType.FOOTMAN, (5.5, 4.5))
    raider = world.spawn_unit(1, UnitType.FOOTMAN, (30.5, 24.5))
    flyer = world.spawn_unit(0, UnitType.FLYING_MACHINE, (7.5, 4.5))
    their_flyer = world.spawn_unit(1, UnitType.FLYING_MACHINE, (28.5, 24.5))
    world.lay_rifts([(6, 20)])
    world.reveal_all(0)
    world.reveal_all(1)
    return world, {"hall": hall.id, "their_hall": their_hall.id, "mine": mine.id, "seam": seam.id, "site": site.id, "smith": smith.id,
                   "their_site": their_site.id,
                   "peasant": peasant.id, "footman": footman.id, "raider": raider.id, "flyer": flyer.id, "their_flyer": their_flyer.id}


REFUSED = {
    "attack on your own": lambda w, e: w.attack([e["peasant"], e["footman"]], e["hall"]),
    "attack with a unit the target belongs to": lambda w, e: w.attack([e["footman"], e["raider"]], e["their_hall"]),
    "attack on a mine": lambda w, e: w.attack([e["footman"]], e["mine"]),
    "attack on a gold seam": lambda w, e: w.attack([e["footman"]], e["seam"]),
    "attack on nothing": lambda w, e: w.attack([e["footman"]], 9999),
    # Melee and stones pass beneath a flyer, and a flying machine carries no weapon: nobody in either group can strike.
    "attack on a flyer by melee": lambda w, e: w.attack([e["peasant"], e["footman"]], e["their_flyer"]),
    "attack by a flying machine": lambda w, e: w.attack([e["flyer"]], e["raider"]),
    "a context order sending melee at a flyer": lambda w, e: w.smart([e["footman"]], (28.5, 24.5), target_id=e["their_flyer"]),
    "harvest with a soldier among the peasants": lambda w, e: w.harvest([e["peasant"], e["footman"]], e["mine"]),
    "harvest where no trees stand": lambda w, e: w.harvest([e["peasant"]], (3, 20)),
    "peasants released with a soldier among them": lambda w, e: w.release_workers([e["peasant"], e["footman"]]),
    "repair of an undamaged hall": lambda w, e: w.repair([e["peasant"]], e["hall"]),
    "repair by soldiers": lambda w, e: w.repair([e["footman"]], e["hall"]),
    "salvage of your own hall": lambda w, e: w.salvage([e["peasant"]], e["hall"]),
    "salvage by soldiers": lambda w, e: w.salvage([e["footman"]], e["their_hall"]),
    "salvage of a gold mine": lambda w, e: w.salvage([e["peasant"]], e["mine"]),
    "salvage of a gold seam": lambda w, e: w.salvage([e["peasant"]], e["seam"]),
    "repair of a gold seam": lambda w, e: w.repair([e["peasant"]], e["seam"]),
    "salvage of your own site": lambda w, e: w.salvage([e["peasant"]], e["site"]),
    "salvage of a rival's site": lambda w, e: w.salvage([e["peasant"]], e["their_site"]),
    "salvage of nothing": lambda w, e: w.salvage([e["peasant"]], 9999),
    "a building on the wood": lambda w, e: w.build(e["peasant"], BuildingType.FARM, (20, 12)),
    "a neutral lair cannot be built": lambda w, e: w.build(e["peasant"], BuildingType.LAIR, (14, 20)),
    "a building by a soldier": lambda w, e: w.build(e["footman"], BuildingType.FARM, (14, 20)),
    "a knight from the hall": lambda w, e: w.train(e["hall"], UnitType.KNIGHT),
    "research at the hall": lambda w, e: w.research(e["hall"], Upgrade.BLADES_1),
    "a queue slot that is not there": lambda w, e: w.cancel_train(e["hall"], 3),
    "a queue slot before the first": lambda w, e: w.cancel_train(e["hall"], -3),
    "research that is not running": lambda w, e: w.cancel_research(e["hall"]),
    # A tier behind more than one thing: the refusal names every one of them, and pays for none.
    "a master weapon without its tier or the keep": lambda w, e: w.research(e["smith"], Upgrade.BLADES_3),
    "the keep away from the hall": lambda w, e: w.research(e["smith"], Upgrade.KEEP),
    "a finished hall cancelled": lambda w, e: w.cancel_building(e["hall"]),
    "a plan off the map": lambda w, e: w.plan_building(0, BuildingType.FARM, (39, 29)),
    "a neutral lair cannot be planned": lambda w, e: w.plan_building(0, BuildingType.LAIR, (14, 20)),
    "an art of another race": lambda w, e: w.order_upgrade(0, Upgrade.BLOODLUST),
    "a plan that is not there": lambda w, e: w.cancel_plan(0, 77),
    "a rally point for nothing": lambda w, e: w.set_rally(9999, (3.0, 3.0)),
    "endless knights from the hall": lambda w, e: w.set_auto_train(e["hall"], UnitType.KNIGHT, True),
    "endless training at a building that is not there": lambda w, e: w.set_auto_train(9999, UnitType.PEASANT, True),
    "endless training at a gold mine": lambda w, e: w.set_auto_train(e["mine"], UnitType.PEASANT, True),
    "a building by a soldier that may wait for the money": lambda w, e: w.build(e["footman"], BuildingType.FARM, (14, 20), plan_if_short=True),
    "a building on the wood that may wait for the money": lambda w, e: w.build(e["peasant"], BuildingType.FARM, (20, 12), plan_if_short=True),
    "a farm on a ley rift": lambda w, e: w.build(e["peasant"], BuildingType.FARM, (6, 20)),
    "a vault half on a ley rift": lambda w, e: w.plan_building(0, BuildingType.VAULT, (7, 21)),
    "a context order on a target that is gone": lambda w, e: w.smart([e["peasant"], e["footman"]], (3.0, 3.0), target_id=9999),
}


@pytest.mark.parametrize("name", REFUSED)
def test_a_refused_order_leaves_the_world_as_it_was(name) -> None:
    world, entities = scenario()
    world.train(entities["hall"], UnitType.PEASANT)  # one in the queue, so a bad slot is a bad slot and not an empty queue
    world.harvest([entities["peasant"]], entities["mine"])  # a job, so an order that let go of it would show
    before = world.to_dict()
    with pytest.raises(RuleError):
        REFUSED[name](world, entities)
    assert world.to_dict() == before, f"{name}: refused, yet the world changed"


def test_resigning_twice_or_after_the_end_is_refused_and_changes_nothing() -> None:
    """Online, resigning is an order (WB-012): refused as any other, never half done."""
    terrain = [[Terrain.GRASS] * 40 for _ in range(30)]
    world = World(40, 30, terrain, 3)
    for player, pos in enumerate(((1, 1), (34, 25), (34, 1))):
        world.place_building(player, BuildingType.TOWN_HALL, pos)
        world.spawn_unit(player, UnitType.PEASANT, (pos[0] + 4.5, pos[1] + 4.5))
    world.resign(2)
    assert not world.players[2].alive and world.winner is None
    before = world.to_dict()
    with pytest.raises(RuleError, match="already out"):
        world.resign(2)
    assert world.to_dict() == before
    world.resign(1)
    assert world.winner == 0
    before = world.to_dict()
    with pytest.raises(RuleError, match="over"):
        world.resign(0)
    assert world.to_dict() == before
