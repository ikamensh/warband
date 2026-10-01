"""Encounter cards, honest fog memory, danger warnings and accomplishment feedback."""

import pytest

from saga2d.effects import Burst, Toast
from warband.sim import camps
from warband.sim.model import Event
from warband.sim.rules import CAMP_ENCOUNTERS, UnitType
from warband.ui.scene import CAMP_TIPS, CodexScene, GameScene, codex_world
from warband.ui.icons import ResourceFloat
from warband.ui.view import Sighting
from warband.sim.rules import Race
from tests.warband.battlefield import SETTINGS, field, live_effects


def scene_with_camp(game, encounter="ancient_sanctum"):
    world = field()
    camp = camps.place_encounter(world, (18, 12), encounter)
    world.reveal_all(0)
    scene = GameScene(world, 9, ranked=False, settings=dict(SETTINGS))
    game.push(scene)
    scene.paused = True
    for _ in range(3):
        game.tick(0.1)
    scene.select([camp.lair], quiet=True)
    return scene, camp


def test_lair_card_names_danger_rewards_and_counterplay(game):
    scene, camp = scene_with_camp(game)
    game.tick(0.1)
    texts = {str(t["text"]) for t in game.backend.texts}
    info = CAMP_ENCOUNTERS[camp.encounter]
    assert info.name in texts
    assert any(info.tier in t and "guards" in t for t in texts)
    assert any(f"{camp.gold:,}" in t and f"{camp.lumber:,}" in t for t in texts)
    assert CAMP_TIPS[camp.encounter] in texts


def test_camp_sighting_roundtrips_the_scouted_reward(game):
    scene, camp = scene_with_camp(game, "wolf_den")
    remembered = scene.view.sighting(camp.lair)
    saved = remembered.to_dict()
    assert Sighting.from_dict(saved).to_dict() == saved
    assert remembered.camp_encounter == "wolf_den"
    assert remembered.camp_gold == camp.gold
    assert remembered.camp_roster == tuple(camp.kinds)


def test_wilds_codex_is_reachable_with_magic_off(game):
    game.push(CodexScene(codex_world(Race.HUMAN), 0, 4, in_match=False))
    game.tick(0.1)
    game.scene.next_page()
    game.tick(0.1)
    assert game.scene.page == 6
    for info in CAMP_ENCOUNTERS.values():
        assert info.name in " ".join(str(t["text"]) for t in game.backend.texts)
    game.scene.next_page()
    assert game.scene.page == 0


def test_clearing_an_ancient_is_announced_and_paid_visibly(game):
    scene, camp = scene_with_camp(game)
    scene.world.events += [Event("hoard", (19.5, 13.5), player=0, other=camp.lair, amount=1200, amount2=300),
                           Event("camp_cleared", (19.5, 13.5), player=0, other=camp.lair, text=camp.encounter)]
    game.tick(0.1)
    assert any(isinstance(effect, Toast) and effect.title == "The Ancient Guardian cleared!" for effect in live_effects(scene))
    rewards = {(effect.resource, effect.amount, effect.suffix) for effect in live_effects(scene) if isinstance(effect, ResourceFloat)}
    assert rewards == {("gold", 1200, "bounty"), ("lumber", 300, "bounty")}
    assert scene.status == "Camp bounty: 1,200 gold · 300 lumber"


def test_a_saved_custom_camp_can_complete_without_a_catalogue_identity(game):
    """Older saves contain custom rosters without an encounter key; their real completion must still render."""
    world = field()
    camps.place(world, (18, 12), [UnitType.WOLF], 1200)
    world = type(world).from_dict(world.to_dict())
    camp = world.camps[0]
    world.reveal_all(0)
    army = [world.spawn_unit(0, UnitType.KNIGHT, (13.5 + i % 3, 11.5 + i // 3)) for i in range(9)]
    world.attack_move([u.id for u in army], camp.posts[0])
    for _ in range(600):
        world.step()
        if camp.cleared:
            break
    assert camp.cleared
    scene = GameScene(world, 9, ranked=False, settings=dict(SETTINGS))
    game.push(scene)
    game.tick(0.1)
    assert any(isinstance(effect, Toast) and effect.title == "Creature camp cleared!" for effect in live_effects(scene))


def test_guardian_slam_is_drawn_at_its_committed_point(game):
    scene, camp = scene_with_camp(game)
    guardian = next(scene.world.units[uid] for uid in camp.guards if scene.world.units[uid].type is UnitType.ANCIENT_GUARDIAN)
    guardian.slam_point = (guardian.x + 1, guardian.y)
    guardian.windup = guardian.info.windup
    game.tick(0.1)
    # The mock backend records public rendering operations: a warning must draw a polygon ring in world space.
    marked = [op for op in game.backend.lines if op["color"][:3] == (239, 176, 247)]
    assert len(marked) >= 36
    x, y = guardian.slam_point
    assert abs(marked[0]["x1"] - (x + guardian.info.splash) * 32) < 0.001
    assert abs(marked[0]["y1"] - y * 32) < 0.001


def test_a_remembered_camp_keeps_its_scouted_reward_when_out_of_sight(game):
    world = field()
    camp = camps.place_encounter(world, (18, 12), "wolf_den")
    scout = world.spawn_unit(0, UnitType.FLYING_MACHINE, (19.5, 13.5))
    world.update_vision()
    scene = GameScene(world, 9, ranked=False, settings=dict(SETTINGS))
    game.push(scene)
    game.tick(0.1)
    seen = scene.view.sighting(camp.lair).to_dict()
    world.move([scout.id], (2.5, 2.5))
    for _ in range(100):
        world.step()
    world.update_vision()
    scene.paused = True
    assert not world.is_visible(0, (19, 13))
    # Staged unseen change: the view must keep the prior sighting rather than reading a live camp.
    camp.gold += 1000
    game.tick(0.1)
    assert scene.view.sighting(camp.lair).to_dict() == seen


def test_a_dodged_slam_still_shows_its_stone_impact(game):
    scene, camp = scene_with_camp(game)
    scene.world.events.append(Event("slam", (19.5, 13.5), player=scene.world.neutral,
                                    text=UnitType.ANCIENT_GUARDIAN.value, amount=270))
    game.tick(0.1)
    assert any(isinstance(effect, Burst) for effect in live_effects(scene))


def test_results_show_shared_bounty_without_claiming_the_clear(game):
    """A contributor who did not earn dominant clear credit still sees their bounty in the battle record."""
    scene, _ = scene_with_camp(game)
    scene.player.stats.update(bounty_gold=1200, bounty_lumber=300)
    scene.world.winner = 0
    game.tick(0.1)
    game.tick(0.1)
    texts = {str(t["text"]) for t in game.backend.texts}
    assert "Bounty: 1,200 gold · 300 lumber" in texts


def test_guardian_tracking_shot_draws_its_obsidian_shard(game):
    """The real anti-air attack reaches the view as a shard, so it cannot inherit an archer's arrow."""
    scene, camp = scene_with_camp(game)
    world = scene.world
    guardian = next(world.units[uid] for uid in camp.guards if world.units[uid].type is UnitType.ANCIENT_GUARDIAN)
    flyer = world.spawn_unit(0, UnitType.GRYPHON, (guardian.x + 4, guardian.y))
    world.attack([flyer.id], guardian.id)
    for _ in range(160):
        world.step()
        shots = [p for p in world.projectiles.values() if p.source == guardian.id]
        if shots:
            break
    assert shots, "guardian must answer the armed flyer"
    game.tick(0.1)
    sprite = scene.view.shot_sprites[shots[0].id]
    assert sprite.visible
    assert sprite.image == "shard"


@pytest.mark.slow
def test_reward_capture_matches_an_actually_completed_encounter(game):
    """A full Ancient assault: the native capture fixture must show earned rewards after every guard and lair fall."""
    from tools.visual_lint import neutral_reward
    neutral_reward(game)
    scene = game.scene
    camp = scene.world.camps[0]
    assert camp.cleared
    assert scene.world.entity(camp.lair) is None
    assert not any(uid in scene.world.units for uid in camp.guards)
    assert scene.status == f"Camp bounty: {camp.gold:,} gold · {camp.lumber:,} lumber"
    assert scene.stats["camps_cleared"] == 1
    assert scene.stats["bounty_gold"] == camp.gold
    assert scene.stats["bounty_lumber"] == camp.lumber
