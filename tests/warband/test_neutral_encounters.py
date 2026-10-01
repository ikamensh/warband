"""Playable neutral objectives: strength, progress, rewards and tactical counterplay."""

import pytest

from warband.sim.model import World
from warband.sim.rules import Terrain, UnitType


def test_encounters_offer_three_meaningfully_different_commitments():
    """The shipped catalogue has early raids, mixed-army strongholds and a distinct apex guardian."""
    from warband.sim.rules import CAMP_ENCOUNTERS, UNITS
    from warband.sim.camps import place_encounter

    world = World(50, 40, [[Terrain.GRASS] * 50 for _ in range(40)], 2)
    assert {info.tier for info in CAMP_ENCOUNTERS.values()} == {"Raid", "Stronghold", "Ancient"}
    info = CAMP_ENCOUNTERS["ancient_sanctum"]
    camp = place_encounter(world, (24, 18), "ancient_sanctum")
    assert world.camp_for(camp.lair) is camp
    assert camp.gold == info.gold and camp.lumber == info.lumber
    guardian = next(world.units[uid] for uid in camp.guards if world.units[uid].type.value == "ancient_guardian")
    assert guardian.max_hp > 3 * UNITS[UnitType.GOLEM].hp
    assert guardian.info.windup >= 1.5 and guardian.info.splash >= 2
    assert info.gold >= 4 * UNITS[UnitType.FOOTMAN].cost.gold


def camp_world(roster=(UnitType.WOLF,)):
    """A scripted sandbox with live opponents, so encounter orders run until their own conclusion."""
    from warband.sim.camps import place
    world = World(50, 40, [[Terrain.GRASS] * 50 for _ in range(40)], 2, scripted=True)
    camp = place(world, (24, 18), list(roster), 1200)
    return world, camp


def advance(world, seconds):
    from warband.sim.rules import SIM_DT
    for _ in range(round(seconds / SIM_DT)):
        world.step()


def test_defeated_guards_stay_dead_and_surviving_lair_waits_for_completion():
    """An expedition makes permanent progress; payday requires the whole encounter, in either kill order."""
    world, camp = camp_world()
    hunter = world.spawn_unit(0, UnitType.KNIGHT, (25.5, 24.5))
    guard = camp.guards[0]
    world.attack([hunter.id], guard)
    advance(world, 12)
    assert guard not in world.units
    assert not camp.cleared
    world.move([hunter.id], (5.5, 5.5))
    advance(world, 65)
    assert not any(uid in world.units for uid in camp.guards), "guard kills must not be erased by a retreat"
    world.attack([hunter.id], camp.lair)
    advance(world, 190)
    assert camp.cleared
    assert world.players[0].stats["bounty_gold"] == camp.gold


def test_stone_slam_commits_to_visible_ground_and_can_be_dodged():
    """A marked slam is a tactical decision: moving out during windup avoids the committed impact."""
    world, camp = camp_world((UnitType.GOLEM,))
    golem = world.units[camp.guards[0]]
    knight = world.spawn_unit(0, UnitType.KNIGHT, (golem.x + 1.0, golem.y))
    world.hold([knight.id])
    for _ in range(100):
        world.step()
        if golem.slam_point is not None:
            break
    assert golem.slam_point is not None
    marked = golem.slam_point
    saved = world.to_dict()
    restored = World.from_dict(saved)
    assert restored.to_dict() == saved and restored.units[golem.id].slam_point == marked
    hp = knight.hp
    world.move([knight.id], (knight.x + 8, knight.y))
    advance(world, golem.info.windup + 0.2)
    impacts = [event for event in world.take_events() if event.kind == "slam"]
    assert impacts and impacts[0].pos == marked
    assert knight.hp == hp


def test_ground_slam_damages_hostile_buildings_but_spares_air_and_friends():
    """Building retaliation cannot turn stone guards harmless; the ground attack keeps its target rules."""
    from warband.sim.rules import BuildingType
    world = World(30, 24, [[Terrain.GRASS] * 30 for _ in range(24)], 2, scripted=True)
    farm = world.place_building(0, BuildingType.FARM, (14, 10))
    golem = world.spawn_unit(world.neutral, UnitType.GOLEM, (13.0, 11.0))
    friend = world.spawn_unit(world.neutral, UnitType.WOLF, (16.5, 11.0))
    flyer = world.spawn_unit(0, UnitType.FLYING_MACHINE, (15.0, 11.0))
    world.attack([golem.id], farm.id)
    hp, friend_hp, flyer_hp = farm.hp, friend.hp, flyer.hp
    advance(world, 6)
    assert farm.hp < hp
    assert friend.hp == friend_hp and flyer.hp == flyer_hp


def test_an_enemy_march_past_a_settled_camp_does_not_turn_into_an_expedition():
    """Seeing guards outside their watch must not divert a player's attack-move to an unrelated camp."""
    world, camp = camp_world()
    from warband.sim.camps import centre
    cx, cy = centre(world, camp)
    marcher = world.spawn_unit(0, UnitType.ARCHER, (cx + 8.0, cy - 4.5))
    world.reveal_all(0)
    world.attack_move([marcher.id], (cx + 8.0, cy + 5.5))
    advance(world, 8)
    assert not camp.roused
    assert not world.to_dict()["camps"][0]["credit"]
    assert all(world.units[uid].hp == world.units[uid].max_hp for uid in camp.guards)
    # An attack-move aimed at the encounter is an intentional expedition and still fights its guards.
    world.attack_move([marcher.id], (cx, cy))
    advance(world, 8)
    assert world.to_dict()["camps"][0]["credit"]


def test_ancient_answers_armed_flyers_without_attacking_unarmed_scouts():
    """A late flyer cannot farm the apex reward for free; reconnaissance remains safe and useful."""
    world, camp = camp_world((UnitType.ANCIENT_GUARDIAN,))
    guardian = world.units[camp.guards[0]]
    scout = world.spawn_unit(0, UnitType.FLYING_MACHINE, (guardian.x + 3, guardian.y))
    advance(world, 1)
    assert not camp.roused and scout.hp == scout.max_hp
    gryphon = world.spawn_unit(0, UnitType.GRYPHON, (guardian.x + 4, guardian.y))
    assert world.can_strike(guardian, gryphon)
    world.attack([gryphon.id], guardian.id)
    advance(world, 8)
    assert camp.roused
    assert gryphon.hp < gryphon.max_hp
    assert scout.hp == scout.max_hp


def test_pack_hunts_exposed_archers_and_spiders_make_melee_close_the_gap():
    """Different neutral bodies require different responses instead of merely scaling hit points."""
    from warband.sim.model import Attack, dist
    world, camp = camp_world()
    wolf = world.units[camp.guards[0]]
    screen = world.spawn_unit(0, UnitType.FOOTMAN, (wolf.x + 1.5, wolf.y))
    archer = world.spawn_unit(0, UnitType.ARCHER, (wolf.x + 3.5, wolf.y))
    world.hold([screen.id, archer.id])
    advance(world, 0.25)
    assert isinstance(wolf.order, Attack) and wolf.order.target == archer.id

    world, camp = camp_world((UnitType.SPIDER,))
    spider = world.units[camp.guards[0]]
    infantry = world.spawn_unit(0, UnitType.FOOTMAN, (spider.x + 2.3, spider.y))
    world.hold([infantry.id])
    opening = dist(spider.pos, infantry.pos)
    advance(world, 1.5)
    assert infantry.hp < infantry.max_hp
    assert dist(spider.pos, infantry.pos) > opening + 0.5


def test_bleeding_damage_earns_credit_and_restored_wounds_erase_it():
    """The same bounty accounting covers physical blows, ongoing wounds and actual recovery."""
    world, camp = camp_world()
    wolf = world.units[camp.guards[0]]
    archer = world.spawn_unit(0, UnitType.ARCHER, (wolf.x + 4.0, wolf.y))
    world.attack([archer.id], wolf.id)
    for _ in range(40):
        world.step()
        if wolf.conditions:
            break
    assert wolf.conditions
    world.move([archer.id], (5.5, 5.5))
    advance(world, 3)
    saved = world.to_dict()["camps"][0]
    assert sum(saved["credit"][str(wolf.id)].values()) == wolf.max_hp - wolf.hp
    advance(world, 50)
    assert wolf.hp == wolf.max_hp
    assert sum(world.to_dict()["camps"][0]["credit"][str(wolf.id)].values()) == pytest.approx(0.0)


def test_automatic_miner_routes_around_a_remembered_camps_whole_watch():
    """Avoiding individual guards is insufficient: a working peasant must not rouse their lair en route."""
    from warband.sim.rules import BuildingType
    world, camp = camp_world((UnitType.GOLEM,))
    world.place_building(0, BuildingType.TOWN_HALL, (3, 18))
    world.place_building(None, BuildingType.GOLD_MINE, (40, 18))
    worker = world.spawn_unit(0, UnitType.PEASANT, (6.5, 19.5))
    world.players[0].gold = 0
    world.reveal_all(0)
    for _ in range(1600):
        world.step()
        assert not camp.roused
    assert worker.id in world.units and world.players[0].gold > 0


def test_siege_on_the_lair_wakes_its_guards_before_any_guard_is_hit():
    """Artillery outside the passive watch still commits to a fight when it attacks the den."""
    from warband.sim.camps import centre
    world, camp = camp_world()
    lair = world.buildings[camp.lair]
    cx, cy = centre(world, camp)
    siege = world.spawn_unit(0, UnitType.CATAPULT, (cx - 9.5, cy))
    world.attack([siege.id], lair.id)
    for _ in range(160):
        world.step()
        if lair.hp < lair.max_hp:
            break
    assert lair.hp < lair.max_hp
    assert all(world.units[uid].hp == world.units[uid].max_hp for uid in camp.guards)
    advance(world, 0.25)
    assert camp.roused
    assert world.players[0].stats["bounty_gold"] == 0


@pytest.mark.parametrize("legacy_origin", [False, True])
def test_online_camps_reveal_only_observed_encounters_and_never_contribution_ledgers(legacy_origin):
    """A room seat learns no unscouted camps, hidden guards or other players' effort."""
    from warband.online.authority import WarbandMatch
    match = WarbandMatch(seed=7)
    world, _camp = camp_world()
    if legacy_origin:
        saved = world.to_dict()
        for camp in saved["camps"]:
            del camp["origin"]  # an authoritative checkpoint written before static anchors
        for knowledge in saved["worker_knowledge"]:
            knowledge.pop("encounters", None)
            knowledge.pop("cleared_encounters", None)
        world = World.from_dict(saved)
    match.world = world
    match.begun = world.to_dict()["terrain"]
    hidden = [camp for camp in world.camps if not any(world.is_visible(0, tile) for tile in world.buildings[camp.lair].tiles())]
    assert hidden
    initial = match.snapshot(0)["world"]["camps"]
    assert not {camp.lair for camp in hidden} & {camp["lair"] for camp in initial}
    target = hidden[0]
    lair = world.buildings[target.lair]
    scout = world.spawn_unit(0, UnitType.FLYING_MACHINE, (lair.center[0], lair.center[1] + 4))
    world.update_vision()
    revealed = next(camp for camp in match.snapshot(0)["world"]["camps"] if camp["lair"] == target.lair)
    assert revealed["encounter"] == target.encounter
    assert not revealed["credit"]
    # A further observer must not receive contribution made while the camp was in somebody else's fog.
    attacker = world.spawn_unit(1, UnitType.ARCHER, (lair.center[0], lair.center[1] + 5))
    world.attack([attacker.id], target.lair)
    advance(world, 2)
    assert world.to_dict()["camps"][world.camps.index(target)]["credit"]
    assert not next(camp for camp in match.snapshot(0)["world"]["camps"] if camp["lair"] == target.lair)["credit"]
    world.move([scout.id], (2.5, 2.5))
    advance(world, 15)
    snapshot = match.snapshot(0)["world"]
    visible_ids = {unit["id"] for unit in snapshot["units"]}
    assert all(set(camp["guards"]) <= visible_ids and not camp["credit"] for camp in snapshot["camps"])
    # The observer retains a static location while a rival completes the encounter unseen.
    remembered_middle = lair.center
    army = [world.spawn_unit(1, UnitType.KNIGHT, (lair.center[0] + i, lair.center[1] + 4)) for i in range(3)]
    world.attack_move([unit.id for unit in army], lair.center)
    advance(world, 100)
    assert target.cleared
    from warband.sim.camps import centre
    client = World.from_dict(match.snapshot(0)["world"])
    remembered = next(camp for camp in client.camps if camp.lair == target.lair)
    assert not remembered.cleared, "completion in fog is still unknown"
    assert centre(client, remembered) == remembered_middle
    world.move([scout.id], remembered_middle)
    advance(world, 15)
    observed = World.from_dict(match.snapshot(0)["world"])
    assert next(camp for camp in observed.camps if camp.lair == target.lair).cleared


def test_online_encounter_memory_survives_a_fallen_lair_and_a_save():
    """A scouted expedition remains identifiable while its surviving guards fight without their den."""
    from warband.online.authority import WarbandMatch
    from warband.sim.camps import centre
    world, camp = camp_world()
    lair = world.buildings[camp.lair]
    middle = lair.center
    lair.hp = 1  # stage a damaged den; its guard is still unharmed
    world.spawn_unit(0, UnitType.FLYING_MACHINE, (middle[0], middle[1] + 4))
    archer = world.spawn_unit(1, UnitType.ARCHER, (middle[0], middle[1] + 5))
    world.update_vision()
    world.attack([archer.id], camp.lair)
    for _ in range(80):
        world.step()
        if camp.lair not in world.buildings:
            break
    assert camp.lair not in world.buildings and any(uid in world.units for uid in camp.guards)
    world.update_vision()
    assert camp.lair not in world.worker_knowledge[0].buildings
    match = WarbandMatch(seed=7)
    match.world = World.from_dict(world.to_dict())
    match.begun = match.world.to_dict()["terrain"]
    client = World.from_dict(match.snapshot(0)["world"])
    remembered = next(encounter for encounter in client.camps if encounter.lair == camp.lair)
    assert centre(client, remembered) == middle
    assert not remembered.cleared and not remembered.credit


def test_last_hit_cannot_steal_earned_bounty_and_saved_progress_pays_once():
    """Actual attacks earn conserved shares; retreat/save/load cannot erase or duplicate that effort."""
    world, camp = camp_world()
    camp.lumber = 150  # a custom resource reward, established before the expedition
    lair = world.buildings[camp.lair]
    lair.hp = lair.max_hp = 300  # the ordinary Raid cleanup health
    first = world.spawn_unit(0, UnitType.KNIGHT, (25.5, 24.5))
    second = world.spawn_unit(1, UnitType.KNIGHT, (40.5, 30.5))
    from warband.records.replay import Playback, Replay
    from warband.sim.rules import Difficulty
    world.update_vision()
    replay = Replay.begin(world, seed=0, difficulty=Difficulty.EASY, human=0)
    world.hold([second.id])
    world.attack([first.id], camp.guards[0])
    advance(world, 12)
    world.attack([first.id], camp.lair)
    for _ in range(1200):
        world.step()
        if world.buildings[camp.lair].hp < 90:
            break
    assert 0 < world.buildings[camp.lair].hp < 90
    assert world.players[0].stats["bounty_gold"] == 0
    world.move([first.id], (5.5, 5.5))
    advance(world, 15)
    restored = World.from_dict(world.to_dict())
    for match in (world, restored):
        match.attack([second.id], camp.lair)
        advance(match, 45)
        assert match.camps[0].cleared
        shares = [p.stats["bounty_gold"] for p in match.players[:match.seats]]
        wood = [p.stats["bounty_lumber"] for p in match.players[:match.seats]]
        assert shares[0] > shares[1] > 0
        assert sum(shares) == camp.gold and sum(wood) == camp.lumber
        assert sum(p.stats["camps_cleared"] for p in match.players[:match.seats]) == 1
        rewards = [event for event in match.take_events() if event.kind == "hoard"]
        assert len(rewards) == 2
        advance(match, 10)
        assert not any(event.kind == "hoard" for event in match.take_events())
    assert restored.to_dict() == world.to_dict()
    replay.finish(world, "left")
    playback = Playback(replay)
    playback.run()
    assert playback.faithful and playback.world.to_dict() == world.to_dict()
