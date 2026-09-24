"""Aether (WB-063): a third resource nobody carries.

Ley rifts are ground the map generator lays down; a finished vault standing square on one draws
aether straight into its owner's store, one every :data:`AETHER_EVERY` seconds, counted in whole
steps.  The store is capped at :data:`AETHER_STORE` for each finished vault, and a vault lost spills
what no longer fits at once.  :meth:`World.in_reach` is how far round a finished vault a spell is
cast at its plain price, which WB-066 builds on.
"""

from __future__ import annotations

import json

from warband.online.authority import WarbandMatch
from warband.sim.model import RIFT, RuleError, World
from warband.sim.rules import (AETHER_EVERY, AETHER_REACH, AETHER_STORE, AETHER_TICKS, SIM_DT, BuildingType, Terrain,
                               UnitType)

import pytest

RIFTS = ((10, 4), (18, 4), (10, 14))


def rift_world() -> World:
    """Open grass, a hall each, three ley rifts on seat 0's side, and every tile explored by both seats."""
    world = World(30, 22, [[Terrain.GRASS] * 30 for _ in range(22)], 2)
    world.place_building(0, BuildingType.TOWN_HALL, (2, 8))
    world.place_building(1, BuildingType.TOWN_HALL, (25, 17))
    world.lay_rifts(RIFTS)
    world.reveal_all(0)
    world.reveal_all(1)
    return world


def run(world: World, seconds: float) -> None:
    for _ in range(round(seconds / SIM_DT)):
        world.step()


def test_a_finished_vault_on_a_rift_draws_one_aether_every_interval() -> None:
    """Exactly one every AETHER_EVERY seconds from the step it stands: an integer store, so ten intervals are ten."""
    world = rift_world()
    site = world.place_building(0, BuildingType.VAULT, RIFTS[0], done=False)
    run(world, 3 * AETHER_EVERY)
    assert world.players[0].aether == 0, "a site draws nothing"
    world.buildings[site.id].progress = site.info.build_time  # staged: finished, as a builder would have left it
    assert world.taps(site)
    run(world, 10 * AETHER_EVERY)
    assert world.players[0].aether == 10
    assert world.aether_rate(0) == pytest.approx(1 / AETHER_EVERY)


def test_the_store_is_capped_per_finished_vault_and_banks_nothing_past_it() -> None:
    """Two vaults on rifts draw twice as fast into a store of twice the size; at the cap the draw stops dead, so the
    first step after a spend is not a burst of aether saved up meanwhile."""
    world = rift_world()
    world.place_building(0, BuildingType.VAULT, RIFTS[0])
    world.place_building(0, BuildingType.VAULT, RIFTS[1])
    assert world.aether_cap(0) == 2 * AETHER_STORE
    run(world, 5 * AETHER_EVERY)
    assert world.players[0].aether == 10
    run(world, AETHER_STORE * AETHER_EVERY)
    assert world.players[0].aether == 2 * AETHER_STORE and world.aether_rate(0) == 0.0
    run(world, 20 * AETHER_EVERY)
    world.players[0].aether -= 50  # staged: a spend, which WB-066's spells will make
    world.step()
    assert world.players[0].aether == 2 * AETHER_STORE - 50
    run(world, AETHER_EVERY / 2 - SIM_DT)  # two vaults: one aether each half interval
    assert world.players[0].aether == 2 * AETHER_STORE - 49


def test_a_vault_off_the_rifts_stores_and_reaches_but_draws_nothing() -> None:
    world = rift_world()
    vault = world.place_building(0, BuildingType.VAULT, (5, 16))
    assert world.can_place(BuildingType.VAULT, (14, 16), 0) is None, "a vault may stand anywhere"
    assert not world.taps(vault) and world.aether_cap(0) == AETHER_STORE
    run(world, 10 * AETHER_EVERY)
    assert world.players[0].aether == 0 and world.aether_rate(0) == 0.0
    assert world.in_reach(0, vault.center)


def test_a_vault_lost_spills_what_no_longer_fits_at_once() -> None:
    """Razed, the cap falls with it the same step and the excess is gone, which the owner is told of alone."""
    world = rift_world()
    kept = world.place_building(0, BuildingType.VAULT, RIFTS[0])
    lost = world.place_building(0, BuildingType.VAULT, RIFTS[1])
    world.players[0].aether = 150  # staged: a full two-vault store, as drawing it would take five minutes
    lost.hp = 0
    world.step()
    assert world.players[0].aether == AETHER_STORE
    spilled = [e for e in world.take_events() if e.kind == "spilled"]
    assert [(e.player, e.amount) for e in spilled] == [(0, 50)]
    kept.hp = 0
    world.step()
    assert world.players[0].aether == 0 and world.aether_cap(0) == 0


def test_a_site_cancelled_spills_nothing() -> None:
    world = rift_world()
    world.place_building(0, BuildingType.VAULT, RIFTS[0])
    site = world.place_building(0, BuildingType.VAULT, RIFTS[1], done=False)
    world.players[0].aether = AETHER_STORE
    world.cancel_building(site.id)
    assert world.players[0].aether == AETHER_STORE


def test_one_vault_to_a_rift_and_the_rift_kept_for_one() -> None:
    """A rift is kept for the vault standing square on it: another building on it, or a vault half on it, would deny it
    for good.  The planner's fast search (``placeable``) says the same as the order."""
    world = rift_world()
    x, y = RIFTS[0]
    assert world.can_place(BuildingType.FARM, (x - 1, y), 0) == "Keep the ley rift for a vault"
    assert world.can_place(BuildingType.VAULT, (x + 1, y + 1), 0) == "Set the vault square on the ley rift"
    assert world.can_place(BuildingType.VAULT, (x, y), 0) is None
    spots = [(x - 1, y), (x + 1, y + 1), (x, y), (x - 3, y)]
    assert list(world.placeable(BuildingType.VAULT, 0, spots)) == [(x, y), (x - 3, y)]
    assert list(world.placeable(BuildingType.FARM, 0, spots)) == [(x - 3, y)]
    world.place_building(1, BuildingType.VAULT, (x, y))
    assert world.can_place(BuildingType.VAULT, (x, y), 0) is not None, "one vault to a rift"
    peasant = world.spawn_unit(0, UnitType.PEASANT, (x - 2.5, y + 0.5))
    with pytest.raises(RuleError, match="ley rift"):
        world.build(peasant.id, BuildingType.FARM, RIFTS[1])
    with pytest.raises(RuleError, match="ley rift"):
        world.plan_building(0, BuildingType.TOWER, (RIFTS[2][0] + 1, RIFTS[2][1]))


def test_reach_is_ten_tiles_round_a_finished_vault_and_nobody_elses() -> None:
    world = rift_world()
    vault = world.place_building(0, BuildingType.VAULT, RIFTS[0])
    cx, cy = vault.center
    assert world.in_reach(0, (cx + AETHER_REACH, cy)) and world.in_reach(0, (cx + 6.0, cy + 8.0))
    assert not world.in_reach(0, (cx + AETHER_REACH + 0.01, cy)) and not world.in_reach(0, (cx + 7.1, cy + 7.1))
    assert not world.in_reach(1, (cx, cy)), "a rival's vault reaches nothing of seat 1's"
    world.place_building(0, BuildingType.VAULT, RIFTS[2], done=False)
    assert not world.in_reach(0, (RIFTS[2][0] + 1.0, RIFTS[2][1] + 12.0)), "a site reaches nothing yet"


def test_aether_and_the_rifts_survive_a_save_bit_for_bit() -> None:
    """The store, the charge toward the next aether and the rifts ride the save, and the loaded match goes on as the
    original does, step for step."""
    world = rift_world()
    world.place_building(0, BuildingType.VAULT, RIFTS[0])
    run(world, 7.5 * AETHER_EVERY)
    assert 0 < world.players[0].aether_charge < AETHER_TICKS
    copy = World.from_dict(json.loads(json.dumps(world.to_dict())))
    assert copy.rifts == world.rifts and copy.players[0].aether == world.players[0].aether == 7
    assert copy.players[0].aether_charge == world.players[0].aether_charge
    run(world, 3 * AETHER_EVERY)
    run(copy, 3 * AETHER_EVERY)
    assert copy.to_dict()["players"] == world.to_dict()["players"]


def test_a_save_from_before_the_rifts_loads_without_them() -> None:
    data = rift_world().to_dict()
    del data["rifts"]
    for player in data["players"]:
        del player["aether"], player["aether_charge"]
    world = World.from_dict(data)
    assert world.rifts == () and world.players[0].aether == 0
    assert world.can_place(BuildingType.FARM, RIFTS[0], 0) is None


def test_rifts_do_not_overlap() -> None:
    world = rift_world()
    with pytest.raises(ValueError, match="overlap"):
        world.lay_rifts([(4, 4), (4 + RIFT - 1, 4)])


def test_a_rivals_aether_is_private_and_the_rifts_are_public_ground() -> None:
    """Like gold: a seat's own store and charge travel to it, a rival's never, until the match is decided.  The rifts
    are the map's, as the ground it began with is, so every seat is sent them all."""
    match = WarbandMatch(seed=3)
    world = match.world
    assert world.rifts, "every generated map has its ley rifts"
    world.players[0].aether, world.players[0].aether_charge = 42, 7
    world.players[1].aether = 13
    mine, theirs = match.snapshot(0)["world"], match.snapshot(1)["world"]
    assert (mine["players"][0]["aether"], mine["players"][0]["aether_charge"], mine["players"][1]["aether"]) == (42, 7, 0)
    assert (theirs["players"][1]["aether"], theirs["players"][0]["aether"], theirs["players"][0]["aether_charge"]) == (13, 0, 0)
    assert mine["rifts"] == theirs["rifts"] == [list(rift) for rift in world.rifts]


def test_a_spill_is_news_for_its_owner_alone() -> None:
    match = WarbandMatch(seed=3)
    world = match.world
    hall = world.player_buildings(0, BuildingType.TOWN_HALL)[0]
    vault = world.place_building(0, BuildingType.VAULT, (hall.x, hall.y + 5))
    world.players[0].aether = 60
    vault.hp = 0
    match.step()
    assert any(fields["kind"] == "spilled" for _index, fields in match.snapshot(0)["events"])
    assert not any(fields["kind"] == "spilled" for _index, fields in match.snapshot(1)["events"])


def test_a_flyer_over_a_rift_is_in_nobody_s_way_and_a_walker_on_it_is() -> None:
    """A flying machine has no ground body (WB-064): hovering over a rift it leaves the vault's square free, where a
    footman standing on it holds it until it steps off."""
    world = rift_world()
    x, y = RIFTS[0]
    flyer = world.spawn_unit(0, UnitType.FLYING_MACHINE, (x + 1.0, y + 1.0))
    assert flyer.flying and world.can_place(BuildingType.VAULT, (x, y), 0) is None
    assert list(world.placeable(BuildingType.VAULT, 0, [(x, y)])) == [(x, y)]
    world.spawn_unit(0, UnitType.FOOTMAN, (x + 1.0, y + 1.0))
    assert world.can_place(BuildingType.VAULT, (x, y), 0) == "A unit is in the way"
