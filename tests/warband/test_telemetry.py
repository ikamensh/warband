"""What a match records about itself, so a balance readout is data rather than impressions.

Properties: a tally is complete (every player, every kind of purchase), and
attribution is exact (whoever landed the last blow gets the kill, priced at
what the victim cost).  They should survive any rewrite of how the arena
schedules matches or how the model reports events.
"""

from __future__ import annotations

from warband.league.arena import MatchSpec, play
from warband.sim.rules import Race


def test_a_played_match_comes_back_with_a_tally_per_player():
    """Every purchase a player made is in its tally, keyed by what was bought."""
    outcome = play(MatchSpec(seed=7, agents=("pro", "pro"), minutes=1.5))
    assert len(outcome.tallies) == 2
    for tally in outcome.tallies:
        assert Race(tally.race)
        assert tally.trained["peasant"] >= 1, "a minute and a half is enough to hire one peasant"
        assert tally.started["farm"] >= 1, "…and to lay one farm"
        assert tally.spent["peasant"] == 400 * tally.trained["peasant"]
        assert 0 < tally.first["farm"] <= 90, "when the first farm was finished, in sim seconds"


def test_the_last_blow_gets_the_kill_priced_at_what_the_victim_cost():
    """A footman that puts down a peasant is credited a 400-gold kill; the peasant's owner records the loss."""
    from warband.sim import mapgen
    from warband.sim.model import tile_center
    from warband.sim.rules import BuildingType, UnitType
    from warband.league.telemetry import Telemetry

    world = mapgen.generate(seed=3, players=2, human=None)
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    x, y = hall.pos
    footman = world.spawn_unit(0, UnitType.FOOTMAN, tile_center((x + 5, y + 5)))
    peasant = world.spawn_unit(1, UnitType.PEASANT, tile_center((x + 6, y + 5)))
    world.reveal_all(0)
    world.attack([footman.id], peasant.id)
    telemetry = Telemetry(world)
    for _ in range(20 * 60):
        world.step()
        telemetry.observe(world, world.take_events())
        if peasant.id not in world.units:
            break
    assert peasant.id not in world.units, "a footman kills an unarmed peasant inside a minute"
    mine, theirs = telemetry.tallies
    assert theirs.lost["peasant"] == 1
    assert mine.killed["peasant"] == 1
    assert mine.kill_value["footman"] == 400
    assert mine.dealt["footman"] == theirs.taken["peasant"] >= 30, "a peasant has 30 hit points"
    assert mine.lost == theirs.killed == {}


def test_a_frame_razed_the_step_it_starts_or_stands_is_still_counted():
    """Regression (WB-044's ladder): a frame wears no armour, so it can fall in the step its construction
    starts or it stands, and the tally is read from events after the building has been buried."""
    from warband.sim import mapgen
    from warband.sim.model import tile_center
    from warband.sim.rules import BUILDINGS, BuildingType, UnitType
    from warband.league.telemetry import Telemetry

    world = mapgen.generate(seed=3, players=2, human=None)
    world.players[0].gold = world.players[0].lumber = 5000
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    x, y = hall.pos
    builder = world.spawn_unit(0, UnitType.PEASANT, tile_center((x + 5, y + 5)))
    world.reveal_all(0)
    world.build(builder.id, BuildingType.FARM, (x + 6, y + 7))  # clear of the ley rift kept for a vault at (x + 6, y + 4)
    telemetry, events, frame = Telemetry(world), [], None
    while not any(e.kind == "built" for e in events):
        world.step()
        events += world.take_events()
        frame = frame or next((b for b in world.player_buildings(0, BuildingType.FARM)), None)
        assert world.time < 60.0
    frame.hp = 0
    world.step()
    assert frame.id not in world.buildings
    telemetry.observe(world, events + world.take_events())
    mine = telemetry.tallies[0]
    assert mine.started["farm"] == mine.completed["farm"] == 1
    assert mine.spent["farm"] == BUILDINGS[BuildingType.FARM].cost.gold + BUILDINGS[BuildingType.FARM].cost.lumber
