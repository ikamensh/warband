"""Snapshots are built from explicit permitted fields, never from the save.

A seat's and a spectator's snapshot used to start from ``World.to_dict()`` — the whole
saved world — and redact it.  Any field a later save change added would travel until
someone remembered to redact it too.  These tests drive the public authority with the
save serializers rigged to fail (and to smuggle a sentinel): real snapshots must still
be produced, still decode through ``World.from_dict``, and never carry the sentinel.
"""
import json

import pytest

from warband.online.authority import WarbandMatch
from warband.sim import model as model_module
from warband.sim.model import World
from warband.sim.rules import BuildingType
from warband.sim.settlement import Settlement
from warband.sim.worker_knowledge import WorkerKnowledge

SENTINEL = "save-only-sentinel-that-must-never-travel"


def fogged_match() -> WarbandMatch:
    match = WarbandMatch(seed=3)
    for _ in range(40):
        match.step()
    return match


def wire(snapshot: dict) -> dict:
    return json.loads(json.dumps(snapshot))


@pytest.fixture
def save_serializers_rigged(monkeypatch: pytest.MonkeyPatch):
    """Every save serializer fails loudly if snapshot construction reaches for it."""

    def forbidden(name):
        def call(*args, **kwargs):
            raise AssertionError(f"snapshot construction called save serializer {name} ({SENTINEL})")

        return call

    monkeypatch.setattr(World, "to_dict", forbidden("World.to_dict"))
    for name in ("_unit_to_dict", "_building_to_dict", "_projectile_to_dict", "_order_to_dict"):
        monkeypatch.setattr(model_module, name, forbidden(name))
    monkeypatch.setattr(WorkerKnowledge, "to_dict", forbidden("WorkerKnowledge.to_dict"))
    monkeypatch.setattr(Settlement, "to_dict", forbidden("Settlement.to_dict"))
    yield


def test_seat_snapshot_is_built_without_the_save_and_still_decodes(save_serializers_rigged) -> None:
    match = fogged_match()
    world = match.world
    for seat in range(world.seats):
        sent = wire(match.snapshot(seat))
        assert SENTINEL not in json.dumps(sent)
        seen = World.from_dict(sent["world"])
        assert {u.id for u in world.player_units(seat)} <= {u.id for u in seen.units.values()}
        rival = 1 - seat
        hidden = [u.id for u in world.player_units(rival) if not world.is_visible(seat, u.tile)]
        assert hidden and not set(hidden) & {u.id for u in seen.units.values()}
        rival_hall = world.player_buildings(rival, BuildingType.TOWN_HALL)[0]
        assert rival_hall.id not in seen.buildings


def test_observer_snapshot_is_built_without_the_save_and_still_decodes(save_serializers_rigged) -> None:
    match = fogged_match()
    world = match.world
    sent = wire(match.observer_snapshot())
    assert SENTINEL not in json.dumps(sent)
    seen = World.from_dict(sent["world"])
    assert {u.id for u in seen.units.values()} == {u.id for u in world.units.values()}
    assert {b.id for b in seen.buildings.values()} == {b.id for b in world.buildings.values()}
    assert seen.settlement.plans == []
    assert all(not list(u.orders) for u in seen.units.values()), "a spectator is told no intentions"


WORLD_KEYS = {
    "width", "height", "theme", "layout", "magic", "wilds", "gates", "rifts", "gate_links", "terrain",
    "players", "regrowth", "camps", "units", "buildings", "projectiles", "explored", "worker_knowledge",
    "settlement", "time", "tick", "next_id", "winner", "scripted", "rng", "exposures",
}
PLAYER_KEYS = {
    "id", "name", "human", "race", "gold", "lumber", "aether", "aether_charge", "alive", "neutral",
    "surrendered", "stats", "last_alert", "last_hit", "upgrades", "cooldowns", "assembly",
}
UNIT_KEYS = {
    "id", "type", "player", "x", "y", "hp", "facing", "orders", "cooldown", "windup", "vx", "vy",
    "worker_orders", "carrying", "carry", "timer", "inside", "constructing", "home", "state", "ease",
    "charge", "auto_work", "commanded", "struck", "conditions", "expires", "slam_point",
}
BUILDING_KEYS = {
    "id", "type", "player", "x", "y", "hp", "max_hp", "progress", "queue", "train_progress", "rally",
    "gold", "builder", "cooldown", "research", "research_progress", "abandoned", "auto",
}
CAMP_KEYS = {
    "lair", "kinds", "posts", "guards", "origin", "watch", "struck", "roused", "quiet_since",
    "encounter", "gold", "lumber", "cleared", "credit",
}
KNOWLEDGE_KEYS = {
    "width", "height", "terrain", "buildings", "encounters", "watches", "cleared_encounters",
    "fallen_guards", "guard_warnings", "mines",
}


def test_every_snapshot_record_carries_only_its_named_fields() -> None:
    """The wire schema itself: a new save field has no record here to ride in on."""
    match = fogged_match()
    for snapshot in (match.snapshot(0), match.snapshot(1), match.observer_snapshot()):
        world = wire(snapshot)["world"]
        assert set(world) == WORLD_KEYS
        assert all(set(player) == PLAYER_KEYS for player in world["players"])
        assert all(set(unit) == UNIT_KEYS for unit in world["units"])
        assert all(set(building) == BUILDING_KEYS for building in world["buildings"])
        assert all(set(camp) == CAMP_KEYS for camp in world["camps"])
        assert all(set(knowledge) == KNOWLEDGE_KEYS for knowledge in world["worker_knowledge"])
        assert set(world["settlement"]) == {"next_id", "plans"}
        assert all(set(plan) == {"id", "player", "kind", "type", "pos", "status", "worker", "building"}
                   for plan in world["settlement"]["plans"])


def test_a_smuggled_save_field_never_appears_in_either_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even if a future save grows a new field, an explicit snapshot cannot inherit it."""
    real = World.to_dict

    def smuggling(self):
        data = real(self)
        data[SENTINEL] = SENTINEL
        for record in (*data["players"], *data["units"], *data["buildings"], *data["camps"]):
            record[SENTINEL] = SENTINEL
        return data

    monkeypatch.setattr(World, "to_dict", smuggling)
    match = fogged_match()
    for snapshot in (match.snapshot(0), match.snapshot(1), match.observer_snapshot()):
        assert SENTINEL not in json.dumps(snapshot)
        World.from_dict(wire(snapshot)["world"])  # and what is sent still loads
