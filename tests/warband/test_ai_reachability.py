"""Public brain decisions on the physical island captured by fuzz seed81."""
import random
from dataclasses import replace

from warband.brains.pro_ai import PRO_WARDEN, ProBrain
from warband.sim.model import Attack, AttackMove, World
from warband.sim.rules import BuildingType, Race, Terrain, UnitType


def boxed_army():
    """Keep the exact local terrain, completed buildings and troops of the archer820 checkpoint."""
    rows = (
        'grrrggtttggggttttttg', 'rrrrggtttggggttttttt',
        'grrrgggggggggggttttt', 'gggttggggggggggttttt',
        'gggggttggggggggttttt', 'ggggggttgggggggttttt',
        'wgggggggtgggggtttttt', 'gggggggggtgggttttttt',
        'gggggggggttggttttttt', 'gggggggggttggttttttt',
        'gggggggggtttgttttttt', 'ggggggggggttgtgttttt',
        'ggggggggggttgtgttgtt', 'gggggggggggtgggggggg',
        'gggggggggggtgggggggg', 'gggggggggggtgggttggg',
        'gggggggggggtgggtttgg', 'gggggggggggrgtgtttgg',
        'gggggggggggrgttttttt', 'gggggggggggttttttttt',
    )
    terrain = [[Terrain.GRASS] * 180 for _ in range(132)]
    types = {'g': Terrain.GRASS, 't': Terrain.TREES, 'r': Terrain.ROCK, 'w': Terrain.WATER}
    for y, row in enumerate(rows, 110):
        terrain[y][104:124] = [types[c] for c in row]
    world = World(180, 132, terrain, 2, rng=random.Random(81))
    world.scripted = True
    world.players[0].race = Race.DWARF
    world.players[0].gold = world.players[0].lumber = 0
    world.place_building(0, BuildingType.TOWN_HALL, (100, 124))
    for kind, point in (
        (BuildingType.FARM, (108, 122)), (BuildingType.BARRACKS, (104, 117)),
        (BuildingType.FARM, (108, 118)), (BuildingType.STABLES, (114, 115)),
        (BuildingType.FARM, (111, 120)), (BuildingType.BARRACKS, (116, 123)),
        (BuildingType.FARM, (105, 114)), (BuildingType.BARRACKS, (113, 111)),
        (BuildingType.FARM, (108, 111)), (BuildingType.CHURCH, (112, 123)),
        (BuildingType.FARM, (110, 127)), (BuildingType.FARM, (108, 115)),
    ):
        world.place_building(0, kind, point)
    target = world.place_building(1, BuildingType.BARRACKS, (55, 114))
    world.place_building(1, BuildingType.TOWN_HALL, (45, 110))
    trapped = [world.spawn_unit(0, kind, point) for kind, point in (
        (UnitType.ARCHER, (115.60644350973571, 118.00000033496387)),
        (UnitType.ARCHER, (115.01537880334759, 118.00031993600906)),
        (UnitType.FOOTMAN, (116.26278237355521, 118.68063532223671)),
        (UnitType.FOOTMAN, (116.97869784873541, 119.71128435972639)),
        (UnitType.ARCHER, (115.09530713586764, 118.6467336345104)),
        (UnitType.ARCHER, (116.01786993891425, 119.26717508294266)),
        (UnitType.ARCHER, (116.82339834147744, 118.10842777457422)),
        (UnitType.FOOTMAN, (116.20591576371187, 118.09539162198449)),
        (UnitType.FOOTMAN, (116.98932629987166, 118.67253052463234)),
        (UnitType.ARCHER, (116.6465690464809, 119.15029769098852)),
        (UnitType.ARCHER, (115.67988588435328, 118.58339575627821)),
    )]
    connected = [world.spawn_unit(0, UnitType.ARCHER, (102.5, 112.5 + i)) for i in range(3)]
    # The same forest pocket is passable to a forest walker and irrelevant to
    # an armed flyer. Both remain eligible for the real reinforcement order.
    connected.append(world.spawn_unit(0, UnitType.TREANT, (116.5, 119.5)))
    connected.append(world.spawn_unit(0, UnitType.GRYPHON, (116.5, 118.5)))
    world.time = 556.05
    world.reveal_all(0)
    return world, trapped, connected, target


def test_a_physically_trapped_reinforcement_is_not_reissued_an_unreachable_march():
    """Seed81: a completed nearest-edge walk must not be restarted forever by the reinforcement branch."""
    world, trapped, connected, target = boxed_army()
    brain = ProBrain(0, replace(PRO_WARDEN, scout=False, retreat_ratio=0, abort_ratio=0))
    brain.attacking = True
    brain.target = target.center
    brain.think(world, random.Random(81))
    assert all(not unit.orders for unit in trapped)
    assert all((isinstance(unit.order, AttackMove) and unit.order.target == target.center)
               or (isinstance(unit.order, Attack) and unit.order.target == target.id) for unit in connected)


def test_a_trapped_idle_army_is_not_reissued_a_disconnected_defense_order():
    """Seed81's earlier archer924 shared this pocket while the defense branch answered a real nearby rival."""
    world, trapped, connected, _ = boxed_army()
    rival = world.spawn_unit(1, UnitType.KNIGHT, (97.5044991683592, 113.36328121241378))
    world.hold([rival.id])
    world.reveal_all(0)
    world.attack([connected[0].id], rival.id)
    brain = ProBrain(0, replace(PRO_WARDEN, scout=False))
    brain.think(world, random.Random(81))
    assert all(not unit.orders for unit in trapped)
    assert isinstance(connected[0].order, Attack) and connected[0].order.target == rival.id
    assert all(isinstance(unit.order, AttackMove) and unit.order.target == rival.pos for unit in connected[1:])
