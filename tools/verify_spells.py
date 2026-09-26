"""Render the Mage Tower and the spells through the real backend and save the frames to look at (WB-066).

    uv run python tools/verify_spells.py DIR

``towers.png``    the four races' Mage Towers side by side: Mage Tower, Spirit Lodge, Starwell Spire, Rune Tower.
``card.png``      the player's tower selected: three rows of spells, level I chosen (its two others closed), level II
                  being researched (its others closed while it is), level III open; the spell bar over the minimap.
``aim.png``       Wither aimed (Alt+2) within a vault's reach: its ring at the pointer, the reach washed violet, the price
                  at the plain rate; Haste on its cooldown, its sweep and seconds on its button.
``aim-far.png``   the same aimed beyond every vault's reach: the ring and the price in the warning ink, twice as dear,
                  and more than the one vault holds.
``aim-store.png`` the Meteor aimed beyond every vault's reach and clicked: 240 aether is more than the one vault holds,
                  and the aim and the refusal on the status line say so (within reach its 120 fits one vault's store).
``looks.png``     a unit under each condition the spells lay: haste (walking), mend, burn, stoneskin, entangled,
                  withered and battle fury, with the card of the entangled one.
``land.png``      Flame Strike and Wither landing on a rival's line: their bursts and rings.
``meteor.png``    a Meteor falling onto a rival's hall, its shadow grown on the ground and its ring.
``summon.png``    two Aether Elementals just summoned beside a rival's footmen and a rival's two, one of the player's
                  selected: its card counts the seconds before it is gone.
``bursts.png``    all nine spells landing at once, a level a row (the Meteor cast two seconds earlier): each spell's
                  burst and rings in its own ink.
``codex.png``     the codex's spells page.
``tree.png``      the codex's tech tree: the Mage Tower's spells by level beside it.

Real window events drive it, as ``tools/verify.py`` does.  The display must be awake (``caffeinate -u``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from saga2d import Game, fonts  # noqa: E402
from warband.sim.model import World, tile_center  # noqa: E402
from warband.sim.rules import AETHER_STORE, BUFFS, SPELL_FAR, SPELLS, BuildingType, Race, Terrain, UnitType, Upgrade  # noqa: E402
from warband.ui.scene import CodexScene, GameScene  # noqa: E402
from warband.ui.style import build_theme  # noqa: E402

RESOLUTION = (1280, 800)
RACES = (Race.HUMAN, Race.ORC, Race.ELF, Race.DWARF)
TOWERS = ((10, 5), (15, 5), (20, 5), (25, 5))
VAULT = (6, 14)  # on a rift, the player's: its reach covers the left of the field
LOOKS = ("haste", "mend", "burn", "stoneskin", "entangled", "withered", "battle_fury")


def staged() -> World:
    """Open grass: seat 0's hall, vault and tower, a tower of each rival race beside it, a line of the player's footmen to
    wear the conditions and a rival line to take the blows; every seat but the first silent (no brain)."""
    width, height = 48, 34
    terrain = [[Terrain.GRASS] * width for _ in range(height)]
    for y in range(1, 3):
        for x in range(4, 44):
            if (x * 7 + y * 3) % 5:
                terrain[y][x] = Terrain.TREES
    world = World(width, height, terrain, 4, races=list(RACES))
    for player in world.players[1:world.seats]:
        player.human = True  # silent: GameScene gives brains only to the seats that are not human
    world.place_building(0, BuildingType.TOWN_HALL, (2, 8))
    world.lay_rifts([VAULT])
    world.place_building(0, BuildingType.VAULT, VAULT)
    for seat, tower in enumerate(TOWERS):
        world.place_building(seat, BuildingType.MAGE_TOWER, tower)
    for seat, hall in ((1, (40, 24)), (2, (40, 8)), (3, (32, 28))):
        world.place_building(seat, BuildingType.TOWN_HALL, hall)
    player = world.players[0]
    player.upgrades |= {Upgrade.KEEP, Upgrade.HASTE, Upgrade.WITHER, Upgrade.METEOR}
    player.aether = 100
    player.gold = player.lumber = 5000
    world.update_vision()
    world.reveal_all(0)
    return world


def main(out: Path) -> None:
    from pyglet.window import key, mouse

    out.mkdir(parents=True, exist_ok=True)
    game = Game("Warband spells", resolution=RESOLUTION, backend="pyglet", visible=False, theme=build_theme())
    backend, window = game.backend, game.backend.window
    fonts.load(game)
    world = staged()
    scene = GameScene(world, 7, settings={"music": 0, "sfx": 0, "tutorial": False, "edge_scroll": False}, ranked=False)
    game.push(scene)

    def frames(n: int) -> None:
        for _ in range(n):
            game.tick(1 / 60)

    def physical(point) -> tuple[int, int]:
        sx, sy = scene.camera.world_to_screen(point[0] * 32, point[1] * 32)
        s = backend.scale_factor
        return int(sx * s + backend.offset_x), int((RESOLUTION[1] - sy) * s + backend.offset_y)

    def point_at(point) -> None:
        window.dispatch_event("on_mouse_motion", *physical(point), 0, 0)
        frames(3)

    def click(point, button: int = mouse.LEFT) -> None:
        px, py = physical(point)
        window.dispatch_event("on_mouse_press", px, py, button, 0)
        window.dispatch_event("on_mouse_release", px, py, button, 0)
        frames(2)

    def press(symbol: int, modifiers: int = 0) -> None:
        window.dispatch_event("on_key_press", symbol, modifiers)
        window.dispatch_event("on_key_release", symbol, modifiers)
        frames(2)

    def shot(name: str) -> None:
        frames(2)
        backend.capture_frame().save(out / f"{name}.png")
        print(f"  {name}.png")

    def look_at(point, zoom: float, settle: int = 20) -> None:
        scene.camera.zoom = zoom
        scene.camera.center_on(point[0] * 32, point[1] * 32)
        frames(settle)

    frames(200)  # past the opening banner

    look_at((19.5, 7.0), 1.8)
    shot("towers")

    # The card: level I chosen as Haste, Stoneskin being researched (Entangle and Wither wait on it), level III open.
    tower = next(b for b in world.player_buildings(0, BuildingType.MAGE_TOWER))
    world.players[0].upgrades.discard(Upgrade.WITHER)
    world.players[0].upgrades.discard(Upgrade.METEOR)
    world.research(tower.id, Upgrade.STONESKIN)
    click(tower.center)
    assert scene.selection == [tower.id], scene.selection
    look_at((14.0, 10.0), 1.2)
    point_at((30.0, 30.0))
    shot("card")
    world.cancel_research(tower.id)
    world.players[0].upgrades |= {Upgrade.WITHER, Upgrade.METEOR}
    press(key.ESCAPE)

    # Aiming: Haste cast and cooling; the bar holds Haste, Wither and Meteor.
    world.cast(0, Upgrade.HASTE, (8.5, 20.5))
    frames(90)
    press(key._2, key.MOD_ALT)
    assert scene.aiming is Upgrade.WITHER, scene.pending
    look_at((12.0, 18.0), 1.0)
    point_at((12.0, 22.0))
    shot("aim")
    point_at((24.0, 24.0))
    shot("aim-far")
    press(key._3, key.MOD_ALT)
    assert scene.aiming is Upgrade.METEOR, scene.pending
    click((24.0, 24.0))
    assert scene.status == (f"Not enough aether ({SPELLS[Upgrade.METEOR].aether * SPELL_FAR} needed, {SPELL_FAR}x beyond your vaults' "
                            f"reach): they hold {AETHER_STORE}, cast it within their reach or build another"), scene.status
    point_at((24.0, 24.0))
    shot("aim-store")
    press(key.ESCAPE)
    point_at((30.0, 30.0))  # off where the nine spells' bar will stand, whose tooltip would cover the bursts

    # Each condition on a footman of the player's, one to a kind, in a row; the hasted one walks.
    row = [world.spawn_unit(0, UnitType.FOOTMAN, tile_center((10 + 2 * i, 26))) for i in range(len(LOOKS))]
    for unit, kind in zip(row, LOOKS):
        world._lay(unit, BUFFS[kind], 0)  # staging: each look alone, without the spell's other effects
    world.move([row[0].id], (10.5, 30.5))
    look_at((16.0, 26.5), 2.0, settle=12)
    click(row[4].pos)
    shot("looks")
    press(key.ESCAPE)

    # A rival's line takes a Wither, then (the store refilled) a Meteor on its hall.
    foes = [world.spawn_unit(1, UnitType.FOOTMAN, tile_center((36 + i % 3, 18 + i // 3))) for i in range(6)]
    world.hold([u.id for u in foes])
    eyes = world.spawn_unit(0, UnitType.FLYING_MACHINE, (38.5, 22.5))  # the player sees the rival's line and hall
    world.hold([eyes.id])
    world.update_vision()
    world.players[0].aether = 1000
    look_at((37.0, 19.0), 1.6, settle=4)
    world.cast(0, Upgrade.WITHER, (37.0, 18.5))
    frames(8)
    shot("land")
    world.cast(0, Upgrade.METEOR, (41.5, 25.5))
    look_at((40.0, 23.5), 1.4, settle=4)
    frames(66)  # most of its two seconds: the shadow grown, the rock low
    shot("meteor")
    frames(60)

    world.players[0].upgrades.discard(Upgrade.METEOR)
    world.players[0].upgrades.add(Upgrade.SUMMON)
    world.cast(0, Upgrade.SUMMON, (34.5, 20.5))
    world.players[1].upgrades.add(Upgrade.SUMMON)
    world.players[1].aether = 1000
    world.cast(1, Upgrade.SUMMON, (37.5, 21.5))  # the rival's own: whose is whose, in one melee
    look_at((35.5, 20.5), 2.0, settle=30)
    mine = next(u for u in world.units.values() if u.type is UnitType.AETHER_ELEMENTAL and u.player == 0)
    click(mine.pos)
    assert scene.selection == [mine.id], scene.selection
    shot("summon")
    press(key.ESCAPE)

    # All nine landing together, the Meteor called down two seconds before the rest.
    world.players[0].upgrades |= set(SPELLS)
    world.players[0].aether = 5000
    spots = {spell: (28.0 + 8.0 * (i % 3), 14.0 + 7.0 * (i // 3)) for i, spell in enumerate(SPELLS)}  # right of the spell bar
    world.players[0].cooldowns.clear()
    world.cast(0, Upgrade.METEOR, spots[Upgrade.METEOR])
    frames(118)
    for spell, spot in spots.items():
        if spell is not Upgrade.METEOR:
            world.players[0].cooldowns.clear()
            world.cast(0, spell, spot)
    scene.view.set_reveal(True)
    look_at((24.0, 20.0), 0.75, settle=6)
    shot("bursts")
    scene.view.set_reveal(False)

    game.push(CodexScene(world, 0, 5))
    frames(4)
    shot("codex")
    game.pop()
    game.push(CodexScene(world, 0, 4))
    frames(4)
    shot("tree")
    game.pop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    main(parser.parse_args().out)
