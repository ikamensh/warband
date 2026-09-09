"""Settlement requests outlive individual workers and production buildings.

Requests are unpaid until the existing construction/production rule starts work.
The scheduler owns assignment and waiting reasons; World remains the player interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warband import path as pathing
from warband.rules import BUILDINGS, SIM_DT, UNITS, UPGRADES, BuildingType, UnitType, Upgrade

if TYPE_CHECKING:
    from warband.model import Unit, World


@dataclass
class Plan:
    id: int
    player: int
    kind: str
    type: BuildingType | UnitType | Upgrade
    pos: tuple[int, int] | None = None
    status: str = "Queued"
    worker: int | None = None
    building: int | None = None


class Settlement:
    def __init__(self, world: World):
        self.world = world
        self.plans: list[Plan] = []
        self.next_id = 1

    def player_plans(self, player: int) -> list[Plan]:
        return [plan for plan in self.plans if plan.player == player]

    def can_plan_building(self, building_type: BuildingType, pos: tuple[int, int], player: int) -> str | None:
        if building_type is BuildingType.GOLD_MINE:
            return "Gold mines cannot be built"
        reason = self.world._placement_reason(building_type, pos, player, ignore_units=True)
        if reason is not None:
            return reason
        size = BUILDINGS[building_type].size
        for plan in self.player_plans(player):
            if plan.kind != "building":
                continue
            other_size = BUILDINGS[plan.type].size
            if (pos[0] < plan.pos[0] + other_size and plan.pos[0] < pos[0] + size
                    and pos[1] < plan.pos[1] + other_size and plan.pos[1] < pos[1] + size):
                return "Another building is planned here"
        return None

    def plan_building(self, player: int, building_type: BuildingType, pos: tuple[int, int]) -> int:
        from warband.model import RuleError

        reason = self.can_plan_building(building_type, pos, player)
        if reason is not None:
            raise RuleError(reason)
        return self._add(player, "building", building_type, pos)

    def _add(self, player: int, kind: str, item: BuildingType | UnitType | Upgrade, pos=None) -> int:
        plan = Plan(self.next_id, player, kind, item, pos)
        self.next_id += 1
        self.plans.append(plan)
        return plan.id

    def update(self) -> None:
        if self.world.tick % round(1 / SIM_DT):
            return
        for plan in list(self.plans):
            if plan.kind == "building":
                self._building(plan)
            elif plan.kind == "unit":
                self._unit(plan)
            elif plan.kind == "upgrade":
                self._upgrade(plan)

    def order_unit(self, player: int, unit_type: UnitType) -> int:
        return self._add(player, "unit", unit_type)

    def cancel_plan(self, player: int, plan_id: int) -> None:
        from warband.model import Build, RuleError

        plan = next((plan for plan in self.player_plans(player) if plan.id == plan_id), None)
        if plan is None:
            raise RuleError("No such settlement plan")
        if plan.kind == "building":
            building = self._site(plan)
            if building is not None and not building.done:
                self.world.cancel_building(building.id)
            worker = self.world.units.get(plan.worker)
            if worker is not None and isinstance(worker.order, Build) and worker.order.type is plan.type and worker.order.pos == plan.pos:
                self.world._finish_order(worker)
        self.plans.remove(plan)

    def _unit(self, plan: Plan) -> None:
        world = self.world
        producer_type = UNITS[plan.type].trained_at
        producers = world.player_buildings(plan.player, producer_type, done=True)
        if not producers:
            plan.status = f"Requires a {world.building_info(plan.player, producer_type).name}"
            return
        producers.sort(key=lambda b: (sum(world.unit_info(plan.player, item).build_time for item in b.queue) - b.train_progress, b.id))
        for producer in producers:
            reason = world.can_train(producer, plan.type)
            if reason is None:
                world.train(producer.id, plan.type)
                self.plans.remove(plan)
                return
            plan.status = reason

    def order_upgrade(self, player: int, upgrade: Upgrade) -> int:
        from warband.model import RuleError
        from warband.races import RACES

        if not RACES[self.world.players[player].race].upgrade_allowed(upgrade):
            raise RuleError(f"{UPGRADES[upgrade].name} is a {RACES[UPGRADES[upgrade].race].adjective} art")
        if upgrade in self.world.players[player].upgrades:
            raise RuleError("Already researched")
        if any(b.research is upgrade for b in self.world.player_buildings(player)):
            raise RuleError("Already being researched")
        if any(plan.type is upgrade for plan in self.player_plans(player)):
            raise RuleError("Already planned")
        return self._add(player, "upgrade", upgrade)

    def _upgrade(self, plan: Plan) -> None:
        world = self.world
        if plan.type in world.players[plan.player].upgrades or any(b.research is plan.type for b in world.player_buildings(plan.player)):
            self.plans.remove(plan)
            return
        producers = [b for b in world.player_buildings(plan.player, done=True) if plan.type in b.info.researches]
        if not producers:
            producer_type = next(kind for kind, info in BUILDINGS.items() if plan.type in info.researches)
            plan.status = f"Requires a {world.building_info(plan.player, producer_type).name}"
            return
        for producer in sorted(producers, key=lambda b: b.id):
            reason = world.can_research(producer, plan.type)
            if reason is None:
                world.research(producer.id, plan.type)
                self.plans.remove(plan)
                return
            plan.status = reason

    def _building(self, plan: Plan) -> None:
        from warband.model import Build

        world = self.world
        worker = world.units.get(plan.worker)
        order = worker.order if worker is not None else None
        matching = isinstance(order, Build) and order.type is plan.type and order.pos == plan.pos
        if matching and order.building is not None:
            plan.building = order.building
        building = self._site(plan)
        if plan.building is not None and (building is None or building.done):
            self.plans.remove(plan)
            return
        if matching:
            plan.status = "Building" if worker.constructing is not None else "Builder en route"
            return
        plan.worker = None
        if building is not None and building.builder is not None:
            plan.worker, plan.status = building.builder, "Building"
            return
        if building is None:
            info = BUILDINGS[plan.type]
            if info.requires is not None and not world.player_buildings(plan.player, info.requires, done=True):
                plan.status = f"Requires a {world.building_info(plan.player, info.requires).name}"
                return
            reason = world.can_afford(plan.player, info.cost)
            if reason is not None:
                plan.status = reason
                return
        worker = self._worker(plan)
        if worker is None:
            plan.status = "Waiting for an available worker and safe route"
            return
        if building is None:
            reason = world.can_place(plan.type, plan.pos, plan.player, builder=worker.id)
            if reason is not None:
                plan.status = reason
                return
            world.build(worker.id, plan.type, plan.pos)
        else:
            world.resume_construction([worker.id], building.id)
        plan.worker, plan.status = worker.id, "Builder en route"

    def _site(self, plan: Plan):
        if plan.building is None:
            site = next((b for b in self.world.player_buildings(plan.player, plan.type) if b.pos == plan.pos), None)
            if site is not None:
                plan.building = site.id
        return self.world.buildings.get(plan.building)

    def _worker(self, plan: Plan) -> Unit | None:
        from warband.model import TOUCH, Deposit, Harvest, rect_gap, tile_center
        from warband.rules import UNIT_RADIUS
        from warband.worker_ai import safe_navigation

        world = self.world
        size = BUILDINGS[plan.type].size
        rect = (*plan.pos, size, size)
        navigation = safe_navigation(world, plan.player)
        goals = {(x, y): 0.0
                 for y in range(max(0, plan.pos[1] - 1), min(world.height, plan.pos[1] + size + 1))
                 for x in range(max(0, plan.pos[0] - 1), min(world.width, plan.pos[0] + size + 1))
                 if not navigation[y * world.width + x] and rect_gap(tile_center((x, y)), rect) <= TOUCH + UNIT_RADIUS}
        candidates = []
        for worker in world.player_units(plan.player):
            if (not worker.is_worker or not worker.auto_work or worker.hidden or worker.hp <= 0 or worker.carrying is not None
                    or any(not isinstance(order, (Harvest, Deposit)) for order in worker.orders)):
                continue
            route = pathing.find_work_path(worker.tile, goals, navigation, world.width, world.height)
            if route is not None:
                candidates.append((bool(worker.orders), len(route), worker.id, worker))
        return min(candidates, key=lambda candidate: candidate[:3])[3] if candidates else None

    def to_dict(self) -> dict:
        return {"next_id": self.next_id,
                "plans": [{"id": plan.id, "player": plan.player, "kind": plan.kind, "type": plan.type.value,
                           "pos": list(plan.pos) if plan.pos is not None else None, "status": plan.status,
                           "worker": plan.worker, "building": plan.building} for plan in self.plans]}

    def restore(self, data: dict) -> None:
        self.next_id = data["next_id"]
        enums = {"building": BuildingType, "unit": UnitType, "upgrade": Upgrade}
        self.plans = [Plan(item["id"], item["player"], item["kind"], enums[item["kind"]](item["type"]),
                           tuple(item["pos"]) if item["pos"] is not None else None, item["status"], item["worker"], item["building"])
                      for item in data["plans"]]
