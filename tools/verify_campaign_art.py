"""Capture campaign buildings and hero motion through the real native renderer.

    uv run python tools/verify_campaign_art.py DIR

Writes building/hero catalogues, a native catalogue animation, all five Undertow
missions, real Issa movement and attacks, and a Weight destroyed and rebuilt with
ordinary World orders. Mission captures reveal the map for inspection and pause
the script between captures; these are presentation fixtures, not balance runs.
All saves, telemetry and profile data stay in a temporary directory. Keep the
display awake and run through the Saga verification slot.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

os.environ["SAGA2D_SILENT"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw  # noqa: E402

from saga2d import Game, Scene, fonts  # noqa: E402
from saga2d.testing.native_frames import tick  # noqa: E402
from warband.art import campaign_landmarks, campaign_units, textures  # noqa: E402
from warband.sim.model import Building, Point  # noqa: E402
from warband.sim.rules import BUILDINGS, SIM_DT, BuildingType as B, Difficulty, UnitType as U  # noqa: E402
from warband.story.campaign import Run  # noqa: E402
from warband.story.dialog import DialogScene  # noqa: E402
from warband.story.mission_scene import MissionScene, build_world  # noqa: E402
from warband.story.new_campaign import CAMPAIGN, RELIEF_SLUICE, WEIGHT_RIFTS  # noqa: E402
from warband.ui.style import build_theme  # noqa: E402

RESOLUTION = (1280, 800)
QUIET = {"tutorial": False, "music": 0.0, "sfx": 0.0, "edge_scroll": False,
         "campaign_speed": 1.0}
FORMS = ("pylon", "dam", "keystone", "vault", "root_vault", "refuge_tower", "sluice", "refuge", "rockfall")
HEROES = ("issa", "brakk", "wrenna", "dagna", "pell", "aldric", "maren")


class Catalogue(Scene):
    """Registered production images, rendered at logical size by the game backend."""

    background_color = (19, 29, 33, 255)

    def __init__(self, title: str, cards: list[tuple[str, str]], *, columns: int, zoom: float = 2.0) -> None:
        self.title, self.cards, self.columns, self.zoom = title, cards, columns, zoom

    def draw(self) -> None:
        self.draw_text("WARBAND / CAMPAIGN ART", 28, 30, font=fonts.EXTRABOLD, font_size=12,
                       color=(221, 183, 105, 255))
        self.draw_text(self.title, 28, 65, font=fonts.EXTRABOLD, font_size=25,
                       color=(238, 234, 214, 255))
        rows = math.ceil(len(self.cards) / self.columns)
        gap, margin, top = 12, 28, 96
        cell_w = (RESOLUTION[0] - 2 * margin - gap * (self.columns - 1)) / self.columns
        cell_h = (RESOLUTION[1] - top - 35 - gap * (rows - 1)) / rows
        for index, (key, label) in enumerate(self.cards):
            x = margin + index % self.columns * (cell_w + gap)
            y = top + index // self.columns * (cell_h + gap)
            self.draw_rect(x, y, cell_w, cell_h, (30, 44, 48, 255),
                           border_color=(71, 88, 89, 255), border_width=1, radius=6)
            width, height = textures.placements[key].size
            zoom = min(self.zoom, (cell_w - 16) / width, (cell_h - 40) / height)
            self.draw_image(key, x + (cell_w - width * zoom) / 2,
                            y + 6 + (cell_h - 40 - height * zoom) / 2, width * zoom, height * zoom)
            self.draw_text(label, x + cell_w / 2, y + cell_h - 15, anchor_x="center",
                           font_size=12, color=(238, 234, 214, 255))
        self.draw_text("Native renderer / registered game images / all eight facings exercised in animation", 28, 780,
                       font_size=11, color=(157, 177, 177, 255))


def frames(game: Game, count: int = 2, dt: float = 1 / 30) -> None:
    for _ in range(count):
        tick(game, dt)
        # Script dialogue must not cover the subject of an art inspection.
        while isinstance(game.scene, DialogScene):
            game.scene.skip()


def capture(game: Game, output: Path, name: str) -> Image.Image:
    frames(game)
    image = game.backend.capture_frame()
    image.save(output / f"{name}.png")
    print(f"  {name}.png", flush=True)
    return image


def save_gif(path: Path, images: list[Image.Image], *, duration: int = 100) -> None:
    images[0].save(path, save_all=True, append_images=images[1:], duration=duration, loop=0)
    print(f"  {path.name}", flush=True)


def gif_frame(game: Game) -> Image.Image:
    """Keep animations at logical resolution instead of storing Retina-sized frame sequences."""
    return game.backend.capture_frame().convert("RGB").resize((960, 600), Image.Resampling.LANCZOS)


def catalogues(game: Game, output: Path) -> None:
    footprints = {"keystone": BUILDINGS[B.MAGE_TOWER].size, "refuge_tower": BUILDINGS[B.MAGE_TOWER].size,
                  "refuge": 3}
    for state in ("active", "ruined"):
        cards = [(campaign_landmarks.register_image(game, form, state, footprints.get(form, 2), 1 if form in ("pylon", "dam") else 0),
                  form.replace("_", " ").title()) for form in FORMS]
        game.clear_and_push(Catalogue(f"Campaign structures / {state}", cards, columns=3))
        capture(game, output, f"01_structures_{state}")
    cards = [(campaign_units.unit_image(game, name, 1 if name == "pell" else 0, 2, frame),
              f"{name.title()} / {label}")
             for frame, label in (("stand", "rest"), ("walk1", "walk"), ("strike", "strike")) for name in HEROES]
    game.clear_and_push(Catalogue("Campaign cast / rest, movement, attack", cards, columns=7, zoom=2.8))
    capture(game, output, "02_heroes_poses")
    sheet = Catalogue("Campaign cast / eight directions and complete motion", [], columns=4, zoom=3.0)
    game.clear_and_push(sheet)
    images = []
    for facing in range(textures.FACINGS):
        for frame in textures.FRAMES:
            sheet.cards = [(campaign_units.unit_image(game, name, 1 if name == "pell" else 0, facing, frame),
                            f"{name.title()} / {frame} / {facing + 1}") for name in HEROES]
            frames(game, 1)
            images.append(gif_frame(game))
    save_gif(output / "02_heroes_motion.gif", images)


def hold_everyone(run: Run) -> None:
    for side in range(run.world.seats):
        ids = [unit.id for unit in run.units(side)]
        if ids:
            run.world.hold(ids)


def mission(game: Game, id: str) -> MissionScene:
    run = build_world(CAMPAIGN.mission(id), flags={})
    hold_everyone(run)
    run.world.reveal_all(0)
    scene = MissionScene(CAMPAIGN, run, difficulty=Difficulty.MEDIUM, settings=dict(QUIET))
    scene.execution.paused = True
    game.clear_and_push(scene)
    backend = game.backend
    backend.window.dispatch_event("on_mouse_motion", round(-100 * backend.scale_factor + backend.offset_x),
                                  round((RESOLUTION[1] + 100) * backend.scale_factor + backend.offset_y), 0, 0)
    frames(game, 18, .2)  # Let the chapter banner leave while the world remains still.
    return scene


def focus(game: Game, scene: MissionScene, point: Point, *, selection: int | None = None, zoom: float = 1.6) -> None:
    scene.run.tick()
    scene.run.looks.clear()  # This inspection owns the camera; script focus cues were already reached offscreen.
    scene.world.reveal_all(0)
    scene.open_catalogue(None)
    scene.select([] if selection is None else [selection], quiet=True)
    scene.camera.zoom = zoom
    scene.camera.center_on(point[0] * textures.TILE, point[1] * textures.TILE)
    if scene.execution.paused:
        # Offscreen World.step calls have no interpolation boundary; display their current positions exactly.
        scene.view.before_step()
    frames(game)


def building_at(run: Run, kind: B, pos: tuple[int, int]) -> Building:
    return next(building for building in run.world.buildings.values() if building.type is kind and building.pos == pos)


def simulate_until(run: Run, condition: Callable[[], bool], *, seconds: float, label: str) -> None:
    """Advance public simulation state offscreen; the scene presents the resulting genuine state."""
    for _ in range(math.ceil(seconds / SIM_DT)):
        if condition():
            return
        run.world.step()
    raise AssertionError(f"{label} did not happen within {seconds:g} simulation seconds")


def site_shots(game: Game, output: Path) -> None:
    for id, key, shots in (
        ("undertow_mill", "issa", (("mill_pylon", "mill_pylon"), ("mill_vault", "mill_vault"), ("mill_fields", "mill_fields"))),
        ("undertow_caravan", "brakk", (("dam", "dam_pylon"), ("old_camp", "old_camp"), ("mesa", "mesa"))),
        ("undertow_grove", "wrenna", (("moon_hall", "moon_hall"), ("firebreak", "firebreak"), ("ancient", "guardian_ring"))),
        ("undertow_weight", "dagna", (("weight", "weight_1"), ("seam", "seam"), ("seam_throat", "seam_rift"))),
        ("undertow_maw", "issa", (("keystone", "keystone"), ("seal_pylon", "seal_pylon_1"), ("refuge", "refuge_tower"))),
    ):
        scene = mission(game, id)
        hero = scene.run.unit(key)
        assert hero is not None
        focus(game, scene, hero.pos, selection=hero.id, zoom=1.1)
        capture(game, output, f"03_{id}_keeper")
        for name, landmark in shots:
            point = tuple(scene.run.vars["landmarks"][landmark]["point"])
            subject = scene.world.building_at((int(point[0]), int(point[1])))
            focus(game, scene, point, selection=subject.id if subject is not None else None)
            capture(game, output, f"04_{id}_{name}")
        if id == "undertow_mill":
            wounded = next(unit for unit in scene.run.soldiers(0) if unit.hp < unit.info.hp)
            focus(game, scene, wounded.pos, selection=wounded.id, zoom=1.8)
            capture(game, output, "04_undertow_mill_injured_outrider")
        elif id == "undertow_grove":
            lock = building_at(scene.run, B.VAULT, (23, 17))
            focus(game, scene, lock.center, selection=lock.id)
            capture(game, output, "04_undertow_grove_root_lock")
        elif id == "undertow_caravan":
            scout = scene.run.soldiers(0)[1]
            scene.world.move([scout.id], (28.5, 23.5))
            simulate_until(scene.run, lambda: scout.x >= 28, seconds=90, label="caravan reaches rockfall trigger")
            scene.run.tick()
            assert len(scene.run.get("rockfall")) == 2
            focus(game, scene, tuple(scene.run.get("middle_ford")))
            capture(game, output, "05_caravan_real_rockfall")
        elif id == "undertow_maw":
            focus(game, scene, RELIEF_SLUICE)
            capture(game, output, "04_undertow_maw_relief_sluice")


def hero_orders(game: Game, output: Path) -> dict[str, list[str]]:
    """Issa's live sprite must really enter walk and attack poses after ordinary orders."""
    scene = mission(game, "undertow_mill")
    run, world = scene.run, scene.world
    hero = run.unit("issa")
    assert hero is not None
    pylon = world.buildings[run.get("mill_pylon")]
    # The actual mission's knight walks to its actual objective. This is not a rig-only animation.
    world.move([hero.id], (24.0, 5.0))
    scene.execution.paused = False
    images, seen = [], {"walk": set(), "attack": set()}
    for _ in range(22):
        tick(game, 1 / 15)
        focus(game, scene, hero.pos, selection=hero.id, zoom=1.9)
        sprite = scene.view.unit_sprite(hero.id)
        assert sprite is not None and sprite.image.startswith("campaign.unit.issa.")
        frame = sprite.image.rsplit(".", 1)[-1]
        seen["walk"].add(frame)
        images.append(gif_frame(game))
    assert set(textures.WALK_FRAMES) & seen["walk"], seen
    scene.execution.paused = True
    simulate_until(run, lambda: math.dist(hero.pos, (24.0, 5.0)) < .65, seconds=90, label="Issa walks through the north ford")
    world.reveal_all(0)
    world.attack([hero.id], pylon.id)
    simulate_until(run, lambda: hero.state == "attack", seconds=12, label="Issa attacks pylon")
    scene.execution.paused = False
    for _ in range(36):
        tick(game, 1 / 30)
        focus(game, scene, (hero.x, hero.y - .7), selection=hero.id, zoom=2.0)
        sprite = scene.view.unit_sprite(hero.id)
        assert sprite is not None and sprite.image.startswith("campaign.unit.issa.")
        seen["attack"].add(sprite.image.rsplit(".", 1)[-1])
        images.append(gif_frame(game))
    scene.execution.paused = True
    assert set(textures.ATTACK_FRAMES) & seen["attack"], seen
    capture(game, output, "06_issa_attacks_pylon")
    save_gif(output / "06_issa_public_orders.gif", images, duration=67)
    # Keep a genuine beast alive so the story does not replace the scene with its result panel.
    beast = world.spawn_unit(1, U.WOLF, (40.5, 30.5))
    world.hold([beast.id])
    simulate_until(run, lambda: pylon.id not in world.buildings, seconds=120, label="pylon demolition")
    run.tick()
    world.move([hero.id], (21.5, 5.0))
    simulate_until(run, lambda: math.dist(hero.pos, pylon.center) > 3, seconds=8, label="Issa clears the pylon rubble")
    focus(game, scene, pylon.center)
    frames(game, 35, .2)  # Let the collapse cloud and its notices leave a readable final ruin.
    capture(game, output, "07_mill_pylon_destroyed")
    focus(game, scene, tuple(run.get("mill_vault_center")))
    capture(game, output, "07_mill_vault_shuttered")
    return {key: sorted(value) for key, value in seen.items()}


def weight_rebuild(game: Game, output: Path) -> None:
    """A campaign art binding survives real demolition and a new building id on the same rift."""
    scene = mission(game, "undertow_weight")
    run, world = scene.run, scene.world
    pos = WEIGHT_RIFTS[0]
    weight = building_at(run, B.VAULT, pos)
    focus(game, scene, weight.center, selection=weight.id)
    capture(game, output, "08_weight_standing")
    # Added siege troops are an explicit presentation fixture; damage still comes from normal attacks.
    attackers = run.spawn(1, [U.CATAPULT] * 3, (25.0, 10.5), hold=True)
    world.attack([unit.id for unit in attackers], weight.id)
    simulate_until(run, lambda: weight.id not in world.buildings, seconds=90, label="Weight demolition")
    world.move([unit.id for unit in attackers], (35.5, 5.5))
    simulate_until(run, lambda: all(math.dist(unit.pos, (35.5, 5.5)) < 2 for unit in attackers),
                   seconds=45, label="siege troops withdraw from the rebuild site")
    world.hold([unit.id for unit in attackers])
    focus(game, scene, weight.center)
    capture(game, output, "08_weight_destroyed")
    # A fallen Weight genuinely sheds an elemental on its rift. Move this fixture's occupants
    # aside through ordinary orders, just as the siege crew withdrew, before asking a worker to build.
    hold_everyone(run)
    blockers = [unit for unit in world.units.values() if not unit.hidden and not unit.flying
                and pos[0] - unit.radius < unit.x < pos[0] + 2 + unit.radius
                and pos[1] - unit.radius < unit.y < pos[1] + 2 + unit.radius]
    for unit in blockers:
        world.move([unit.id], (32.5, 9.5))
    if blockers:
        simulate_until(run, lambda: all(math.dist(unit.pos, (32.5, 9.5)) < 1.5 for unit in blockers),
                       seconds=45, label="rift occupants leave the rebuild footprint")
        for unit in blockers:
            world.hold([unit.id])
    builder = min(run.units(0, U.PEASANT), key=lambda unit: math.dist(unit.pos, weight.center))
    world.reveal_all(0)
    world.build(builder.id, B.VAULT, pos)
    simulate_until(run, lambda: any(building.type is B.VAULT and building.pos == pos and building.done
                                   for building in world.buildings.values()), seconds=120, label="Weight rebuilt by worker")
    rebuilt = building_at(run, B.VAULT, pos)
    assert rebuilt.id != weight.id
    focus(game, scene, rebuilt.center, selection=rebuilt.id)
    sprite = scene.view.building_sprite(rebuilt.id)
    assert sprite is not None and "campaign" in sprite.image, sprite
    frames(game, 35, .2)  # The completed-building banner should not hide the very body this proves.
    capture(game, output, "08_weight_rebuilt")


def overview(output: Path) -> None:
    paths = sorted(output.glob("0[34578]_*.png"))
    thumb_w, thumb_h, caption = 384, 240, 24
    columns, rows = 3, math.ceil(len(paths) / 3)
    sheet = Image.new("RGB", (columns * thumb_w, rows * (thumb_h + caption)), (20, 30, 33))
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        x, y = index % columns * thumb_w, index // columns * (thumb_h + caption)
        with Image.open(path) as image:
            sheet.paste(image.convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS), (x, y))
        draw.text((x + 5, y + thumb_h + 5), path.stem.removeprefix("04_").removeprefix("03_"), fill=(236, 230, 211))
    sheet.save(output / "09_mission_overview.jpg", quality=90)


def main(output: Path) -> None:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="warband-campaign-art-") as scratch:
        game = Game("Campaign art verification", resolution=RESOLUTION, backend="pyglet", visible=False,
                    save_dir=Path(scratch) / "saves", theme=build_theme())
        try:
            fonts.load(game)
            catalogues(game, output)
            site_shots(game, output)
            poses = hero_orders(game, output)
            weight_rebuild(game, output)
        finally:
            game.close()
    overview(output)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent.parent, text=True).strip()
    command = f"uv run python tools/verify_campaign_art.py {shlex.quote(str(output))}"
    (output / "verification.json").write_text(json.dumps({"source_commit": commit, "command": command,
                                                         "hero_frames_from_public_orders": poses,
                                                         "missions": [mission.id for mission in CAMPAIGN.missions]}, indent=2) + "\n")
    (output / "README.md").write_text(f"# Campaign art verification\n\nSource commit: `{commit}` (plus current working changes).\n\n"
                                      f"Reproduce: `{command}`\n\nNative registered catalogues and all five real Undertow scenes. "
                                      "Map visibility is revealed for inspection. Issa moves and attacks through public World orders; "
                                      "a Weight is attacked, destroyed and rebuilt by an ordinary worker, changing its entity id. "
                                      "The siege units used for the Weight are a presentation fixture.\n")
    print(f"Campaign art verification passed: {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path, help="explicit output directory for native verification evidence")
    main(parser.parse_args().out)
