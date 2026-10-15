"""The Undertow's dialogue, kept apart from its authored maps and triggers.

Each Step gives its keeper a different stake in the same machinery. Tactical
instructions stay explicit, but the characters argue from their own work and
history. Outcome lines read actions the player actually performed; no branch
assumes the other branch's sacrifice or forgiveness.
"""

from warband.story.campaign import ChartBeat, Choice, Dialog, Line, Option


MILL_BRIEFING: Dialog = (
    Line("Hasp", "The wolves left the sheep alive. Now they're coming for the mill. "
                 "My fieldhands are still out there, Captain.",
         chart=ChartBeat("The fieldhands are still outside",
                         ("home", "mill_fields"))),
    Line("Issa", "I'm here, Hasp. Company, cover the south field. "
                 "That vault's been humming since dawn. Get the hands indoors before we touch it.",
         chart=ChartBeat("Hold the south field; protect the vault",
                         ("mill_fields", "mill_vault"), ("home", "mill_fields"))),
    Line("Issa", "Your company is ready. Right-click a wolf to attack, or the ground to move. "
                 "Alt+1, then click a wounded ally, casts Mend. We keep the village safe first.",
         chart=ChartBeat("Take command of the company",
                         ("home", "mill_fields", "mill_vault"))),
)


MILL_DEBRIEF: Dialog = (
    Line("Hasp", "All right. The night shift can come in. I'll bring the crew something hot.", when="undertow_mill_vault"),
    Line("Hasp", "No spell-light tonight. Tell the night shift to sleep; we'll start at sunrise.", when="undertow_mill_shuttered"),
    Line("Hasp", "I'll need timber for that roof before it rains. Captain, don't take every carpenter with you.", when="undertow_mill_lost"),
    Line("Brakk", "Captain Renn? Brakk, from the Saltmarches. Our camps are moving up. We need the road through Millfield."),
    Line("Brakk", "Your lock held. Is there room here for people who have lost theirs?", when="undertow_mill_vault"),
    Line("Brakk", "You shut your own lock. I'd heard the Lockwatch never did that.", when="undertow_mill_shuttered"),
    Line("Brakk", "We saw the light go out from the road. How many hurt?", when="undertow_mill_lost"),
    Line("Issa", "Hasp, open the storehouse. Brakk, show me where your people are. We go down together."),
)


CARAVAN_BRIEFING: Dialog = (
    Line("", "Issa scouts the road down-valley. Brakk brings the Saltmarch camps uphill, to the Broken Tooth mesa.",
         chart=ChartBeat("Uphill, to the Broken Tooth",
                         ("old_camp", "mesa"), ("old_camp", "middle_ford", "mesa"))),
    Line("Brakk", "Strip the Old Camp to its pegs. Hall-timbers, farm-frames, everything we can carry. We raise it again on the Tooth.",
         chart=ChartBeat("Salvage the Old Camp; rebuild on the mesa",
                         ("old_camp", "mesa"), ("old_camp", "middle_ford", "mesa"))),
    Line("Ugga", "Six drovers. Five to put a roof up, one to tell the other five they're doing it wrong. Keep five of us on that mesa, Brakk.",
         chart=ChartBeat("Bring at least five drovers home",
                         ("old_camp", "mesa"))),
    Line("Ugga", "The Open Hand's camp guards the north ford. Blast their dam-pylon and the water will clear them out. "
                 "I'd take that over the spiders at the south ford.",
         chart=ChartBeat("The guarded north ford and its dam",
                         ("north_ford", "dam_pylon"))),
    Line("Brakk", "That's Hasp's millpond, Ugga. Her wheels stop if we drain it, and their dam crew is below the spill. "
                  "We can open the middle causeway instead, or fight through the south ford.",
         chart=ChartBeat("Choose a crossing; count the cost to Millfield",
                         ("middle_ford", "south_ford", "dam_pylon"), ("old_camp", "middle_ford", "mesa"),
                                 alternatives=(("old_camp", "south_ford", "ford_east", "mesa"),))),
)


CARAVAN_DEBRIEF: Dialog = (
    Line("", "Brakk unfolds a paper worn soft at the creases. Issa's signature crosses one of them."),
    Line("Brakk", "Ashford. Six years ago, at lambing. You sent the bloom through our camp. My sister Orra stayed with the last pen."),
    Line("Issa", "There were farmhouses below the other vent. I had to get the pressure off before—"),
    Line("Brakk", "I know what was below the other vent. Orra was below yours."),
    Line("Issa", "I signed it. Nine people died. I kept the farms and called that enough."),
    Line("Brakk", "You shut your own works at Millfield. When we get to the next lock, I want to be there before you touch it.",
         when="undertow_mill_shuttered", unless="undertow_dam"),
    Line("Brakk", "You held Millfield. Good. Next time, hear the camp below it before you open a vent.",
         when="undertow_mill_vault", unless="undertow_dam"),
    Line("Brakk", "Millfield lost a lock. It has not lost the right to be asked. Neither have we.",
         when="undertow_mill_lost", unless="undertow_dam"),
    Line("Brakk", "And today we took Hasp's millpond. I wanted our people over that river. I still have to face her.", when="undertow_dam"),
    Line("Issa", "We'll go to her together. I'll leave a repair crew.", when="undertow_dam"),
    Line("Issa", "Come with me, Brakk. Before I touch it.", unless="undertow_dam"),
    Line("Ugga", "The camp's up. Supper's on. Also, this was nailed to the roadblock: Sella Voss says open the locks and warn the camps. "
                 "Could someone tell her a warning needs a road?"),
)


GROVE_BRIEFING: Dialog = (
    Line("", "New shoots crowd the Deep Grove's road. Violet sap beads on a row of fresh stumps.",
         chart=ChartBeat("The living filter is at its limit",
                         ("moon_hall", "firebreak"))),
    Line("Wrenna", "We cut those last spring. The roots usually take a week to cover the road again. They did it overnight.",
         chart=ChartBeat("The grove grows back overnight",
                         ("moon_hall", "firebreak"))),
    Line("Issa", "There's a Lockwatch crew ahead. Stop the saws until we've spoken to them.",
         chart=ChartBeat("Hear the woodcutters before drawing steel",
                         ("cutter_camp",), ("moon_hall", "cutter_camp"))),
    Line("Wrenna", "The camp is south. Walk in without an attack order if you want an answer. "
                   "And leave my escort behind if I visit the Ancient in the eastern ring. It remembers what soldiers do.",
         chart=ChartBeat("Courtesy before steel at the stone ring",
                         ("guardian_ring",), ("moon_hall", "guardian_ring"))),
)


GROVE_PARLEY: Dialog = (
    Line("Pell", "Sergeant Pell, Lockwatch. Captain, here's your warrant. Firebreak from the south road to the old stone ring."),
    Line("Issa", "It stopped the last bloom reaching Hasp's fields. Those men are doing what I told them."),
    Line("Wrenna", "And where did that bloom go? Here. We had blossom in winter. "
                   "These roots drink what you send us; you've ordered him to cut them."),
    Line("Issa", "Pell, stop the saws. I should have come down this road before I signed that."),
    Line("Pell", "I'll need the cancellation in writing, Captain. Then my crew can hold the south road. Nobody else comes in with an axe."),
    Line("Wrenna", "I'll walk the line with you, Sergeant. There may still be cuts we need to make. Let me show you which roots they take."),
)


GROVE_ROUT_AFTERMATH: Dialog = (
    Line("", "In the ruined camp, a warrant hangs beside the abandoned saws. Issa's seal is unbroken."),
    Line("Issa", "My standing order. That firebreak kept the last bloom out of Millfield."),
    Line("Wrenna", "It came here instead. We grew blossom in winter. Now your men have cut the roots that drank it."),
    Line("Issa", "I sent them. Pell would have shown us this if we'd let him. Bring the warrant; I need to cancel every copy."),
)


GROVE_PLAN: Dialog = (
    Line("Wrenna", "Finish the marked firebreak and we'll face a smaller surge, but have fewer roots to help the Maw. "
                   "Keep the grove whole and we must weather both surges here. I'll need the guard at Moon Hall."),
    Choice("grove_intent", "Wrenna", "Which part of the wood do we ask to bear it?",
           (Option("Cut the firebreak; ease this bloom", "cut"),
            Option("Keep the roots; face both surges", "whole"))),
)


GROVE_DEBRIEF: Dialog = (
    Line("Issa", "Pell's warrant has my seal. I'll send the cancellation to every crew. You choose where the saws go, Wrenna."),
    Line("Wrenna", "I'll need people on the stump-line after we leave. Shoots will come back before the deep roots do.", when="undertow_grove_cut"),
    Line("Wrenna", "Still whole. Listen: the leaves have stopped rattling. We can leave a few tenders here and go.", unless="undertow_grove_cut"),
    Line("Wrenna", "Sella sat in my kitchen last winter. I showed her how the roots followed the Chain. "
                   "She drew all afternoon; I kept making tea."),
    Line("Issa", "You didn't know what she was planning."),
    Line("Wrenna", "I didn't ask. Bring my root-map. Dagna will want to see what Sella copied."),
)


WEIGHT_BRIEFING: Dialog = (
    Line("", "Tarnlock's three Weights shine above a basin full of workshops. The Open Hand's siege train is moving up from the south.",
         chart=ChartBeat("A siege train below the three Weights",
                         ("enemy", "weight_1", "weight_2", "weight_3"))),
    Line("Dagna", "Keep two Weights standing. Lose another and the basin spills through the workshops. My repair crews are already out there.",
         chart=ChartBeat("Keep at least two Weights standing",
                         ("weight_1", "weight_2", "weight_3"))),
    Line("Issa", "Cover the crews. Break the siege train before it reaches them.",
         chart=ChartBeat("Break the siege; cover the repair crews",
                         ("home", "enemy"), ("home", "weight_1", "enemy"))),
    Line("Dagna", "After that, come north-east to the seam. There's a drawing I should have shown Sella thirty years ago. "
                  "I won't ask you to fight for Tarnlock without seeing it.",
         chart=ChartBeat("The endless seam has its own account",
                         ("seam",))),
)


WEIGHT_SELLA_EXCHANGE: Dialog = (
    Line("Sella", "You used to tap a gauge twice, Issa. Never trusted the first reading. "
                  "Read these: draw rates rising every year, and another winter's spill signed off as normal."),
    Line("Issa", "How many of your crews are still under those guns? You taught me to clear a worksite before releasing pressure."),
    Line("Sella", "And the council taught me what waiting buys. Another season of spell-light for the towers. Another camp moving uphill. "
                  "I need the Weights down before the next bloom."),
    Line("Dagna", "You need the Tarnlock survey first, Sella. The one we wouldn't let you read. Stop the guns and I'll bring it myself."),
)


WEIGHT_CONFESSION: Dialog = (
    Line("Dagna", "See the layers? No ore in the stone above them. The gold is pressed aether. Two hundred years of it, holding the basin down."),
    Line("Issa", "You've been mining the lid."),
    Line("Dagna", "Thirty years. The gold paid for lock-gaskets, wages, all of this. "
                  "My family made the survey. I signed the copies with this layer missing."),
    Line("Dagna", "Sella's sequence releases the locks onto that thinned cap. Tarnlock bursts before her crews can leave. "
                  "We must relieve the seam first. I'll mark the bypass on her drawing."),
    Choice("seam_intent", "Dagna", "The face is still open. What do we do with it?",
           (Option("Cap its rift; quiet the Maw", "cap"),
            Option("Mine 300 gold; risk Maw blooms", "mine"),
            Option("Post a guard; close the face", "guard"))),
    Line("Dagna", "North-east. A vault on the throat-rift, three hundred gold hauled, or soldiers at the face after the siege. "
                  "Tell my crews which. I'll stay to see it done.", when="seam_intent"),
)


WEIGHT_DEBRIEF: Dialog = (
    Line("Dagna", "Tern, one of Sella's engineers, came through our line. She was promised an hour to clear the works. "
                  "Sella's own gauge-sheet says nine minutes. Both in the same handwriting."),
    Line("Issa", "She used to wait for the last apprentice before testing a valve. Bring Tern. I want Sella to look her in the face."),
    Line("Dagna", "With both surveys. Mine goes on top. No missing layer this time."),
)


MAW_BRIEFING: Dialog = (
    Line("", "The river falls into the Maw without pooling. Across the broken ring, Sella waits. "
             "The marked refuge tower in her southern camp holds wounded crews, including Tern's apprentices.",
         chart=ChartBeat("The Keepers arrive at the broken ring",
                         ("keepers_camp", "keystone", "enemy"), ("keepers_camp", "keystone"))),
    Line("Sella", "Nine days. We open the locks in stages, move everyone uphill, and finish before the next bloom. "
                  "You have Dagna's bypass now. We can do this.",
         chart=ChartBeat("Sella's refuge holds the wounded crews",
                         ("enemy",))),
    Line("Issa", "Tern was promised an hour at Tarnlock. You wrote nine minutes on the gauge-sheet. Which did her apprentices get told?",
         chart=ChartBeat("The survey's missing nine minutes",
                         ("enemy",))),
    Line("Sella", "An hour. If I'd told them nine minutes, they'd have refused to work. "
                  "I thought getting it finished would make that all right.",
         chart=ChartBeat("The people behind the promise",
                         ("enemy",))),
    Line("Brakk", "They're still in your tower. Ask them now.",
         chart=ChartBeat("Ask the crews waiting in the refuge",
                         ("refuge_tower",))),
    Line("Wrenna", "The grove can take a share, if we give the breath roots and vaults to pass through. "
                   "It will need tenders long after we leave.", unless="undertow_grove_cut",
         chart=ChartBeat("Three vaults to drink the Maw's aether",
                         ("maw_rift_1", "maw_rift_2", "maw_rift_3"))),
    Line("Wrenna", "With the grove cut, only the Guardian or its heart-stone can carry our share. "
                   "If we brought neither, we cannot ground the Maw.", when="undertow_grove_cut",
         chart=ChartBeat("GROUND needs the Guardian or its heart",
                         ("maw_rift_1", "maw_rift_2", "maw_rift_3"))),
    Line("", "Your first work commits the ending: RESEAL by repairing the Keystone with peasants; "
             "OPEN by destroying a seal-pylon; GROUND by completing a vault on a Maw rift. The other courses then close. Mend heals people, not buildings.",
         chart=ChartBeat("First work commits the ending",
                         ("keystone", "seal_pylon_1", "maw_rift_1"))),
    Line("", "RESEAL needs full repairs and victory over the final assault. OPEN needs Issa at the marked Relief Sluice, "
             "all three pylons destroyed, and the bloom defeated. GROUND needs three Maw vaults, 450 stored aether, and victory over the last surge.",
         chart=ChartBeat("Set the Relief Sluice before OPEN",
                         ("relief_sluice", "keystone"), ("keepers_camp", "relief_sluice"))),
)


MAW_REFUGE_WARNING: Dialog = (
    Line("Dagna", "That marked tower is the refuge. Tern's apprentices are in there: Neri and the twins. Two came out of Tarnlock on stretchers."),
    Line("Issa", "Keep siege fire off that tower. We're here for the ring. Leave the wounded somewhere to shelter."),
)


MAW_COMMIT_SEALED: Dialog = (
    Line("Issa", "Repair the Keystone. No vent opens until the keeper below it agrees. Brakk, you take the lower gauge."),
    Line("Brakk", "I want a key to the valve too. Orra's camp had a gauge."),
    Line("Issa", "Take mine."),
    Line("Sella", "And when a keeper says no? You'll be back here with the same pressure and fewer friends to carry it."),
)


MAW_COMMIT_OPEN: Dialog = (
    Line("Issa", "Open it. People uphill before we lose the lower works."),
    Line("Dagna", "My workshop's down there. So is my father's. Give me a moment. "
                  "Then, Captain: the Relief Sluice first. Stand at its mark; I've set the corrected measure."),
    Line("Sella", "I'll pass that drawing to every crew. The actual clearance time, on every copy."),
)


MAW_RELIEF_OPENED: Dialog = (
    Line("Dagna", "The bypass is taking the seam's load. Gauge falling. Now we can release the three seals without bursting Tarnlock."),
    Line("Sella", "I see it. Crews, check that reading yourselves. Then back from the ring."),
    Line("Issa", "Disable the remaining pylons. Soldiers, fall back to the north camp when they're down. Keep the road clear."),
)


MAW_OPENED: Dialog = (
    Line("Sella", "Tools down. All companies back to camp. The Keepers have the road; nobody fights them."),
    Line("Issa", "The bloom's through. Turn the company north. Hold it off the camp."),
    Line("Brakk", "Ugga's got the families above the pans. I'll take the rear. This time I know where they're going."),
)


MAW_COMMIT_GROUND: Dialog = (
    Line("Wrenna", "First vault drinking. Two more, then hold 450 aether against the last surge. "
                   "Keep that reserve; spells draw from it too."),
    Line("Issa", "We'll need tenders from all four Steps. I'll send Lockwatch hands down for the first shift."),
    Line("Wrenna", "And the next one? I can leave six here. They're six who won't be tending the grove."),
    Line("Sella", "Put their wages ahead of spell-light. Otherwise you'll have built the council another cheap workshop."),
)


MAW_FINAL_SEALED: Dialog = (
    Line("Sella", "You're giving the council back its locks. Last company, with me. Break the Keystone before it sets."),
    Line("Issa", "Hold the Keystone. Anyone who puts down a weapon gets through to the refuge. Make room for them."),
)


MAW_DEBRIEF: Dialog = (
    Line("Sella", "My last company broke. Are you sending guards to the tower?", when="undertow_ending_sealed"),
    Line("Issa", "Stretcher crews first. Then you and I are going to the lower valve with Brakk.", when="undertow_ending_sealed"),
    Line("Dagna", "The workshop roofs are under. I thought I'd have longer to look. "
                  "Sella, help me find the crews before we start anything else.", when="undertow_ending_open"),
    Line("Sella", "Tern can call the roll. I'll stand where they can see me.", when="undertow_ending_open"),
    Line("Wrenna", "The leaves at Moon Hall are settling. I can feel it through the roots. "
                   "Now I need to go home and tell six people why they aren't coming with me.", when="undertow_ending_ground"),
    Line("Sella", "I'll take a shift. Tern can check my gauges before anyone works from them.", when="undertow_ending_ground"),
    Line("Brakk", "Ugga sent word. The first roof's up on the Tooth. She wants to know how many beds to leave for Millfield."),
    Line("Brakk", "I'll keep Orra's paper. But I'll walk down to the next valve with you.",
         when="undertow_mill_shuttered", unless="undertow_dam"),
    Line("Brakk", "We start with the camps below Millfield, Captain. I'll show you the paths.",
         when="undertow_mill_vault", unless="undertow_dam"),
    Line("Brakk", "When Hasp rebuilds, we go with her to see what lies below Millfield.",
         when="undertow_mill_lost", unless="undertow_dam"),
    Line("Brakk", "And then we go to Hasp. I've found six hands for her mill. Put yours down for the timber.", when="undertow_dam"),
    Line("Dagna", "Tern's apprentices are coming out of the refuge. Neri's kept the gauge-sheets dry. "
                  "I'll find her a place at the new works, if she wants one.", when="undertow_sella_tower_spared"),
    Line("Dagna", "The refuge is gone. Tern is looking for her apprentices. Help her before you ask me for another drawing.",
         unless="undertow_sella_tower_spared"),
)


EPILOGUE: Dialog = (
    Line("", "At the resealed locks, two keys hang above each valve. On Brakk's first watch the mill stops for half a day. "
             "Hasp sends someone down to ask how long, and waits for his answer.", when="undertow_ending_sealed"),
    Line("", "The lower workshops disappear beneath violet rain. Their crews carry the corrected bypass drawing uphill with the tools. "
             "When the weather clears, Dagna stakes out a smaller shop above the old waterline.", when="undertow_ending_open"),
    Line("", "Three vaults drink at the Maw. Four sets of boots wait by the watch-room door; the next shift brings its own supper. "
             "The grove's tenders teach the lockwrights which roots to leave alone.", when="undertow_ending_ground"),
    Line("", "Hasp adds the vault crew to the mill's supper rota. The night they held the lock is still an excuse for second helpings.", when="undertow_mill_vault"),
    Line("", "The shuttered vault stores grain. The mill starts at sunrise; Hasp turns away anyone who wakes her night shift before then.", when="undertow_mill_shuttered"),
    Line("", "Hasp hangs the fallen vault's gauge beside the flour scales. When the roof is mended, she starts asking for carpenters for the next Step.", when="undertow_mill_lost"),
    Line("", "Without its millpond, Millfield buys flour through two lean seasons. Saltmarch carts bring timber back on every trip. "
             "Ugga complains about the weight and never brings an empty cart.", when="undertow_dam"),
    Line("", "Shoots cover the firebreak before the stump-line rots. Wrenna still takes the long way round it; "
             "she is waiting for the deep roots, which grow more slowly.", when="undertow_grove_cut"),
    Line("", "In the whole Deep Grove, the road needs clearing every spring. The road crew asks Wrenna to walk it with them before anyone starts a saw.", unless="undertow_grove_cut"),
    Line("", "Wrenna keeps the eastern path to the Ancient's stone ring open. No guard is posted there.", when="undertow_guardian_ally"),
    Line("", "The Guardian's heart-stone warms a chamber in the new works. Wrenna leaves water there on each visit. "
             "She never tells the apprentices it was only a stone.", when="undertow_guardian_core"),
    Line("", "Over the capped seam, a vault hums. Dagna hangs the complete survey in its doorway, low enough for an apprentice to read.", when="undertow_seam_capped"),
    Line("", "Seam-gold pays the first crews. Dagna keeps the haul weights beside the gauges. When someone asks for another cart, "
             "she makes them come down and read both.", when="undertow_seam_mined"),
    Line("", "A guard sits at the closed seam. The council's next survey party is made to wait while an apprentice goes for Dagna.", when="undertow_seam_guarded"),
    Line("", "Tern's apprentices mend gauges at a long bench. Neri writes the clearance time above every station before letting anyone take up a tool.", when="undertow_sella_tower_spared"),
    Line("", "Tern pins three names beside the refuge's broken door. The next survey leaves a blank space there until she can finish looking.", unless="undertow_sella_tower_spared"),
    Line("", "Sella keeps a workshop above the Saltmarches. On its first morning, Tern sends back a drawing with the clearance time circled. "
             "The corrected copy arrives before work begins."),
    Line("", "Mother Hasp keeps a sack by the mill door marked 'for those coming uphill'. She charges the keepers for it, monthly, with receipts."),
)
