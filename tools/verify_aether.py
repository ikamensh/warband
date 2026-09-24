"""Render the aether economy through the real backend and save the frames to look at (WB-063).

    uv run python tools/verify_aether.py DIR

``rift.png``       an open ley rift streaming motes, beside a vault drawing from another, near.
``vaults.png``     the four races' vaults, each set square on a rift and drawing: Arcane Vault, Spirit Cage,
                   Moon Reliquary, Rune Vault.
``reach.png``      the player's vault selected: its card (what it draws, whether it stands on a rift), the aether
                   figure beside gold and lumber, and the violet wash of its reach.
``placing.png``    a peasant placing a vault: the rifts it knows lit, the site snapped square onto the rift under the
                   pointer, and the hint saying it will draw.
``placing-off.png`` the same with the pointer away from every rift: the hint says the vault would not draw.
``full.png``       the player's store full: its vault dim and no motes, a rival's still drawn drawing.

Real window events drive it, as ``tools/verify.py`` does.  The display must be awake (``caffeinate -u``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from saga2d import Game, fonts  # noqa: E402
from warband.sim.model import World, tile_center  # noqa: E402
from warband.sim.rules import BuildingType, Race, Terrain, UnitType  # noqa: E402
from warband.ui.scene import GameScene  # noqa: E402
from warband.ui.style import build_theme  # noqa: E402

RESOLUTION = (1280, 800)
RACES = (Race.HUMAN, Race.ORC, Race.ELF, Race.DWARF)
#: A vault for each race, on the rifts in a row in front of seat 0's hall; two rifts left open.
VAULT_RIFTS = ((12, 14), (17, 14), (22, 14), (27, 14))
OPEN_RIFTS = ((12, 20), (22, 20))


def staged() -> World:
    """Open grass with a wood to the north: seat 0's hall and a peasant, four seats each owning a vault on a rift, and
    every seat but the first silent (no brain), so nothing moves but what the frames stage."""
    width, height = 44, 32
    terrain = [[Terrain.GRASS] * width for _ in range(height)]
    for y in range(1, 5):
        for x in range(4, 40):
            if (x * 7 + y * 3) % 5:
                terrain[y][x] = Terrain.TREES
    world = World(width, height, terrain, 4, races=list(RACES))
    for player in world.players[1:world.seats]:
        player.human = True  # silent: GameScene gives brains only to the seats that are not human
    world.place_building(0, BuildingType.TOWN_HALL, (5, 8))
    world.lay_rifts(VAULT_RIFTS + OPEN_RIFTS)
    for seat, rift in enumerate(VAULT_RIFTS):
        world.place_building(seat, BuildingType.VAULT, rift)
    for seat, hall in ((1, (37, 9)), (2, (37, 20)), (3, (30, 26))):  # each rival holds a hall, or its vault alone is laid bare
        world.place_building(seat, BuildingType.TOWN_HALL, hall)
    peasant = world.spawn_unit(0, UnitType.PEASANT, tile_center((10, 23)))
    world.hold([peasant.id])  # parked by the rift it lights, rather than sent to the woods by the worker policy
    watch = [world.spawn_unit(0, UnitType.FOOTMAN, tile_center(tile)).id for tile in ((24, 23), (24, 17))]  # eyes on the rest
    world.hold(watch)
    world.players[0].aether = 37
    world.update_vision()
    world.reveal_all(0)
    return world


def main(out: Path) -> None:
    from pyglet.window import key, mouse

    out.mkdir(parents=True, exist_ok=True)
    game = Game("Warband aether", resolution=RESOLUTION, backend="pyglet", visible=False, theme=build_theme())
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

    def press(symbol: int) -> None:
        window.dispatch_event("on_key_press", symbol, 0)
        window.dispatch_event("on_key_release", symbol, 0)
        frames(2)

    def shot(name: str) -> None:
        frames(2)
        backend.capture_frame().save(out / f"{name}.png")
        print(f"  {name}.png")

    def look_at(point, zoom: float) -> None:
        scene.camera.zoom = zoom
        scene.camera.center_on(point[0] * 32, point[1] * 32)
        frames(40)  # the banner fades and the motes rise

    frames(200)  # past the opening banner
    assert all(world.taps(b) for b in world.buildings.values() if b.type is BuildingType.VAULT)

    look_at((15.0, 18.5), 2.0)
    point_at((3.0, 28.0))
    shot("rift")

    look_at((20.0, 16.0), 1.4)
    shot("vaults")

    vault = next(b for b in world.player_buildings(0, BuildingType.VAULT))
    click(vault.center)
    assert scene.selection == [vault.id] and scene.reach_shown() == [vault.center], scene.selection
    look_at((16.0, 16.0), 1.0)
    point_at((30.0, 28.0))
    shot("reach")

    peasant = next(u for u in world.player_units(0) if u.is_worker)
    click(peasant.pos)
    press(key.B)
    press(key.V)
    assert scene.placing is BuildingType.VAULT
    look_at((17.0, 18.0), 1.4)
    point_at((OPEN_RIFTS[0][0] + 0.2, OPEN_RIFTS[0][1] + 2.4))  # beside the rift, not on it: the site snaps
    ghost = scene.ghost()
    assert ghost is not None and ghost[1] == OPEN_RIFTS[0] and ghost[2], ghost
    shot("placing")
    point_at((7.0, 17.0))
    assert scene.rift_near(scene.hover) is None and scene.ghost() is not None
    shot("placing-off")
    press(key.ESCAPE)
    press(key.ESCAPE)

    world.players[0].aether = world.aether_cap(0)
    look_at((20.0, 16.0), 1.4)
    shot("full")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    main(parser.parse_args().out)
