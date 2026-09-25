"""From the title screen to a player's first spell, through real window events: can a player find the spells (WB-066)?

    uv run python tools/verify_first_spell.py DIR

A fresh profile starts a match the way a player does (New game, Start: the tutorial on), and each step is taken
through the HUD, saving a frame to look at:

``build-before-vault.png``  a peasant's Build card: the Mage Tower greyed with its padlock, its tooltip saying what it
                            researches and "Requires" the vault.
``build-after-vault.png``   the vault built through the card (its key twice: the planner puts it on the known rift):
                            the tower buildable, its price in the card's ink.
``tower-card.png``          the tower built and selected: level I's three spells offered, Haste's tooltip.
``spell-bar.png``           Haste researched: the spell bar over the minimap with its key and price.
``aim.png``                 Alt+1: the aim's ring and price at the pointer, the vault's reach washed violet.
``help.png``, ``codex.png`` How to play (F1) and the codex's Spells page (F2, 6).

The purse is topped up once the vault is ordered, so nothing waits for money; time runs in tenths of a second between
the steps.  The display must be awake (``caffeinate -u -d``).
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from saga2d import Game, fonts  # noqa: E402
from warband.sim.rules import BuildingType, Upgrade  # noqa: E402
from warband.ui.scene import DEFAULT_SETTINGS, GameScene  # noqa: E402
from warband.ui.style import build_theme  # noqa: E402
from warband.ui.title import TitleScene  # noqa: E402

RESOLUTION = (1280, 800)


def main(out: Path) -> None:
    from pyglet.window import key, mouse

    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="first-spell-") as profile:
        game = Game("Warband", resolution=RESOLUTION, backend="pyglet", visible=False, theme=build_theme(),
                    save_dir=Path(profile) / "saves")
        try:
            walk(game, out, key, mouse)
        finally:
            game.close()


def walk(game: Game, out: Path, key, mouse) -> None:
    backend, window = game.backend, game.backend.window
    fonts.load(game)
    settings = game.settings(DEFAULT_SETTINGS)
    settings["music"] = settings["sfx"] = 0
    game.push(TitleScene(settings=settings))

    def frames(n: int) -> None:
        for _ in range(n):
            game.tick(1 / 60)

    def run(seconds: float, until) -> None:
        for _ in range(int(seconds * 10)):
            game.tick(0.1)
            if until():
                return
        raise AssertionError(f"not within {seconds} s")

    def press(symbol: int, mods: int = 0) -> None:
        window.dispatch_event("on_key_press", symbol, mods)
        window.dispatch_event("on_key_release", symbol, mods)
        frames(3)

    def letter(ch: str) -> None:
        press(getattr(key, ch.upper()))

    def physical(x: float, y: float) -> tuple[int, int]:
        s = backend.scale_factor
        return int(x * s + backend.offset_x), int((RESOLUTION[1] - y) * s + backend.offset_y)

    def move(x: float, y: float) -> None:
        window.dispatch_event("on_mouse_motion", *physical(x, y), 0, 0)
        frames(3)

    def click(x: float, y: float) -> None:
        px, py = physical(x, y)
        window.dispatch_event("on_mouse_motion", px, py, 0, 0)
        window.dispatch_event("on_mouse_press", px, py, mouse.LEFT, 0)
        window.dispatch_event("on_mouse_release", px, py, mouse.LEFT, 0)
        frames(3)

    def on_screen(point) -> tuple[float, float]:
        return scene.camera.world_to_screen(point[0] * 32, point[1] * 32)

    def look_at(point) -> None:
        scene.camera.center_on(point[0] * 32, point[1] * 32)
        frames(2)

    def shot(name: str) -> None:
        frames(2)
        backend.capture_frame().save(out / f"{name}.png")
        print(f"  {name}.png")

    def card(target):
        """The card's command for *target* and its button."""
        for command, button in zip(scene.card, scene.card_buttons):
            if command.target == target:
                return command, button
        raise AssertionError(f"{target} is not on the card: {[c.target for c in scene.card]}")

    def hover(button) -> None:
        x, y, w, h = button.bounds
        move(x + w / 2, y + h / 2)

    def select_peasant(near) -> None:
        """Click the peasant nearest *near* that is out on the map (they start inside the hall and walk into the mine)."""
        for _ in range(40):
            out_there = [u for u in world.player_units(me) if u.is_worker and u.inside is None]
            if out_there:
                peasant = min(out_there, key=lambda u: abs(u.x - near[0]) + abs(u.y - near[1]))
                look_at(peasant.pos)
                click(*on_screen(peasant.pos))
                if scene.selection == [peasant.id]:
                    return
                press(key.ESCAPE)
            frames(10)
        raise AssertionError(f"no peasant could be selected: {scene.selection}")

    def open_build() -> None:
        letter(next(c for c in scene.card if c.label.lower().startswith("build")).hotkey)

    frames(10)
    press(key.N)  # New game
    press(key.RETURN)  # Start
    scene = game.scene
    assert isinstance(scene, GameScene), scene
    frames(240)  # past the opening banner
    world, me = scene.world, scene.human
    hall = world.player_buildings(me, BuildingType.TOWN_HALL)[0]

    select_peasant(hall.center)
    open_build()
    command, button = card(BuildingType.MAGE_TOWER)
    hover(button)
    assert "Requires" in scene.tooltip, scene.tooltip
    shot("build-before-vault")

    command, _button = card(BuildingType.VAULT)
    letter(command.hotkey)
    letter(command.hotkey)  # its key again: the planner puts it on the known rift
    scene.player.gold += 4000
    scene.player.lumber += 2000
    run(120, lambda: bool(world.player_buildings(me, BuildingType.VAULT, done=True)))
    vault = world.player_buildings(me, BuildingType.VAULT, done=True)[0]
    press(key.ESCAPE)
    press(key.ESCAPE)
    select_peasant(vault.center)
    open_build()
    command, button = card(BuildingType.MAGE_TOWER)
    hover(button)
    assert "Requires" not in scene.tooltip, scene.tooltip
    shot("build-after-vault")

    letter(command.hotkey)
    letter(command.hotkey)
    run(180, lambda: bool(world.player_buildings(me, BuildingType.MAGE_TOWER, done=True)))
    tower = world.player_buildings(me, BuildingType.MAGE_TOWER, done=True)[0]
    press(key.ESCAPE)
    press(key.ESCAPE)
    look_at(tower.center)
    click(*on_screen(tower.center))
    assert scene.selection == [tower.id], scene.selection
    command, button = card(Upgrade.HASTE)
    hover(button)
    shot("tower-card")

    letter(command.hotkey)
    run(120, lambda: Upgrade.HASTE in scene.player.upgrades)
    run(30, lambda: scene.player.aether >= 30)
    shot("spell-bar")
    press(key._1, key.MOD_ALT)
    assert scene.aiming is Upgrade.HASTE, scene.aiming
    move(*on_screen((vault.center[0] + 3, vault.center[1] + 2)))
    shot("aim")
    press(key.ESCAPE)

    press(key.F1)
    shot("help")
    press(key.ESCAPE)
    press(key.F2)
    press(key._6)
    shot("codex")
    press(key.ESCAPE)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path, help="directory for the frames")
    main(parser.parse_args().out)
