"""Healer choices remain useful, observable and faithful to player commands."""

import math

import pytest

from warband.model import Heal, World
from warband.rules import BuildingType, SIM_DT, Terrain, UnitType


def arena(terrain=None):
    world = World(24, 18, terrain or [[Terrain.GRASS] * 24 for _ in range(18)], 2)
    world.place_building(0, BuildingType.TOWN_HALL, (1, 1))
    world.place_building(1, BuildingType.TOWN_HALL, (19, 13))
    return world


def advance(world, seconds):
    for _ in range(round(seconds / SIM_DT)):
        world.step()
        for unit in world.units.values():
            assert 0 <= unit.x < world.width and 0 <= unit.y < world.height
            assert unit.hidden or world.passable(*unit.tile)


def loaded_heal(world, healer, patient, *, automatic):
    """Use the public save format because there is no direct friendly Heal command."""
    saved = world.to_dict()
    actor = next(unit for unit in saved["units"] if unit["id"] == healer.id)
    actor["orders"] = [{"kind": "Heal", "target": patient.id, "auto": automatic}]
    return World.from_dict(saved)


def test_healer_treats_an_ally_under_visible_fire_before_a_nearer_safe_ally():
    """Equal injuries need different priority when only one patient faces visible enemy fire."""
    world = arena()
    healer = world.spawn_unit(0, UnitType.CLERIC, (6.5, 6.5))
    safe = world.spawn_unit(0, UnitType.FOOTMAN, (7.5, 6.5))
    threatened = world.spawn_unit(0, UnitType.FOOTMAN, (9.5, 6.5))
    enemy = world.spawn_unit(1, UnitType.ARCHER, (13.5, 6.5))
    safe.hp = threatened.hp = 20
    world.hold([safe.id, threatened.id, enemy.id])
    world.update_vision()
    assert world.is_visible(0, enemy.tile)
    advance(world, .25)
    injured_hp = threatened.hp
    advance(world, .5)
    assert isinstance(healer.order, Heal) and healer.order.target == threatened.id
    assert threatened.hp > injured_hp
    assert safe.hp == 20


def test_an_urgent_distant_patient_does_not_mask_useful_reachable_treatment():
    """A better nearby patient can receive healing while an even more urgent patient is out of reach."""
    world = arena()
    healer = world.spawn_unit(0, UnitType.CLERIC, (6.5, 7.5))
    current = world.spawn_unit(0, UnitType.FOOTMAN, (7.4, 7.5))
    nearby = world.spawn_unit(0, UnitType.KNIGHT, (7.5, 8.4))
    distant = world.spawn_unit(0, UnitType.KNIGHT, (10.7, 7.5))
    enemy = world.spawn_unit(1, UnitType.ARCHER, (14.5, 7.5))
    current.hp, nearby.hp, distant.hp = 55, 10, 1
    enemy.cooldown = enemy.info.cooldown  # Its next shot has not recovered yet.
    world.hold([current.id, nearby.id, distant.id, enemy.id])
    world.update_vision()
    world = loaded_heal(world, healer, current, automatic=True)
    advance(world, .75)
    assert world.units[distant.id].hp == 1  # The urgent alternative was present throughout.
    assert world.units[nearby.id].hp > 10
    assert isinstance(world.units[healer.id].order, Heal)
    assert world.units[healer.id].order.target == nearby.id


def test_explicit_healing_survives_loading_even_when_a_better_patient_is_nearby():
    """A manual patient's treatment takes priority over automatic triage after a saved game loads."""
    world = arena()
    healer = world.spawn_unit(0, UnitType.CLERIC, (6.5, 6.5))
    chosen = world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 6.5))
    alternative = world.spawn_unit(0, UnitType.KNIGHT, (7.5, 6.5))
    chosen.hp = alternative.hp = 10
    world.hold([chosen.id, alternative.id])
    world.update_vision()
    world = loaded_heal(world, healer, chosen, automatic=False)
    advance(world, 2)
    actor = world.units[healer.id]
    assert isinstance(actor.order, Heal) and not actor.order.auto and actor.order.target == chosen.id
    assert world.units[chosen.id].hp > 10
    assert world.units[alternative.id].hp == 10


@pytest.mark.parametrize("command", ["attack_move", "patrol"])
@pytest.mark.parametrize("player", [0, 1])
def test_acquired_healing_keeps_its_intent_and_underlying_journey_after_loading(command, player):
    """Moving healers still triage after loading, then finish their interrupted route."""
    world = arena()
    healer = world.spawn_unit(player, UnitType.CLERIC, (6.5, 6.5))
    patient = world.spawn_unit(player, UnitType.FOOTMAN, (11.5, 6.5))
    patient.hp = 10
    world.hold([patient.id])
    destination = (18.0, 6.5)
    getattr(world, command)([healer.id], destination)
    world.update_vision()
    advance(world, .25)
    assert isinstance(healer.order, Heal)
    loaded = World.from_dict(world.to_dict())
    for match in (world, loaded):
        actor = match.units[healer.id]
        alternative = match.spawn_unit(player, UnitType.KNIGHT, (actor.x + 1, actor.y))
        alternative.hp = 10
        match.hold([alternative.id])
        match.update_vision()
        advance(match, .5)
        assert isinstance(actor.order, Heal) and actor.order.auto and actor.order.target == alternative.id
        assert alternative.hp > 10
    assert world.to_dict() == loaded.to_dict()
    actor = loaded.units[healer.id]
    for _ in range(round(35 / SIM_DT)):
        advance(loaded, SIM_DT)
        if math.dist(actor.pos, destination) < .3:
            break
    assert math.dist(actor.pos, destination) < .3


@pytest.mark.parametrize("hidden_kind", ["catapult", "tower"])
def test_unobserved_enemy_pressure_cannot_change_healing_choices(hidden_kind):
    """Hidden long-range threats must not influence which owned patient receives treatment."""
    observations = []
    for hidden in (False, True):
        world = arena()
        healer = world.spawn_unit(0, UnitType.CLERIC, (6.5, 6.5))
        farther = world.spawn_unit(0, UnitType.FOOTMAN, (10.5, 6.5))
        nearer = world.spawn_unit(0, UnitType.KNIGHT, (7.5, 6.5))
        farther.hp = nearer.hp = 10
        world.hold([farther.id, nearer.id])
        if hidden:
            if hidden_kind == "catapult":
                threat = world.spawn_unit(1, UnitType.CATAPULT, (17.5, 6.5))
                world.hold([threat.id])
                tiles = [threat.tile]
            else:
                threat = world.place_building(1, BuildingType.TOWER, (17, 5))
                tiles = list(threat.tiles())
        world.update_vision()
        if hidden:
            assert not any(world.is_visible(0, tile) for tile in tiles)
        advance(world, .5)
        observations.append([(unit.id, unit.pos, unit.hp, unit.order) for unit in world.player_units(0)])
    assert observations[0] == observations[1]


def test_a_moving_healer_reaches_a_patient_through_the_legal_crossing():
    """Acquiring a patient during attack-move must keep actual movement inside the map and off water."""
    terrain = [[Terrain.GRASS] * 24 for _ in range(18)]
    for y in range(18):
        if y not in (2, 3):
            terrain[y][9] = terrain[y][10] = Terrain.WATER
    world = arena(terrain)
    healer = world.spawn_unit(0, UnitType.CLERIC, (6.5, 7.5))
    patient = world.spawn_unit(0, UnitType.FOOTMAN, (15.5, 7.5))
    patient.hp = 40
    world.hold([patient.id])
    world.attack_move([healer.id], (18, 7.5))
    world.update_vision()
    advance(world, 12)
    assert healer.x > 10
    assert patient.hp > 40
