"""The campaign: missions with a plot, objectives and dialogue, and the progress that outlives any one version of the game.

Two kinds of state, kept apart on purpose:

* **Progress** (:class:`Progress`, ``~/.warband/campaign/save_1.json`` through :class:`ProgressStore`): which missions
  are done, the choices made, the difficulty.  A few hundred bytes of stable ids and JSON values.  Unknown keys and
  unknown mission ids are carried along untouched, missing keys take their defaults, and only a *newer* format is
  refused, so a player keeps their place across versions of Warband in both directions.
* **The mission in play**: an ordinary match save (slot ``campaign``) with a ``mission`` block: the mission's id, the
  triggers that have fired, the objectives' states and the mission's variables.  It depends on the world format like
  any save; when it cannot be read the campaign offers that mission again from its briefing, and nothing before it
  is lost.  New graphics never touch either file: art is looked up by race and unit type at draw time.

Content (speakers, lines, choices, objectives, triggers, map setup) is code in :mod:`warband.story.missions`, referenced
by id from both files.  :class:`Run` is one mission in play: the scene asks it to :meth:`Run.tick` after the
simulation advances and then shows the dialogues, toasts and camera cues it queued.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from saga2d import SaveError, SaveManager
from warband.sim.model import Building, Point, Pos, Unit, World, dist, rects_gap, tile_center
from warband.sim.rules import BUILDINGS, BuildingType, Difficulty, Layout, MapTheme, Race, Terrain, UnitType

FORMAT = 1  # of the progress file; bump only when an older Warband could misread a newer file
MINE_CLEARANCE = 2


# -- Story ---------------------------------------------------------------------


@dataclass(frozen=True)
class Speaker:
    """Who talks: the name shown, and the race and unit whose portrait stands beside the words."""

    name: str
    race: Race
    subject: UnitType | BuildingType
    player: int = 0  # whose colours the portrait wears


@dataclass(frozen=True)
class Line:
    """One thing said.  ``speaker`` is a :class:`Speaker` name, or empty for narration.  ``when`` and ``unless`` name
    variables (a mission's, or a flag from an earlier mission) that decide whether the line is spoken at all."""

    speaker: str
    text: str
    when: str | None = None
    unless: str | None = None

    def spoken(self, vars: dict[str, Any]) -> bool:
        return (self.when is None or bool(vars.get(self.when))) and (self.unless is None or not vars.get(self.unless))


@dataclass(frozen=True)
class Option:
    label: str
    value: Any  # stored under the choice's key; a boolean keeps ``when``/``unless`` on later lines simple


@dataclass(frozen=True)
class Choice:
    """A question with a few answers; the answer is stored under ``key`` in the mission's variables, and the mission
    remembers it into the campaign's flags when :attr:`Mission.remember` names it."""

    key: str
    speaker: str
    prompt: str
    options: tuple[Option, ...]


Item = Line | Choice
Dialog = tuple[Item, ...]


# -- Mission definition ----------------------------------------------------------


@dataclass(frozen=True)
class Objective:
    """A line of the objectives panel.  ``done`` and ``failed`` read the run; ``shown`` hides the line until it holds
    (then it stays).  A failed objective loses the mission.  An optional one is never required to win: a second way
    to win that the mission's ``win`` counts, or a condition that only matters by failing (``done`` never true)."""

    id: str
    text: str
    done: Callable[[Run], bool]
    failed: Callable[[Run], bool] | None = None
    shown: Callable[[Run], bool] | None = None
    optional: bool = False


@dataclass(frozen=True)
class Trigger:
    """Fires once, when ``when`` first holds after the previous frame's triggers: spawns, dialogue, cues."""

    id: str
    when: Callable[[Run], bool]
    do: Callable[[Run], None]


@dataclass(frozen=True)
class Side:
    """A player of the mission: sides[0] is the human.  ``ai`` is the brain's base difficulty, shifted by the campaign's;
    ``None`` is a scripted side that only the triggers move."""

    name: str
    race: Race
    ai: Difficulty | None = None


@dataclass(frozen=True)
class Mission:
    id: str  # stable: progress files and mission saves refer to it
    title: str
    act: str
    sides: tuple[Side, ...]
    size: str  # a key of mapgen.SIZES
    theme: MapTheme
    layout: Layout  # always named: a layout drawn from the seed would put the setup's camps in a river or a rock ring
    seed: int
    briefing: Dialog
    debrief: Dialog
    setup: Callable[[Run], None]  # reshapes the generated map: bases, bands, camps, variables
    objectives: tuple[Objective, ...]
    triggers: tuple[Trigger, ...] = ()
    win: Callable[[Run], bool] | None = None  # default: every required objective done
    remember: tuple[str, ...] = ()  # variables copied into the campaign's flags on completion

    def won(self, run: Run) -> bool:
        """The mission's own rule, else every required objective on the panel is done."""
        if self.win is not None:
            return self.win(run)
        required = [o for o in self.objectives if not o.optional and run.state.get(o.id) != "hidden"]
        return bool(required) and all(run.state[o.id] == "done" for o in required)


@dataclass(frozen=True)
class Campaign:
    id: str
    title: str
    tagline: str
    speakers: dict[str, Speaker]
    missions: tuple[Mission, ...]
    epilogue: Dialog

    def mission(self, mission_id: str) -> Mission:
        for mission in self.missions:
            if mission.id == mission_id:
                return mission
        raise KeyError(f"no mission {mission_id!r} in the {self.title} campaign")

    def index(self, mission: Mission) -> int:
        return self.missions.index(mission) + 1


_ORDER = (Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD, Difficulty.MASTER)
_SHIFT = {Difficulty.EASY: -1, Difficulty.MEDIUM: 0, Difficulty.HARD: 1}  # the campaign's own setting: Master is only ever a shift


def shifted(base: Difficulty, campaign: Difficulty) -> Difficulty:
    """A side's brain difficulty: the mission's base level, one step easier or harder with the campaign's setting."""
    return _ORDER[max(0, min(len(_ORDER) - 1, _ORDER.index(base) + _SHIFT[campaign]))]


# -- Predicates for missions ----------------------------------------------------------


def at(seconds: float) -> Callable[[Run], bool]:
    return lambda run: run.time >= seconds


def after(trigger_id: str, seconds: float) -> Callable[[Run], bool]:
    """*seconds* after the trigger fired."""
    return lambda run: trigger_id in run.fired and run.time - run.fired[trigger_id] >= seconds


def var(key: str, value: Any = True) -> Callable[[Run], bool]:
    return lambda run: key in run.vars and run.vars[key] == value


def objective_done(objective_id: str) -> Callable[[Run], bool]:
    return lambda run: run.state.get(objective_id) == "done"


def side_out(side: int) -> Callable[[Run], bool]:
    """The side has been eliminated, surrendered, or was never put on the map."""
    return lambda run: not run.world.players[side].alive


def any_of(*predicates: Callable[[Run], bool]) -> Callable[[Run], bool]:
    return lambda run: any(p(run) for p in predicates)


def all_of(*predicates: Callable[[Run], bool]) -> Callable[[Run], bool]:
    return lambda run: all(p(run) for p in predicates)


# -- A mission in play ----------------------------------------------------------------


class Run:
    """The world, the mission's variables, what has fired and what the objectives say, and the queue of things the
    scene should show.  ``vars`` starts as a copy of the campaign's flags, less the mission's own remembered keys, so
    lines and triggers read past choices and a replayed mission asks its own question again."""

    def __init__(self, mission: Mission, world: World, *, flags: dict[str, Any]) -> None:
        self.mission = mission
        self.world = world
        self.human = 0
        self.vars: dict[str, Any] = {key: value for key, value in flags.items() if key not in mission.remember}  # own choices are made afresh
        self.ai: dict[int, Difficulty] = {i: side.ai for i, side in enumerate(mission.sides) if side.ai is not None}  # base levels; setup may change them
        self.fired: dict[str, float] = {}  # trigger id -> simulation time it fired
        self.state: dict[str, str] = {o.id: "hidden" if o.shown is not None else "open" for o in mission.objectives}
        self.pending: list[Dialog] = []  # dialogues to show, oldest first
        self.notes: list[tuple[str, list[str]]] = []  # toasts: title and lines
        self.looks: list[Point] = []  # points to pan the camera to and ping on the minimap
        self.completed: list[str] = []  # objectives finished this frame, for the scene to celebrate
        self.won = False
        self.lost: str | None = None

    # -- Reading ------------------------------------------------------------------

    @property
    def time(self) -> float:
        return self.world.time

    def get(self, key: str, default: Any = None) -> Any:
        return self.vars.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.vars[key] = value

    def units(self, side: int, unit_type: UnitType | None = None) -> list[Unit]:
        return [u for u in self.world.player_units(side) if unit_type is None or u.type is unit_type]

    def soldiers(self, side: int) -> list[Unit]:
        return [u for u in self.world.player_units(side) if not u.is_worker]

    def buildings(self, side: int, building_type: BuildingType | None = None, *, done: bool | None = True) -> list[Building]:
        return self.world.player_buildings(side, building_type, done=done)

    def hall(self, side: int) -> Building | None:
        halls = self.world.player_buildings(side, BuildingType.TOWN_HALL)
        return halls[0] if halls else None

    def home(self, side: int) -> Point:
        """Where the side's forces should aim: its hall, else any building, else its first unit, else the map's middle."""
        hall = self.hall(side)
        if hall is not None:
            return hall.center
        buildings = self.world.player_buildings(side)
        if buildings:
            return buildings[0].center
        units = self.world.player_units(side)
        if units:
            return units[0].pos
        return (self.world.width / 2, self.world.height / 2)

    def unit(self, key: str) -> Unit | None:
        """The unit whose id a variable holds, while it lives."""
        unit_id = self.vars.get(key)
        return self.world.units.get(unit_id) if isinstance(unit_id, int) else None

    def near(self, key: str, point: Point, within: float) -> bool:
        unit = self.unit(key)
        return unit is not None and dist(unit.pos, point) <= within

    # -- Telling the scene ----------------------------------------------------------

    def say(self, *items: Item) -> None:
        self.pending.append(tuple(items))

    def toast(self, title: str, *lines: str) -> None:
        self.notes.append((title, list(lines)))

    def look(self, point: Point) -> None:
        self.looks.append(point)

    # -- Shaping the map ------------------------------------------------------------

    def free_tiles(self, around: Point, count: int, *, radius: int = 8) -> list[Pos]:
        """Up to *count* passable tiles nobody stands on, nearest *around* first."""
        cx, cy = int(around[0]), int(around[1])
        found: list[Pos] = []
        for ring in range(radius + 1):
            candidates = [(cx + dx, cy + dy) for dx in range(-ring, ring + 1) for dy in range(-ring, ring + 1)
                          if max(abs(dx), abs(dy)) == ring]
            candidates.sort(key=lambda p: dist(tile_center(p), around))
            for tile in candidates:
                if self.world.passable(*tile) and self.world.unit_at(tile_center(tile), 0.5) is None:
                    found.append(tile)
                    if len(found) == count:
                        return found
        return found

    def spawn(self, side: int, units: list[UnitType], around: Point, *, attack: Point | None = None, hold: bool = False) -> list[Unit]:
        """Put a band on the map around a point; send it at *attack*, or have it hold its ground."""
        tiles = self.free_tiles(around, len(units))
        if len(tiles) < len(units):
            raise RuntimeError(f"no room for {len(units)} units around {around} in mission {self.mission.id}")
        band = [self.world.spawn_unit(side, unit_type, tile_center(tile)) for unit_type, tile in zip(units, tiles)]
        ids = [u.id for u in band]
        if attack is not None:
            self.world.attack_move(ids, attack)
        elif hold:
            self.world.hold(ids)
        self.world.update_vision()
        return band

    def footprint_free(self, building_type: BuildingType, pos: Pos) -> bool:
        """Open ground, nothing built or standing there, and the mine clearance kept; exploration does not matter."""
        world = self.world
        size = BUILDINGS[building_type].size
        for dy in range(size):
            for dx in range(size):
                tile = (pos[0] + dx, pos[1] + dy)
                if not world.in_bounds(tile) or world.terrain_at(tile) is not Terrain.GRASS or not world.passable(*tile):
                    return False
        if any(pos[0] - u.radius < u.x < pos[0] + size + u.radius and pos[1] - u.radius < u.y < pos[1] + size + u.radius
               for u in world.units.values() if not u.hidden):
            return False
        return all(rects_gap((pos[0], pos[1], size, size), mine.rect) >= MINE_CLEARANCE for mine in world.mines())

    def place(self, side: int | None, building_type: BuildingType, around: Point, *, radius: int = 10, done: bool = True) -> Building:
        """A finished building on the nearest free footprint to *around*.  Raises when there is no room: a mission
        that does not fit its map is a bug, not a quieter mission."""
        size = BUILDINGS[building_type].size
        cx, cy = int(around[0]) - size // 2, int(around[1]) - size // 2
        for ring in range(radius + 1):
            candidates = [(cx + dx, cy + dy) for dx in range(-ring, ring + 1) for dy in range(-ring, ring + 1)
                          if max(abs(dx), abs(dy)) == ring]
            candidates.sort(key=lambda p: dist((p[0] + size / 2, p[1] + size / 2), around))
            for pos in candidates:
                if self.footprint_free(building_type, pos):
                    building = self.world.place_building(side, building_type, pos, done=done)
                    if BUILDINGS[building_type].mine is None:  # World.place_building fills a deposit itself
                        self.world.players[side].alive = True  # a side cleared by the setup is back with its first holding
                    self.world.update_vision()
                    return building
        raise RuntimeError(f"no room for a {building_type.value} within {radius} tiles of {around} in mission {self.mission.id}")

    def replace(self, building: Building, side: int | None, building_type: BuildingType) -> Building:
        """Another building of the same size where *building* stands: a camp where a hall was drawn."""
        if BUILDINGS[building_type].size != building.size:
            raise ValueError(f"a {building_type.value} is not the size of a {building.type.value}")
        world = self.world
        del world.buildings[building.id]
        world._set_blocked(building, False)
        placed = world.place_building(side, building_type, building.pos)
        world.update_vision()
        return placed

    # -- Each frame ------------------------------------------------------------------

    def tick(self) -> None:
        """Fire due triggers, settle the objectives, decide the mission.  Called after the simulation advanced."""
        for trigger in self.mission.triggers:
            if trigger.id not in self.fired and trigger.when(self):
                self.fired[trigger.id] = self.time
                trigger.do(self)
        for objective in self.mission.objectives:
            state = self.state[objective.id]
            if state == "hidden":
                if objective.shown is not None and objective.shown(self):
                    self.state[objective.id] = state = "open"
                else:
                    continue
            if state != "open":
                continue
            if objective.failed is not None and objective.failed(self):
                self.state[objective.id] = "failed"
                if self.lost is None:
                    self.lost = objective.text
            elif objective.done(self):
                self.state[objective.id] = "done"
                self.completed.append(objective.id)
        if not self.won and self.lost is None and self.mission.won(self):
            self.won = True

    # -- Saving -----------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.mission.id, "vars": dict(self.vars), "fired": dict(self.fired), "state": dict(self.state),
                "ai": {str(side): level.value for side, level in self.ai.items()}}

    @classmethod
    def from_dict(cls, mission: Mission, world: World, data: dict[str, Any]) -> Run:
        if data.get("id") != mission.id:
            raise ValueError(f"mission block is for {data.get('id')!r}, not {mission.id!r}")
        if not isinstance(data.get("vars"), dict) or not isinstance(data.get("fired"), dict) or not isinstance(data.get("state"), dict):
            raise ValueError("mission block needs vars, fired and state objects")
        run = cls(mission, world, flags=data["vars"])
        # Verbatim, not through the constructor's filter: those are this run's own variables, and the answers it
        # already gave are among them.  Dropping them lost the choice the player made before the save (the emissary
        # at Greywater Ford), with it the objective the answer opens and the flag the campaign remembers.
        run.vars = dict(data["vars"])
        run.fired = {str(k): float(v) for k, v in data["fired"].items()}
        if "ai" in data:
            run.ai = {int(side): Difficulty(level) for side, level in data["ai"].items()}
        for objective_id, state in data["state"].items():
            if objective_id in run.state:  # an objective this version no longer has is simply forgotten
                if state not in ("hidden", "open", "done", "failed"):
                    raise ValueError(f"objective {objective_id!r} in unknown state {state!r}")
                run.state[objective_id] = state
        # A failed objective lost the mission when it failed, and is never looked at again; the result shows a frame
        # later, so a save can fall between the two.
        run.lost = next((o.text for o in mission.objectives if run.state[o.id] == "failed"), None)
        return run

    def remembered(self) -> dict[str, Any]:
        return {key: self.vars[key] for key in self.mission.remember if key in self.vars}


# -- Progress across missions -----------------------------------------------------------


_KNOWN = ("format", "campaign", "difficulty", "completed", "flags")


@dataclass
class Progress:
    campaign: str
    difficulty: Difficulty
    completed: list[str] = field(default_factory=list)
    flags: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)  # keys this version does not know, written back untouched

    def next_mission(self, campaign: Campaign) -> Mission | None:
        """The first mission in order not yet completed; None once the campaign is finished."""
        return next((m for m in campaign.missions if m.id not in self.completed), None)

    def complete(self, mission: Mission, remembered: dict[str, Any]) -> None:
        if mission.id not in self.completed:
            self.completed.append(mission.id)
        self.flags.update(remembered)

    def to_dict(self) -> dict[str, Any]:
        return {**self.extra, "format": FORMAT, "campaign": self.campaign, "difficulty": self.difficulty.value,
                "completed": list(self.completed), "flags": dict(self.flags)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Progress:
        if not isinstance(data, dict):
            raise ValueError("campaign progress must be an object")
        version = data.get("format")
        if type(version) is not int:
            raise ValueError("campaign progress has no format number")
        if version > FORMAT:
            raise ValueError(f"campaign progress format {version} is newer than this Warband understands (format {FORMAT}); update the game")
        if not isinstance(data.get("campaign"), str):
            raise ValueError("campaign progress names no campaign")
        completed = data.get("completed", [])
        flags = data.get("flags", {})
        if not isinstance(completed, list) or not all(isinstance(m, str) for m in completed):
            raise ValueError("completed missions must be a list of ids")
        if not isinstance(flags, dict):
            raise ValueError("flags must be an object")
        difficulty = Difficulty(data.get("difficulty", Difficulty.MEDIUM.value))
        if difficulty not in _SHIFT:
            raise ValueError("the campaign's difficulty must be easy, medium or hard")
        return cls(data["campaign"], difficulty, list(completed), dict(flags),
                   {k: v for k, v in data.items() if k not in _KNOWN})


class ProgressStore:
    """The progress file under the game's data directory, with the save manager's durable writes and backup.  A file
    this version cannot read must never be written over: :meth:`set_aside` moves it out of the way first."""

    def __init__(self, data_dir) -> None:
        self.saves = SaveManager(data_dir / "campaign")
        self.path = data_dir / "campaign" / "save_1.json"
        self.aside = self.path.with_name("save_1.unreadable.json")

    def load(self) -> Progress | None:
        saved = self.saves.load(1)
        if saved is None:
            return None
        try:
            return Progress.from_dict(saved["state"])
        except (KeyError, TypeError, ValueError) as error:
            raise SaveError(f"Cannot read the campaign progress: {error}") from error

    def save(self, progress: Progress) -> None:
        self.saves.save(1, progress.to_dict(), "WarbandCampaign", summary={"completed": len(progress.completed)})

    def clear(self) -> None:
        self.saves.delete(1)

    def set_aside(self) -> None:
        """Move a progress file this version cannot read (a newer Warband's, or a damaged one) to :attr:`aside`, so a
        new campaign begins without writing over it."""
        self.path.replace(self.aside)
