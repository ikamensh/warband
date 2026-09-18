"""Units at ease keep elbow room and loosen a packed crowd (docs/unit-motion.md part 5)."""

from warband.model import World, dist
from warband.rules import SIM_DT, UNIT_RADIUS, BuildingType, Terrain, UnitType

TOUCHING = 2 * UNIT_RADIUS


def open_field(width: int = 30, height: int = 24) -> World:
    world = World(width, height, [[Terrain.GRASS] * width for _ in range(height)], 2)
    world.rng.seed(1)
    return world


def packed_footmen(world: World, player: int = 0, at=(10.0, 10.0), side: int = 3, gap: float = TOUCHING):
    """A square block of footmen standing shoulder to shoulder."""
    return [world.spawn_unit(player, UnitType.FOOTMAN, (at[0] + (i % side) * gap, at[1] + (i // side) * gap))
            for i in range(side * side)]


def nearest(units) -> list[float]:
    return [min(dist(u.pos, v.pos) for v in units if v is not u) for u in units]


def run(world: World, seconds: float) -> None:
    for _ in range(int(seconds / SIM_DT)):
        world.step()


def test_idle_soldiers_standing_shoulder_to_shoulder_loosen_up():
    """Footmen dropped touching each other and left alone drift apart to arm's length, without
    wandering off, leaving the map or being given any order for it (they stay idle to Tab and the AI)."""
    world = open_field()
    units = packed_footmen(world)
    before = [u.pos for u in units]
    run(world, 15)
    assert min(nearest(units)) > TOUCHING + 0.1
    assert all(dist(u.pos, p) < 3.0 for u, p in zip(units, before))
    assert all(not u.orders and u.state == "idle" for u in units)
    assert all(world.passable(*u.tile) for u in units)


def test_a_crowd_sent_to_a_point_still_arrives_and_settles():
    """Elbow room must not keep a marching group pressing forever: sixteen footmen ordered to one spot
    all finish the order within the time the tight crowd used to take, and end up around the spot."""
    world = open_field(40, 30)
    units = [world.spawn_unit(0, UnitType.FOOTMAN, (5 + (i % 4) * 0.8, 5 + (i // 4) * 0.8)) for i in range(16)]
    target = (20.5, 15.5)
    world.move([u.id for u in units], target)
    run(world, 22)
    assert all(not u.orders for u in units)
    assert all(dist(u.pos, target) < 4.0 for u in units)
    assert min(nearest(units)) > TOUCHING + 0.1


def test_held_soldiers_keep_their_exact_spots():
    """Hold position means hold: a packed block told to hold neither eases apart nor steps away."""
    world = open_field()
    units = packed_footmen(world)
    world.hold([u.id for u in units])
    before = [u.pos for u in units]
    run(world, 15)
    assert all(dist(u.pos, p) < 1e-6 for u, p in zip(units, before))


def test_a_soldier_at_ease_makes_room_for_a_fighting_ally_instead_of_shoving_it():
    """The comfort push moves the unit that wants room, never the one in a fight: a peasant idling
    against an ally hitting a wall steps back (a soldier would join in), and the attacker keeps landing blows."""
    world = open_field()
    wall = world.place_building(1, BuildingType.TOWN_HALL, (14, 10))
    attacker = world.spawn_unit(0, UnitType.FOOTMAN, (13.6, 10.5))
    bystander = world.spawn_unit(0, UnitType.PEASANT, (13.6, 11.2))
    world.attack([attacker.id], wall.id)
    hits = 0
    for _ in range(int(6 / SIM_DT)):
        world.step()
        hits += sum(e.kind == "hit" and e.entity == attacker.id for e in world.take_events())
    assert hits >= 4
    assert dist(attacker.pos, bystander.pos) > TOUCHING + 0.1
    assert attacker.state == "attack" and not bystander.orders
