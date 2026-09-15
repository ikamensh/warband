"""The Thornwood War: six missions for the Marches, in three acts.

Ten years of quiet on the Greywater end when orc warbands cross the river and burn Hollowmere (act I).  Held at the
ford, the orcs turn out to be refugees: the Thornwood elves' forest is growing over the wastes, and the dwarves of
Karst Hold, in its path, have gone silent (act II, in the snow, once as the dwarves themselves).  The company comes
home to find the ford under leaves and marches on the Court of Thorns (act III).  Two choices carry across
missions, a truce with the orcs and the dwarves' blasting powder, and one ends the war.

Every mission is a generated map (its seed, size and theme below) reshaped by ``setup``: bases removed or added,
bands placed, camps built, ids stored in the run's variables for the objectives and triggers to read.
"""

from __future__ import annotations

from warband.campaign import (
    Campaign, Choice, Line, Mission, Objective, Option, Run, Side, Speaker, Trigger, after, all_of, any_of, at, objective_done, side_out, var,
)
from warband.model import tile_center
from warband.rules import BuildingType as B, Difficulty, MapTheme, Race, UnitType as U, Upgrade

SPEAKERS = {
    "Aldric": Speaker("Captain Aldric Vane", Race.HUMAN, U.KNIGHT),
    "Maren": Speaker("Sister Maren", Race.HUMAN, U.CLERIC),
    "Tomas": Speaker("Reeve Tomas", Race.HUMAN, U.PEASANT),
    "Gorrash": Speaker("Gorrash Ironjaw", Race.ORC, U.FOOTMAN, player=1),
    "Brunna": Speaker("Thane Brunna Stonebrow", Race.DWARF, U.FOOTMAN),
    "Ysolde": Speaker("Lady Ysolde of the Thornwood", Race.ELF, U.ARCHER, player=1),
    "Warden": Speaker("Thornwood Warden", Race.ELF, U.FOOTMAN, player=1),
}

ACT_1, ACT_2, ACT_3 = "Act I · The Marches", "Act II · The Silent Hold", "Act III · The Thornwood"


def _hall_stands(side: int):
    return lambda run: run.hall(side) is None


def _no_buildings(side: int):
    return lambda run: not run.world.player_buildings(side)


# -- 1. Hollowmere ------------------------------------------------------------------


def _setup_hollowmere(run: Run) -> None:
    world = run.world
    camp_site = run.hall(1).center
    world.clear_player(1)
    camp = run.place(1, B.BARRACKS, camp_site)
    run.place(1, B.FARM, (camp.center[0] + 4, camp.center[1] + 1))
    run.set("camp", list(camp.center))


def _raid(units: list[U]):
    def do(run: Run) -> None:
        camp = tuple(run.get("camp"))
        run.spawn(1, units, camp, attack=run.home(0))
        run.look(camp)

    return do


def _raid_1(run: Run) -> None:
    _raid([U.FOOTMAN] * 3 + [U.ARCHER])(run)
    run.say(Line("Aldric", "Dust on the east road. Here they come — everyone to the hall, peasants inside. Soldiers, hold the road!"))


def _raid_3(run: Run) -> None:
    _raid([U.FOOTMAN] * 5 + [U.ARCHER] * 2 + [U.SCOUT])(run)
    run.say(Line("Aldric", "That's their whole camp on the move. Break this band and Hollowmere stands."))


HOLLOWMERE = Mission(
    id="hollowmere", title="Hollowmere", act=ACT_1,
    sides=(Side("Hollowmere", Race.HUMAN), Side("Bloodfang Raiders", Race.ORC)),
    size="Small", theme=MapTheme.SUMMER, seed=1101,
    briefing=(
        Line("", "Ten years of quiet on the Greywater ended in one night. Orc warbands crossed the river, and the village of Hollowmere burned."),
        Line("Aldric", "The raiders pulled back east to a camp in the hills, but they'll be back once they've counted their dead. "
                       "We hold what's left: a hall, three peasants and the road they'll come down."),
        Line("Maren", "The people need a roof and bread before they need spears, Captain."),
        Line("Aldric", "They'll get both. A farm, a barracks, four soldiers on the road. Then we see what the orcs bring."),
        Line("Tomas", "The mine's untouched, Captain, and there's timber south of the hall. Say the word and we'll dig."),
    ),
    debrief=(
        Line("Maren", "They fought like men with nowhere to go back to, Captain. Look at their packs: pots, blankets, children's things. "
                      "That was no raiding party."),
        Line("Aldric", "Whatever it was, it came out of the wastes across the Greywater, and more will follow. We meet them at the ford."),
        Line("Tomas", "Hollowmere thanks you, Captain. We'll rebuild. Mind the road."),
    ),
    setup=_setup_hollowmere,
    objectives=(
        Objective("farm", "Build a farm", lambda run: bool(run.buildings(0, B.FARM))),
        Objective("barracks", "Build a barracks", lambda run: bool(run.buildings(0, B.BARRACKS))),
        Objective("soldiers", "Train four soldiers", lambda run: len(run.soldiers(0)) >= 4),
        Objective("hold", "Hold Hollowmere against the raids", lambda run: "raid_3" in run.fired and not run.units(1),
                  failed=_hall_stands(0), shown=lambda run: "raid_1" in run.fired),
        Objective("camp", "Or raze the raiders' camp in the east", _no_buildings(1), shown=lambda run: "raid_1" in run.fired, optional=True),
    ),
    triggers=(
        Trigger("raid_1", any_of(all_of(objective_done("farm"), objective_done("barracks"), objective_done("soldiers")), at(300)), _raid_1),
        Trigger("raid_2", after("raid_1", 80), lambda run: (_raid([U.FOOTMAN] * 4 + [U.ARCHER] * 2)(run), run.toast("Another band from the east", "Hold the road"))),
        Trigger("raid_3", after("raid_2", 95), _raid_3),
        Trigger("camp_razed", objective_done("camp"), lambda run: run.toast("The raiders' camp burns", "Whoever is left has nowhere to return to")),
    ),
    win=any_of(objective_done("hold"), objective_done("camp")),
)


# -- 2. Greywater Ford ----------------------------------------------------------------


def _setup_greywater(run: Run) -> None:
    world = run.world
    hall = run.hall(0).center
    run.place(0, B.BARRACKS, (hall[0] + 5, hall[1] + 1))
    run.spawn(0, [U.FOOTMAN] * 3, (hall[0], hall[1] + 4))
    world.players[0].gold = 1500
    run.set("orc_home", list(run.hall(1).center))


def _probe(units: list[U], title: str):
    def do(run: Run) -> None:
        if run.world.players[1].alive:
            run.spawn(1, units, tuple(run.get("orc_home")), attack=run.home(0))
            run.toast(title, "Hold the ford")

    return do


def _emissary(run: Run) -> None:
    run.say(
        Line("Gorrash", "Marcher. I am Gorrash Ironjaw, and I have not come for your fields."),
        Line("Gorrash", "Our lands are gone. The forest walks: it swallowed our camps in a season, the Thornwood elves behind every tree. "
                        "We crossed your river because there was nothing left to stand on."),
        Line("Maren", "Captain — the packs at Hollowmere."),
        Line("Gorrash", "Give us the wastes north of the ford and we trouble you no more. Refuse, and we fight for it, because we can do nothing else."),
        Choice("truce", "Aldric", "Your answer, Captain?", (Option("Grant the truce", True), Option("No quarter", False))),
        Line("Aldric", "The wastes are yours, Ironjaw. Cross a farm and it's war again.", when="truce"),
        Line("Gorrash", "Then we are done here.", when="truce"),
        Line("Aldric", "You burned Hollowmere. You'll get the river.", unless="truce"),
        Line("Gorrash", "So be it, marcher.", unless="truce"),
    )


def _truce(run: Run) -> None:
    run.world.resign(1)
    run.world.take_events()  # a withdrawal, not a fall: no "rival falls" toast
    run.toast("The orcs withdraw", "Ironjaw's people take the wastes north of the ford")


GREYWATER = Mission(
    id="greywater", title="Greywater Ford", act=ACT_1,
    sides=(Side("The Marches", Race.HUMAN), Side("Bloodfang Clan", Race.ORC, ai=Difficulty.EASY)),
    size="Medium", theme=MapTheme.WASTELAND, seed=1202,
    briefing=(
        Line("", "The Greywater is the border. The ford at the old mill is the only crossing for a day's ride, and the orcs have made camp on the far bank."),
        Line("Aldric", "We hold the ford. Ten minutes and the Marcher levies reach us from the south; until then it's us and what we can raise."),
        Line("Maren", "And if they want to talk?"),
        Line("Aldric", "Orcs don't talk, Sister."),
    ),
    debrief=(
        Line("Maren", "A forest that walks. The Thornwood has kept to itself for a hundred years.", when="truce"),
        Line("Aldric", "Ironjaw's lot said it swallowed the wastes in a season. If that's true, the dwarves at Karst Hold sit right in its path, "
                       "and we've had no word from Karst since midsummer.", when="truce"),
        Line("Maren", "They fought to the last peon, Captain. Whatever drove them here frightened them more than we did.", unless="truce"),
        Line("Aldric", "Ironjaw said the forest walks. If the Thornwood is moving, the dwarves at Karst Hold sit in its path, "
                       "and we've had no word from Karst since midsummer.", unless="truce"),
        Line("Maren", "Then someone should go and ask."),
    ),
    setup=_setup_greywater,
    objectives=(
        Objective("hold", "Hold the ford until the levies arrive (10:00)", at(600), failed=_hall_stands(0)),
        Objective("answer", "Answer the orc emissary", lambda run: "truce" in run.vars, shown=lambda run: "emissary" in run.fired),
        Objective("raze", "Raze the orc camp across the ford", side_out(1), shown=var("truce", False)),
    ),
    triggers=(
        Trigger("probe_1", at(150), _probe([U.FOOTMAN] * 3, "Orc scouts at the ford")),
        Trigger("probe_2", at(390), _probe([U.FOOTMAN] * 4 + [U.ARCHER] * 2, "A warband crosses the ford")),
        Trigger("emissary", all_of(at(600), lambda run: run.world.players[1].alive), _emissary),
        Trigger("truce", var("truce", True), _truce),
        Trigger("war", var("truce", False), lambda run: run.toast("No quarter", "Raze the orc camp across the ford")),
    ),
    win=side_out(1),
    remember=("truce",),
)


# -- 3. The Silent Hold ----------------------------------------------------------------


def _setup_silent_hold(run: Run) -> None:
    world = run.world
    start = run.hall(0).center
    goal = run.hall(1).center
    world.clear_player(0)
    world.clear_player(1)
    band = run.spawn(0, [U.KNIGHT, U.CLERIC] + [U.FOOTMAN] * 6 + [U.ARCHER] * 2, start)
    run.set("aldric", band[0].id)
    run.set("maren", band[1].id)
    run.set("goal", [goal[0], goal[1]])
    world.players[0].gold = world.players[0].lumber = 0
    outpost = run.place(1, B.BARRACKS, ((goal[0] * 2 + world.width / 2) / 3, (goal[1] * 2 + world.height / 2) / 3))
    run.spawn(1, [U.FOOTMAN] * 3 + [U.ARCHER] * 2, outpost.center, hold=True)
    middle = (world.width / 2, world.height / 2)
    for corner in ((world.width * 0.75, world.height * 0.25), (world.width * 0.25, world.height * 0.75)):
        patrol = run.spawn(1, [U.FOOTMAN, U.FOOTMAN, U.ARCHER], corner)
        world.patrol([u.id for u in patrol], middle)


def _past_the_middle(run: Run) -> bool:
    world = run.world
    return any(u.x + u.y > (world.width + world.height) / 2 for u in run.units(0))


def _ambush(run: Run) -> None:
    aldric = run.unit("aldric") or (run.units(0) or [None])[0]
    if aldric is None:
        return
    world = run.world
    ahead = (min(world.width - 2, aldric.x + 5), min(world.height - 2, aldric.y + 5))
    run.spawn(1, [U.FOOTMAN] * 3 + [U.ARCHER] * 2, ahead, attack=aldric.pos)
    run.say(
        Line("Warden", "You are far from your river, marchers. The wood does not want you here."),
        Line("Maren", "We come for the dwarves, not for your trees."),
        Line("Warden", "The dwarves are the wood's now."),
    )


SILENT_HOLD = Mission(
    id="silent_hold", title="The Silent Hold", act=ACT_2,
    sides=(Side("Aldric's Company", Race.HUMAN), Side("Thornwood Wardens", Race.ELF)),
    size="Medium", theme=MapTheme.WINTER, seed=1303,
    briefing=(
        Line("", "Karst Hold lies beyond the Frostcomb pass, three days north through country that was open moor a year ago. It is open moor no longer."),
        Line("Aldric", "No wagons, no peasants. A company on foot: Sister Maren, myself and the best of the levy."),
        Line("Maren", "The Thornwood wardens hold the pass. We need only reach it; the dwarves will see us from the walls."),
        Line("Aldric", "Keep the Sister alive. Nothing else out here matters."),
    ),
    debrief=(
        Line("Brunna", "Marchers! By the Deep, we'd stopped watching the road. Thane Brunna Stonebrow. You've walked through the Thornwood's teeth to get here."),
        Line("Aldric", "We came to ask why Karst went silent. I think we have our answer."),
        Line("Brunna", "The wood came up the valley in a month. Roots in the mine shafts, wardens on every ridge; they've sat under our walls since the thaw. "
                       "My hold stands, but it doesn't breathe. Help us break them and Karst is your friend for a hundred years."),
    ),
    setup=_setup_silent_hold,
    objectives=(
        Objective("reach", "Bring Sister Maren to the Frostcomb pass in the south-east", lambda run: run.near("maren", tile_center((int(run.get("goal")[0]), int(run.get("goal")[1]))), 4.0)),
        Objective("maren", "Sister Maren must survive", lambda run: False, failed=lambda run: run.unit("maren") is None, optional=True),
    ),
    triggers=(
        Trigger("road", at(1), lambda run: (run.toast("The pass lies to the south-east", "Keep the company together"), run.look(tuple(run.get("goal"))))),
        Trigger("ambush", _past_the_middle, _ambush),
        Trigger("in_sight", lambda run: run.near("maren", tuple(run.get("goal")), 12.0), lambda run: run.toast("The pass", "Karst's walls lie beyond the wardens' lodge")),
    ),
)


# -- 4. Karst Hold ------------------------------------------------------------------------


def _setup_karst(run: Run) -> None:
    world = run.world
    hold = run.hall(0).center
    run.place(0, B.TOWER, (hold[0] + 5, hold[1] - 3))
    run.place(0, B.TOWER, (hold[0] - 4, hold[1] + 4))
    run.place(0, B.BARRACKS, (hold[0] + 5, hold[1] + 3))
    run.spawn(0, [U.FOOTMAN] * 4 + [U.CATAPULT], (hold[0], hold[1] + 5))
    world.players[0].gold, world.players[0].lumber = 2500, 1000
    camp = run.hall(1).center
    run.place(1, B.BARRACKS, (camp[0] + 5, camp[1]))
    run.spawn(1, [U.FOOTMAN] * 3 + [U.ARCHER] * 2, camp)
    world.players[1].gold += 1500
    run.set("siege", [(hold[0] * 2 + camp[0]) / 3, (hold[1] * 2 + camp[1]) / 3])


def _assault(run: Run) -> None:
    run.spawn(1, [U.FOOTMAN] * 4 + [U.ARCHER] * 3, tuple(run.get("siege")), attack=run.home(0))
    run.toast("The wardens attack the walls", "Stonework: your buildings have +25 % hit points and +2 armour")
    run.look(tuple(run.get("siege")))


KARST_HOLD = Mission(
    id="karst_hold", title="Karst Hold", act=ACT_2,
    sides=(Side("Karst Hold", Race.DWARF), Side("Thornwood Host", Race.ELF, ai=Difficulty.NORMAL)),
    size="Medium", theme=MapTheme.WINTER, seed=1404,
    briefing=(
        Line("Brunna", "You'll lead the hold's defence, Captain; my people know the walls, not the field. Bolt towers, a guard hall, a mortar we've been saving. Gold enough."),
        Line("Aldric", "And the wardens?"),
        Line("Brunna", "Camped at the valley mouth, with a moon hall growing out of the snow. Burn it and the wood goes quiet. "
                       "Ironguards to the front — they'll come the moment they see smoke."),
    ),
    debrief=(
        Line("Brunna", "Quiet. Hear that? A month of that whispering and now — quiet. Karst owes you, Captain."),
        Line("Brunna", "We've one thing worth giving: blasting powder, three casks, and the engineers who know it. "
                       "Take it south for your siege, or leave it here to hold the valley if the wood comes back."),
        Choice("powder", "Brunna", "The powder, Captain?", (Option("Take the powder south", True), Option("Leave it to hold Karst", False))),
        Line("Aldric", "We'll need it more than you, Thane. The Thornwood won't stop at Karst.", when="powder"),
        Line("Brunna", "Then the engineers march with you.", when="powder"),
        Line("Aldric", "Keep it. If the wood comes back, I want Karst still standing behind us.", unless="powder"),
        Line("Brunna", "Then take the hold's gold instead. Two thousand, and don't argue.", unless="powder"),
    ),
    setup=_setup_karst,
    objectives=(
        Objective("break", "Break the siege: destroy the Thornwood camp", side_out(1)),
        Objective("hold", "Karst's Deep Hold must stand", lambda run: False, failed=_hall_stands(0), optional=True),
    ),
    triggers=(
        Trigger("assault", at(4), _assault),
    ),
    remember=("powder",),
)


# -- 5. Greywater Retaken ------------------------------------------------------------------


def _setup_retaken(run: Run) -> None:
    world = run.world
    hall = run.hall(0).center
    run.place(0, B.BARRACKS, (hall[0] + 5, hall[1] + 1))
    run.spawn(0, [U.FOOTMAN] * 4 + [U.ARCHER] * 2, (hall[0], hall[1] + 5))
    if run.get("truce"):
        world.players[0].gold += 1000
        run.ai[1] = Difficulty.EASY
    lodge = run.hall(1).center
    run.place(1, B.BARRACKS, (lodge[0] + 5, lodge[1]))
    run.place(1, B.TOWER, (lodge[0] - 4, lodge[1] - 3))
    run.spawn(1, [U.FOOTMAN] * 4 + [U.ARCHER] * 2, lodge)
    world.players[1].gold += 1000


RETAKEN = Mission(
    id="retaken", title="Greywater Retaken", act=ACT_3,
    sides=(Side("The Marches", Race.HUMAN), Side("Thornwood Lodges", Race.ELF, ai=Difficulty.NORMAL)),
    size="Medium", theme=MapTheme.SUMMER, seed=1505,
    briefing=(
        Line("", "The company came south by the river road and found the ford under leaves. The old mill is a lodge of living wood; the Thornwood has crossed the Greywater."),
        Line("Aldric", "They took the ford while we were away. Everything south of it is next."),
        Line("Gorrash", "Marcher. Ironjaw keeps his word: my warbands harry their flank from the wastes, and their camp is thin on the north side. "
                        "There's gold with this message. Call it tribute.", when="truce"),
        Line("Maren", "No help from the north, Captain. We drove the orcs into the river ourselves.", unless="truce"),
        Line("Aldric", "Then we take it back the hard way. Raise the levy; every lodge on this bank burns."),
    ),
    debrief=(
        Line("Maren", "Look at the trees, Captain. The ones we felled this morning are growing back."),
        Line("Aldric", "Regrowth. It's not an army we're fighting, it's a season."),
        Line("Maren", "Then we go to its root. Lady Ysolde holds the Court of Thorns at the heart of the wood. Stop her, and the forest goes back to being a forest."),
    ),
    setup=_setup_retaken,
    objectives=(
        Objective("retake", "Retake the ford: destroy every Thornwood building", side_out(1)),
        Objective("hall", "Your town hall must stand", lambda run: False, failed=_hall_stands(0), optional=True),
    ),
    triggers=(
        Trigger("tribute", all_of(at(1), var("truce", True)), lambda run: run.toast("Orc tribute", "+1000 gold from Ironjaw; the lodges are thin on the north side")),
    ),
)


# -- 6. The Court of Thorns ------------------------------------------------------------------


def _setup_court(run: Run) -> None:
    world = run.world
    hall = run.hall(0).center
    run.place(0, B.BARRACKS, (hall[0] + 5, hall[1] + 1))
    run.spawn(0, [U.FOOTMAN] * 4 + [U.ARCHER] * 2 + [U.KNIGHT] * 2, (hall[0], hall[1] + 5))
    if run.get("powder"):
        run.place(0, B.WORKSHOP, (hall[0] - 4, hall[1] + 4))
        world.players[0].upgrades.add(Upgrade.SIEGE)
        run.spawn(0, [U.CATAPULT] * 2, (hall[0] + 2, hall[1] + 6))
    else:
        world.players[0].gold += 2000
    court = run.hall(1).center
    run.place(1, B.BARRACKS, (court[0] + 5, court[1]))
    run.place(1, B.BARRACKS, (court[0], court[1] + 5))
    run.place(1, B.TOWER, (court[0] - 4, court[1] - 3))
    run.place(1, B.TOWER, (court[0] + 4, court[1] - 4))
    run.spawn(1, [U.FOOTMAN] * 6 + [U.ARCHER] * 4 + [U.KNIGHT], court)
    world.players[1].gold += 3000
    if run.get("truce"):
        world.clear_player(2)  # Ironjaw's warbands hold the northern wood for us; the site and its mine lie open
    else:
        warband = run.hall(2).center
        run.spawn(2, [U.FOOTMAN] * 4 + [U.ARCHER] * 2, warband)
        world.players[2].gold += 1000


COURT_OF_THORNS = Mission(
    id="court_of_thorns", title="The Court of Thorns", act=ACT_3,
    sides=(Side("The Marches", Race.HUMAN), Side("The Court of Thorns", Race.ELF, ai=Difficulty.HARD),
           Side("Ironjaw's Warband", Race.ORC, ai=Difficulty.NORMAL)),
    size="Large", theme=MapTheme.SUMMER, seed=1606,
    briefing=(
        Line("", "The Court of Thorns: a moon hall older than the Marches, ringed with eyries, under a canopy that has never been cut."),
        Line("Ysolde", "Marcher. You have cut your way through half my wood to bring me a message. Say it."),
        Line("Aldric", "Pull the forest back to your old borders. The orcs get their wastes, the dwarves their valley, the Marches their river."),
        Line("Ysolde", "The wood does not pull back. It grows. That is what a wood is for."),
        Line("Brunna", "Then it can grow around a crater. The engineers are ready, Captain.", when="powder"),
        Line("Aldric", "Karst's gold bought us a proper siege train. We'll not need powder.", unless="powder"),
        Line("Maren", "Captain — the orcs. Ironjaw's survivors have come out of the wastes, and they're not here to help us.", unless="truce"),
        Line("Maren", "Ironjaw's warbands hold the northern wood. It's the Court alone.", when="truce"),
        Line("Aldric", "Burn the Court. Every lodge, every eyrie, the hall itself."),
    ),
    debrief=(
        Line("Ysolde", "So. The wood burns, and the marcher stands in the ashes of the Court. What now, Captain? Will you cut it all down?"),
        Choice("burn", "Ysolde", "The Thornwood, Captain?", (Option("Burn it back to the old border", True), Option("Bind the Court to a treaty", False))),
        Line("Aldric", "To the old border. Every tree that walks past it, we fell, and we fell it every spring.", when="burn"),
        Line("Ysolde", "Then every spring we will meet.", when="burn"),
        Line("Aldric", "The Court stands, under oath: the wood keeps to the old border, and the Marches keep the peace of it.", unless="burn"),
        Line("Ysolde", "An oath to a forest. You are stranger than your orcs, Captain. Very well.", unless="burn"),
    ),
    setup=_setup_court,
    objectives=(
        Objective("court", "Destroy the Court of Thorns: every Thornwood building", side_out(1)),
        Objective("orcs", "Drive off Ironjaw's warband", side_out(2), shown=lambda run: not run.get("truce")),
        Objective("hall", "Your town hall must stand", lambda run: False, failed=_hall_stands(0), optional=True),
    ),
    triggers=(
        Trigger("engineers", all_of(at(1), var("powder", True)), lambda run: run.toast("Karst's engineers", "Two mortar crews and Siege Engineering, ready at the workshop")),
        Trigger("gold", all_of(at(1), var("powder", False)), lambda run: run.toast("Karst's gold", "+2000 gold from the hold's treasury")),
    ),
    remember=("burn",),
)


CAMPAIGN = Campaign(
    id="thornwood",
    title="The Thornwood War",
    tagline="The orcs came over the Greywater. They were not the enemy.",
    speakers=SPEAKERS,
    missions=(HOLLOWMERE, GREYWATER, SILENT_HOLD, KARST_HOLD, RETAKEN, COURT_OF_THORNS),
    epilogue=(
        Line("", "The Thornwood War ended in the ash of the Court, and the forest stood where it was."),
        Line("", "Every spring since, the Marcher levies ride the old border with axes. Every spring the wood sends a few green shoots to meet them.", when="burn"),
        Line("", "Lady Ysolde's oath held. The wood keeps to the old border, and the eyries watch the Marches with something that is not quite friendship.", unless="burn"),
        Line("", "Gorrash Ironjaw's people keep the wastes north of the ford. His grandchildren trade at Greywater market.", when="truce"),
        Line("", "No orc has crossed the Greywater since. The wastes are empty, and the Marches do not speak of why.", unless="truce"),
        Line("", "Karst Hold sent its engineers home with a crater to boast of, and kept the road to the Marches open.", when="powder"),
        Line("", "Karst Hold kept its powder, and its valley, and paid in gold that built the new mill at Hollowmere.", unless="powder"),
        Line("", "Captain Aldric Vane commands the Marches still. Sister Maren keeps the road."),
    ),
)
