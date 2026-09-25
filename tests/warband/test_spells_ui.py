"""The spells in the match's HUD (WB-066): the spell bar, aiming and casting through the scene's input, the Mage Tower's
card of levels, and a spell's landing seen and heard.  Mock backend, through the scene's input."""

import math

import pytest

from saga2d import Game
from warband.art.textures import TILE
from warband.sim.model import Event
from warband.sim.rules import AETHER_STORE, BUFFS, SIM_DT, SPELL_FAR, SPELLS, UNITS, BuildingType, UnitType, Upgrade
from warband.ui.controls import SCHEMES
from warband.ui.scene import AIM, new_game
from warband.ui.spellbar import SpellButton, aim_ink
from warband.ui.style import BAD, build_theme
from warband.ui.view import METEOR_WARNING, to_world


@pytest.fixture
def play(tmp_path):
    game = Game("Warband spells", backend="mock", resolution=(1280, 800), theme=build_theme(), save_dir=tmp_path / "saves")
    scene = new_game(seed=3, settings={"music": 0, "sfx": 0, "tutorial": False})
    game.push(scene)
    game.tick(1 / 60)
    yield game, scene
    game.close()


def screen_of(scene, point) -> tuple[int, int]:
    sx, sy = scene.camera.world_to_screen(point[0] * 32, point[1] * 32)
    return int(sx), int(sy)


def click_map(game, scene, point, button: str = "left") -> None:
    x, y = screen_of(scene, point)
    game.backend.inject_mouse_move(x, y)
    game.backend.inject_click(x, y, button)
    game.backend.inject_release(x, y, button)
    game.tick(1 / 60)


def point_at(game, scene, point) -> None:
    game.backend.inject_mouse_move(*screen_of(scene, point))
    game.tick(1 / 60)


def press(game, key: str, **modifiers) -> None:
    game.backend.inject_key(key, **modifiers)
    game.tick(1 / 60)


def hall(scene):
    return scene.world.player_buildings(scene.human, BuildingType.TOWN_HALL)[0]


def learn(scene, *spells: Upgrade, aether: int = 400) -> None:
    scene.world.players[scene.human].upgrades.update(spells)
    scene.world.players[scene.human].aether = aether


def near_hall(scene, dx: float = 5.5, dy: float = 1.5) -> tuple[float, float]:
    home = hall(scene)
    return home.x + dx, home.y + dy


def test_a_player_learns_where_the_spells_come_from_before_having_one(play) -> None:
    """Before a spell is chosen nothing on the map shows magic, so the words must: the help says a vault draws aether
    for the spells a Mage Tower researches and which keys aim them; on the Build card the tower says what it needs and
    that its spells are cast with aether, beside the vault that draws it."""
    game, scene = play
    press(game, "f1")
    help_text = " ".join(t["text"] for t in game.backend.texts)
    assert all(words in help_text for words in ("vault", "aether for the spells a Mage Tower researches", "Alt+1-3")), help_text
    press(game, "escape")
    worker = next(u for u in scene.world.player_units(scene.human) if u.is_worker)
    scene.select([worker.id])
    scene.open_catalogue("build")
    game.tick(1 / 60)
    tips = {}
    for command, button in zip(scene.card, scene.card_buttons):
        if command.target in (BuildingType.VAULT, BuildingType.MAGE_TOWER):
            x, y, w, h = button.bounds
            game.backend.inject_mouse_move(x + w / 2, y + h / 2)
            game.tick(1 / 60)
            tips[command.target] = scene.tooltip
    assert "aether" in tips[BuildingType.VAULT], tips
    assert "spells, cast with aether" in tips[BuildingType.MAGE_TOWER] and "(Requires an Arcane Vault)" in tips[BuildingType.MAGE_TOWER], tips


def test_the_spell_bar_shows_the_chosen_spells_once_there_is_one(play) -> None:
    game, scene = play
    assert not scene.spell_bar.visible
    learn(scene, Upgrade.HASTE, Upgrade.WITHER)
    game.tick(1 / 60)
    buttons = [c for c in scene.spell_bar.walk() if isinstance(c, SpellButton)]
    assert scene.spell_bar.visible and [b.spell for b in buttons] == [Upgrade.HASTE, Upgrade.WITHER]
    assert [b.key for b in buttons] == ["1", "2"]
    texts = " ".join(t["text"] for t in game.backend.texts)
    assert "Haste" in texts and "Wither" in texts and "Alt +" in texts


@pytest.mark.parametrize("resolution", [(1200, 680), (1280, 800)], ids=lambda r: f"{r[0]}x{r[1]}")
def test_the_spell_bar_never_covers_the_settlement_or_the_command_row(tmp_path, resolution) -> None:
    """Over the tallest minimap a map is drawn with (a Small map's), a side's three spells stand in one column; nine, a
    verification's world, stand a level a row rather than rise over the rows above."""
    game = Game("Warband spells", backend="mock", resolution=resolution, theme=build_theme(), save_dir=tmp_path / "saves")
    try:
        scene = new_game(seed=3, settings={"music": 0, "sfx": 0, "tutorial": False})
        game.push(scene)
        for spells, laid in (((Upgrade.HASTE, Upgrade.WITHER, Upgrade.METEOR), [[1], [2], [3]]), (tuple(SPELLS), [[1] * 3, [2] * 3, [3] * 3])):
            scene.world.players[scene.human].upgrades.update(spells)
            game.tick(1 / 60)
            rows = [row for row in scene.spell_bar.children if any(isinstance(c, SpellButton) for c in row.children)]
            assert [[button.info.level for button in row.children] for row in rows] == laid
            top = scene.spell_bar.bounds[1]
            for above in (scene.settlement_row, scene.command_row):
                assert above.bounds[1] + above.bounds[3] <= top, (len(spells), above.bounds, scene.spell_bar.bounds)
            assert top + scene.spell_bar.bounds[3] <= scene.minimap.bounds[1]
    finally:
        game.close()


@pytest.mark.parametrize("controls", list(SCHEMES))
def test_alt_and_a_levels_number_aim_its_spell_and_a_click_casts_it(play, controls) -> None:
    """Alt with 1, 2 or 3 in every scheme: the plain digits stay the control groups."""
    game, scene = play
    scene.settings["controls"] = controls
    scene.apply_settings()
    learn(scene, Upgrade.FLAME_STRIKE)
    foe = scene.world.spawn_unit(1, UnitType.PEASANT, near_hall(scene))
    game.tick(1 / 60)
    press(game, "1", alt=True)
    assert scene.aiming is Upgrade.FLAME_STRIKE and "Flame Strike: click the map" in scene.status
    click_map(game, scene, foe.pos)
    assert scene.aiming is None and scene.world.cooldown_left(scene.human, Upgrade.FLAME_STRIKE) > 0
    assert foe.hp < foe.max_hp or foe.id not in scene.world.units


def test_esc_or_a_right_click_takes_an_aimed_spell_back_and_nothing_is_cast(play) -> None:
    game, scene = play
    learn(scene, Upgrade.HASTE)
    game.tick(1 / 60)
    for undo in (lambda: press(game, "escape"), lambda: click_map(game, scene, near_hall(scene), "right")):
        press(game, "1", alt=True)
        assert scene.pending == AIM + "haste"
        undo()
        assert scene.aiming is None
    assert not scene.world.players[scene.human].cooldowns


def test_a_refused_cast_says_why_on_the_status_line_and_stays_aimed(play) -> None:
    game, scene = play
    learn(scene, Upgrade.METEOR, aether=10)
    game.tick(1 / 60)
    press(game, "3", alt=True)
    click_map(game, scene, near_hall(scene))
    assert scene.status.startswith("Not enough aether") and scene.aiming is Upgrade.METEOR
    _icon, label = scene.resource_pair("aether")
    assert label.style.text_color == BAD, "the store's number flashes red, as gold's does"


def test_a_spell_of_a_level_not_yet_chosen_says_so(play) -> None:
    game, scene = play
    press(game, "2", alt=True)
    assert scene.aiming is None and scene.status == "No level II spell yet: research one at a Mage Tower"
    assert not scene.selection, "Alt+2 is no control group"


def test_the_aim_shows_the_vaults_reach_and_the_price_at_the_pointer(play) -> None:
    game, scene = play
    world = scene.world
    rift = min(world.rifts, key=lambda r: abs(r[0] - hall(scene).x) + abs(r[1] - hall(scene).y))
    vault = world.place_building(scene.human, BuildingType.VAULT, rift)
    learn(scene, Upgrade.HASTE)
    game.tick(1 / 60)
    press(game, "1", alt=True)
    assert scene.reach_shown() == [vault.center]
    point_at(game, scene, vault.center)
    assert "Haste · 30 aether" in " ".join(t["text"] for t in game.backend.texts)
    assert ("Click", "cast Haste: 30 aether") in scene.hint()
    far = (vault.center[0] + 15.0, vault.center[1])
    point_at(game, scene, far)
    assert scene.cast_price_at(scene.hover) == (30 * SPELL_FAR, True)
    assert f"Haste · 90 aether · {SPELL_FAR}× beyond your vaults' reach" in " ".join(t["text"] for t in game.backend.texts)


def test_the_aim_is_the_circle_on_the_ground_the_spell_reaches(play) -> None:
    """A spell touches every body within its radius of the point, north and south as far as east and west, on square
    ground: the aim's ring is that circle, as the vaults' reach and the burst are.  A flattened ring showed the units
    north and south of the point that the spell would land on as outside it."""
    game, scene = play
    learn(scene, Upgrade.WITHER)
    game.tick(1 / 60)
    press(game, "2", alt=True)
    point_at(game, scene, near_hall(scene))
    cx, cy = to_world(scene.hover)
    rings = [p["points"] for p in game.backend.polygons if p["space"] == "world" and p["color"] == (*aim_ink(True), 44)]
    assert len(rings) == 1, "no vault stands: the dearer price's ink"
    radius = SPELLS[Upgrade.WITHER].radius * TILE
    assert all(math.hypot(x - cx, y - cy) == pytest.approx(radius) for x, y in rings[0])


def test_a_falling_meteor_rings_the_circle_it_will_strike(play) -> None:
    game, scene = play
    learn(scene, Upgrade.METEOR)
    point = near_hall(scene)
    scene.world.cast(scene.human, Upgrade.METEOR, point)
    game.tick(1 / 60)
    cx, cy = to_world(point)
    ring = [line for line in game.backend.lines if line["color"] == METEOR_WARNING]
    radius = SPELLS[Upgrade.METEOR].radius * TILE
    assert ring and all(math.hypot(line["x1"] - cx, line["y1"] - cy) == pytest.approx(radius) for line in ring)


def test_a_price_the_vaults_can_never_hold_says_so_on_the_bar_at_the_aim_and_in_the_refusal(play) -> None:
    """With no vault the store holds nothing, and the bar says so beside the price ("max 0").  One vault holds any plain
    price, so the bar then says nothing more; beyond its reach a Meteor costs three times its 120, more than one vault
    holds, which no wait pays: the aim says what the vaults hold, the refusal what will, and within reach it casts."""
    game, scene = play
    world = scene.world
    learn(scene, Upgrade.METEOR, aether=0)
    game.tick(1 / 60)
    assert "max 0" in [t["text"] for t in game.backend.texts]
    rift = min(world.rifts, key=lambda r: abs(r[0] - hall(scene).x) + abs(r[1] - hall(scene).y))
    vault = world.place_building(scene.human, BuildingType.VAULT, rift)
    world.players[scene.human].aether = world.aether_cap(scene.human)  # the one vault's store, full
    game.tick(1 / 60)
    assert not [t["text"] for t in game.backend.texts if t["text"].startswith("max ")]
    press(game, "3", alt=True)
    far = (vault.center[0] + 15.0, vault.center[1])
    price = SPELLS[Upgrade.METEOR].aether * SPELL_FAR
    assert 2 * AETHER_STORE < price <= 3 * AETHER_STORE  # three vaults hold it: two more than the one standing
    point_at(game, scene, far)
    assert f"Meteor · {price} aether · {SPELL_FAR}× beyond your vaults' reach · they hold {AETHER_STORE}" in [t["text"] for t in game.backend.texts]
    click_map(game, scene, far)
    assert scene.status == (f"Not enough aether ({price} needed, {SPELL_FAR}x beyond your vaults' reach): they hold {AETHER_STORE}, "
                            "cast it within their reach or build 2 more")
    assert scene.aiming is Upgrade.METEOR and world.players[scene.human].aether == AETHER_STORE
    click_map(game, scene, (vault.center[0] + 3.0, vault.center[1]))
    assert world.players[scene.human].aether == AETHER_STORE - SPELLS[Upgrade.METEOR].aether


def test_a_summoned_units_card_counts_the_seconds_before_it_is_gone(play) -> None:
    game, scene = play
    learn(scene, Upgrade.SUMMON)
    scene.world.cast(scene.human, Upgrade.SUMMON, near_hall(scene))
    elemental = next(u for u in scene.world.units.values() if u.type is UnitType.AETHER_ELEMENTAL)
    scene.select([elemental.id])
    game.tick(1 / 60)
    left = math.ceil(scene.world.lifetime_left(elemental))
    assert left == UNITS[UnitType.AETHER_ELEMENTAL].lifetime and f"{left}s" in [t["text"] for t in game.backend.texts]
    for _ in range(int(round(10 / SIM_DT))):
        scene.world.step()
    game.tick(1 / 60)
    assert f"{math.ceil(scene.world.lifetime_left(elemental))}s" == f"{left - 10}s"
    assert f"{left - 10}s" in [t["text"] for t in game.backend.texts]


def test_a_card_under_many_spells_counts_what_its_row_has_no_room_for(play) -> None:
    """Four of the side's own spells and a rival's Wither on one footman: the row beside its hit points shows what fits,
    right of them, and counts the rest."""
    game, scene = play
    footman = scene.world.spawn_unit(scene.human, UnitType.FOOTMAN, near_hall(scene))
    for kind in ("haste", "mend", "stoneskin", "battle_fury", "withered"):
        scene.world._lay(footman, BUFFS[kind], 1 if kind == "withered" else scene.human)  # staging: the conditions alone
    scene.select([footman.id])
    game.tick(1 / 60)
    texts = game.backend.texts
    hp = next(t for t in texts if t["text"] == f"{footman.hp}/{footman.max_hp}")
    hp_end = hp["x"] + game.backend.measure_text(hp["text"], hp["font_size"])[0]
    row = [t for t in texts if t["y"] == hp["y"] and t["anchor_x"] == "right"]  # the row's seconds and count, on its line
    assert row and all(t["x"] - game.backend.measure_text(t["text"], t["font_size"])[0] > hp_end for t in row)
    counts = [t["text"] for t in row if t["text"].startswith("+")]
    shown = sum(1 for t in row if t["text"].endswith("s"))
    assert counts == [f"+{5 - shown}"] and shown >= 1


def test_a_rooted_units_card_says_it_walks_nowhere(play) -> None:
    game, scene = play
    footman = scene.world.spawn_unit(scene.human, UnitType.FOOTMAN, near_hall(scene))
    scene.world._lay(footman, BUFFS["entangled"], 1)  # staging: a rival's roots, without the rival's spell
    scene.select([footman.id])
    game.tick(1 / 60)
    assert f"{-UNITS[UnitType.FOOTMAN].speed:+g}" in [t["text"] for t in game.backend.texts]


def test_a_spell_on_its_cooldown_sweeps_its_button_and_will_not_aim(play) -> None:
    game, scene = play
    learn(scene, Upgrade.HASTE)
    scene.world.cast(scene.human, Upgrade.HASTE, near_hall(scene))
    game.tick(1 / 60)
    assert scene.cooldown_share(Upgrade.HASTE) == pytest.approx(1.0, abs=0.01)
    for _ in range(int(15 / SIM_DT)):
        scene.world.step()
    game.tick(1 / 60)
    # No vault stands: the cast was the dearer one, 90 s of cooldown, and the sweep goes by those.
    assert scene.cooldown_share(Upgrade.HASTE) == pytest.approx(1 - 15 / 90, abs=0.01)
    press(game, "1", alt=True)
    assert scene.aiming is None and scene.status.startswith("Haste is ready in")


def test_the_mage_towers_card_lays_out_the_levels_with_the_chosen_and_the_closed(play) -> None:
    game, scene = play
    world = scene.world
    tower = world.place_building(scene.human, BuildingType.MAGE_TOWER, (hall(scene).x + 5, hall(scene).y + 5))
    learn(scene, Upgrade.MEND)
    scene.select([tower.id])
    game.tick(1 / 60)
    by_target = {c.target: c for c in scene.card}
    assert [by_target[s].slot for s in SPELLS] == [0, 1, 2, 3, 4, 5, 6, 7, 8]
    assert by_target[Upgrade.MEND].mark() == "chosen" and by_target[Upgrade.HASTE].mark() == "closed"
    assert by_target[Upgrade.STONESKIN].mark() == "" and by_target[Upgrade.STONESKIN].blocked() == "Requires Keep"
    assert by_target[Upgrade.HASTE].blocked() == "Closed: Mend was chosen"
    texts = [t["text"] for t in game.backend.texts]
    assert texts.count("Chosen") == 1 and texts.count("Closed") == 2
    world.players[scene.human].upgrades.add(Upgrade.KEEP)
    world.research(tower.id, Upgrade.WITHER)  # its level's others wait on it; a cancel would open them again
    game.tick(1 / 60)
    assert [by_target[s].mark() for s in (Upgrade.STONESKIN, Upgrade.ENTANGLE, Upgrade.WITHER)] == ["waiting", "waiting", ""]
    assert "Waiting" in [t["text"] for t in game.backend.texts]
    cancel = next(c for c in scene.card if c.label == "Cancel")
    assert cancel.slot == 11 and cancel.hotkey == "X"


def test_a_spell_landing_in_sight_bursts_and_sounds(play) -> None:
    game, scene = play
    learn(scene, Upgrade.WITHER)
    scene.world.cast(scene.human, Upgrade.WITHER, near_hall(scene))
    before = len(scene.effects)
    game.tick(1 / 60)
    assert "spell_wither" in scene.recent_sounds
    assert len(scene.effects) > before


def test_a_summoned_unit_breaks_into_light_when_it_is_gone(play) -> None:
    game, scene = play
    learn(scene, Upgrade.SUMMON)
    scene.world.cast(scene.human, Upgrade.SUMMON, near_hall(scene))
    game.tick(1 / 60)
    elemental = next(u for u in scene.world.units.values() if u.type is UnitType.AETHER_ELEMENTAL)
    scene.world.events.append(Event("expired", elemental.pos, player=scene.human, entity=elemental.id, text=elemental.type.value))
    game.tick(1 / 60)
    assert "aether_elemental_death" in scene.recent_sounds and not scene.bodies  # its body's own death, and no body left
