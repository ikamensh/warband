"""What a player can pile up on the world is bounded.

Plans and queued orders cost the simulation time every second and travel in every online snapshot.
Without a bound, one seat of a public room could queue tens of thousands of them (the server allows
twenty orders a second) until the shared server crawled for every room on it.
"""
import pytest

from warband.model import RuleError
from warband.rules import MAX_PLANS, MAX_QUEUED_ORDERS, BuildingType, UnitType
from tests.warband.battlefield import field


def test_a_player_holds_a_bounded_number_of_plans_and_room_returns_when_one_goes() -> None:
    world = field()
    world.reveal_all(0)  # the farm's site is ground the player knows
    plans = [world.order_unit(0, UnitType.FOOTMAN) for _ in range(MAX_PLANS)]
    with pytest.raises(RuleError, match="plans"):
        world.order_unit(0, UnitType.FOOTMAN)
    with pytest.raises(RuleError, match="plans"):
        world.plan_building(0, BuildingType.FARM, (10, 10))
    assert len(world.player_plans(0)) == MAX_PLANS
    world.order_unit(1, UnitType.FOOTMAN)  # the other seat's allowance is its own
    world.cancel_plan(0, plans[0])
    world.plan_building(0, BuildingType.FARM, (10, 10))
    assert len(world.player_plans(0)) == MAX_PLANS


def test_a_units_queue_of_orders_is_bounded_and_a_fresh_order_still_clears_it() -> None:
    world = field()
    squad = [world.spawn_unit(0, UnitType.FOOTMAN, (8.5 + i, 8.5)) for i in range(3)]
    ids = [u.id for u in squad]
    for i in range(MAX_QUEUED_ORDERS):
        world.move(ids, (10.5 + i % 5, 12.5), queue=True)
    before = world.to_dict()
    for order in (lambda: world.move(ids, (20.5, 20.5), queue=True), lambda: world.attack_move(ids, (20.5, 20.5), queue=True),
                  lambda: world.patrol(ids, (20.5, 20.5), queue=True), lambda: world.smart(ids, (20.5, 20.5), queue=True)):
        with pytest.raises(RuleError, match="queued"):
            order()
    assert world.to_dict() == before, "a refused order changed the world"
    world.move(ids, (20.5, 20.5))
    assert all(len(u.orders) == 1 for u in squad)
