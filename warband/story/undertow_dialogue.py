"""The Undertow's dialogue, kept apart from its authored maps and triggers.

Mill outcomes distinguish a held vault, intentional shuttering and a lost vault.
The Maw names the corrected Relief Sluice procedure, and its closing lines read
the chosen ending and the refuge tower's fate. Runtime actions set these flags;
the dialogue never substitutes a menu answer for an action on the map.
"""

from warband.story.campaign import Choice, Dialog, Line, Option


MILL_BRIEFING: Dialog = (
    Line("", "Violet aether rises beneath Millfield. Its vault has metered that breath for generations; "
             "now it strains, and beasts are coming uphill."),
    Line("Hasp", "Flour first, Captain. My mill feeds half the Hollow. If the lock goes, tell me before you tell the council."),
    Line("Issa", "Soldiers to the south fields. Keep the peasants clear, and Sister's Mend ready. "
                 "We hold the vault while it keeps people safe."),
    Line("Hasp", "Good. A lock is useful. A village is the reason we have one."),
)


MILL_DEBRIEF: Dialog = (
    Line("Brakk", "Captain Renn. Brakk, of the Saltmarches. My people are moving uphill before the bloom does. All of them, this time."),
    Line("Brakk", "You held your lock. I hope Millfield was asked what holding it might cost. "
                  "I have seen a captain make that choice for a camp before.", when="undertow_mill_vault"),
    Line("Brakk", "You gave up your own lock to spare your village. That is not the answer I expected from the Lockwatch.",
         when="undertow_mill_shuttered"),
    Line("Brakk", "Your vault fell. That is a loss, Captain, not a choice. I know the difference; I wish more officers did.",
         when="undertow_mill_lost"),
    Line("Issa", "Get your people clear, Brakk. Then we go down together and find out why the locks are failing."),
)


CARAVAN_BRIEFING: Dialog = (
    Line("", "While Issa scouts the road down-valley, Brakk leads the Saltmarches uphill to the Broken Tooth mesa."),
    Line("Brakk", "Strip the Old Camp to its pegs. We carry the hall-timbers across the Sorrow and raise them on the Tooth."),
    Line("Ugga", "Six drovers, Brakk. Keep five of us breathing and I'll raise you a camp on that rock."),
    Line("Brakk", "The river has three fords. Use the road that gets us home. We are moving people, not winning a river."),
)


CARAVAN_DEBRIEF: Dialog = (
    Line("Brakk", "Six years ago, a bloom came up this Step at lambing. The Lockwatch vented it through my sister's camp. "
                  "She stayed to get the last lambs clear. I have carried the order ever since."),
    Line("Issa", "I signed it. Nine people died, and I called that the smaller number. The order was lawful. The decision was mine."),
    Line("Brakk", "You put the number on the paper. I put my sister in the ground."),
    Line("Issa", "I cannot give her back, or ask you to forgive me. I can put the full order on record, "
                 "and give the people below a say before another vent opens. No camp gets volunteered again."),
    Line("Brakk", "At Millfield you gave up your own works. I will walk with you, Captain. I have not forgiven you.",
         when="undertow_mill_shuttered", unless="undertow_dam"),
    Line("Brakk", "At Millfield you held the lock again. If we walk together, you will have to hear us before you count us.",
         when="undertow_mill_vault", unless="undertow_dam"),
    Line("Brakk", "Millfield lost its lock. That does not make Ashford right. But you came down to hear this, and I will walk with you.",
         when="undertow_mill_lost", unless="undertow_dam"),
    Line("Brakk", "Today we spent Millfield's millpond to buy our road. Put that in the account too. It was not harmless because we needed it.",
         when="undertow_dam"),
    Line("Issa", "Then Hasp gets the truth, and our help with what it cost her. Your name beside mine, Brakk.", when="undertow_dam"),
    Line("Ugga", "The road crew's orders name Sella Voss. Open the locks before they burst, and warn the camps. "
                 "Late warning is not much use in water."),
)


GROVE_BRIEFING: Dialog = (
    Line("", "The Deep Grove drinks surplus aether and spends it growing. This spring it is at its limit, "
             "and someone is cutting a firebreak through it."),
    Line("Wrenna", "Saws in my grove, Captain. Trees coming down in a marked line. Very tidy, for a wound."),
    Line("Issa", "Stop the cutting until we know who ordered it. They may think they are saving Millfield. Hear them first."),
    Line("Wrenna", "Gladly. And the Ancient in the eastern stone ring may answer courtesy before steel. "
                   "I will go alone, if we want to find out."),
)


GROVE_ROUT_AFTERMATH: Dialog = (
    Line("", "Among the woodcutters' tools lies a Lockwatch warrant, stamped with Issa Renn's seal."),
    Line("Wrenna", "Your men, Captain. Your standing order: cut a firebreak when a bloom threatens Millfield. "
                   "They thought they were protecting your people."),
    Line("Issa", "I wrote it. I saw trees between a bloom and a farm; I never asked what the trees did. "
                 "The order was mine, and so is what we have done here."),
    Line("Wrenna", "Then choose with the grove in view this time. Finish the marked firebreak, "
                   "or bring our guard to Moon Hall and let the whole wood drink."),
)


GROVE_DEBRIEF: Dialog = (
    Line("Issa", "The woodcutters carried my order. I will not write another firebreak order without asking the people whose trees it takes."),
    Line("Wrenna", "The stumps stopped the worst of it. They also stopped roots that drank for the Maw. "
                   "We saved our hall; we have less to give the next Step.", when="undertow_grove_cut"),
    Line("Wrenna", "The whole wood held. It can still help the Maw, but it has a limit. "
                   "I will not pretend a living grove is an endless drain.", unless="undertow_grove_cut"),
    Line("Wrenna", "One thing more. The roots trace the Chain's own plan. I showed that map to Sella Voss last winter, over tea. "
                   "She was my friend. I did not ask what she meant to do with it."),
    Line("Issa", "Then we warn Tarnlock. Her crews know which vaults are locks. Bring the root-map, Wrenna; we need the full drawing now."),
)


WEIGHT_BRIEFING: Dialog = (
    Line("", "Three great vaults glow in Tarnlock's snow basin. Sella's Open Hand has brought a siege train to the south tree-ring."),
    Line("Dagna", "They will go for the Weights. Someone gave them the right drawings. Keep two standing, and we keep the basin stable."),
    Line("Issa", "Break the siege. Give your repair crews cover, and leave them a road back."),
    Line("Dagna", "One more account waits north-east, at the endless seam. Mine and my council's. "
                  "You will hear it before anyone decides what to do with that face."),
)


WEIGHT_SELLA_EXCHANGE: Dialog = (
    Line("Sella", "I taught you to read a strain gauge, Issa. Read these. Draw rates rise every year. "
                  "The Compact rejected my survey; stone does not obey a vote."),
    Line("Issa", "You also taught me to clear the crew before releasing pressure. Your people are working under this siege."),
    Line("Sella", "The towers sell spell-light while the lower camps take the spills. "
                  "I will open the locks while people can still move. What does another season of waiting buy them?"),
    Line("Dagna", "Room for us to show you the Tarnlock survey. You were denied it. We owe you that much."),
)


WEIGHT_CONFESSION: Dialog = (
    Line("Dagna", "The seam is not a vein. It is two hundred years of aether, crystallised under this basin. We have been mining the lid."),
    Line("Dagna", "Every cart thins the cap. Every cart also bought the gaskets that kept the locks shut. "
                  "My family wrote the survey; my council kept its true measure from Sella."),
    Line("Dagna", "Her sequence vents the locks before relieving the seam. That load meets a thinned cap here and bursts Tarnlock. "
                  "The order of the work must change. Her diagnosis was right; our missing drawing made her remedy fatal."),
    Choice("seam_intent", "Dagna", "What do we do with the seam?",
           (Option("Cap it with a vault on its rift", "cap"),
            Option("Work it and pay for the siege", "mine"),
            Option("Post a guard and close the face", "guard"))),
    Line("Dagna", "North-east. Do it where my crews can witness it. This account goes to the council with my name on it.", when="seam_intent"),
)


WEIGHT_DEBRIEF: Dialog = (
    Line("Dagna", "One of their engineers surrendered with her clearance orders. Sella promised her crew an hour to leave Tarnlock. "
                  "Her own survey gave them nine minutes. She knew both figures."),
    Line("Issa", "That is the clearance rule she taught me. She chose to break it. Bring the engineer and both surveys to the Maw. "
                 "She will answer them herself."),
    Line("Dagna", "And my confession goes with them. The seam's measure, what we drew, what we closed, and who concealed it. No redacted copy."),
)


MAW_BRIEFING: Dialog = (
    Line("", "At the Maw, the Keepers face Sella across the broken ring. The refuge tower behind her holds engineers, wounded crews and their drawings."),
    Line("Sella", "My terms: open the locks over nine days, with the valley warned and moved. "
                  "Count my dead beside the Compact's. Theirs are better filed."),
    Line("Issa", "Your engineer was promised an hour at Tarnlock. Your own survey gave her nine minutes. "
                 "Say it to the people waiting behind you, Sella."),
    Line("Sella", "I lied about their margin. I told myself we had no time for fear; "
                  "it was their nine minutes, and I took the choice from them."),
    Line("Issa", "The first work chooses our course: peasants repairing the Keystone commit us to RESEAL. "
                 "Mend heals people, not buildings. The first pylon destroyed commits OPEN; the first Maw vault completed commits GROUND."),
    Line("Dagna", "Issa, stand at the marked Relief Sluice to open it to my corrected seam measure. "
                  "It sheds the Weight's load safely; the Maw cannot release until that setting is made."),
    Line("Wrenna", "GROUND needs the whole grove, or the Guardian, living or as heart-stone. Our grove stands whole. "
                   "Three drinking vaults, and keepers tending them every day.", unless="undertow_grove_cut"),
    Line("Wrenna", "With the grove cut, GROUND needs the Guardian standing until the works finish, or its stored heart-stone. "
                   "If we brought neither, we must reseal or open.", when="undertow_grove_cut"),
    Line("Issa", "Once we begin one, the other endings are closed. For GROUND, hold all three Maw vaults, bank 450 aether and beat the last surge. "
                 "For RESEAL, repair the Keystone fully and defeat the final assault."),
)


MAW_COMMIT_SEALED: Dialog = (
    Line("Issa", "We reseal. Public gauges on every Step, spell quotas when pressure rises, "
                 "and no vent without the downstream keeper's consent."),
    Line("Dagna", "Repair the Keystone fully with peasants, then keep it whole through their last assault. "
                  "A sealed lock still needs a watch. These limits will be our work, not just words."),
    Line("Sella", "Quotas can be bought, Issa. Councils can forget. I will not leave another lambing camp beneath your promises."),
)


MAW_COMMIT_OPEN: Dialog = (
    Line("Issa", "We open the Hollow. The lower works will be lost; the people get out first. I will not trade them for free magic."),
    Line("Dagna", "Captain, stand at the marked Relief Sluice and open it to the seam's measure. "
                  "That relieves the Weight before we release the three seals."),
    Line("Sella", "Show my crews that setting. Nobody works from a redacted page again."),
)


MAW_RELIEF_OPENED: Dialog = (
    Line("Dagna", "The relief is taking the Weight's load. With all three seal-pylons disabled, the Maw can release without forcing that load through Tarnlock."),
    Line("Sella", "The gauges agree. Give every crew the true margin and a road out. Tools are replaceable."),
    Line("Issa", "Hands clear of the ring. Disable any remaining seal-pylons, then soldiers back to the camp. We defend people while it vents."),
)


MAW_OPENED: Dialog = (
    Line("Sella", "The Relief Sluice took the Weight first. I can see it on the gauges. "
                  "Stand down, everyone. Tools to the camp; no one stays to measure this surge."),
    Line("Issa", "Towers silent, soldiers to the north camp. The bloom is coming through. Keep the road clear."),
    Line("Brakk", "The families are uphill. Hold this last front away from their road."),
)


MAW_COMMIT_GROUND: Dialog = (
    Line("Wrenna", "First vault drinking. Build the other two and bank 450 aether, then hold the ring through the last surge. "
                   "Save your spells; each casting empties the store."),
    Line("Issa", "We keep the valley, but we spend the surplus here. Four peoples on the maintenance rota, every day. "
                 "The towers get no promise of cheap magic."),
    Line("Sella", "I had tools and a deadline. You have roots, stone and people willing to stay. Make sure they hear what staying costs."),
)


MAW_FINAL_SEALED: Dialog = (
    Line("Sella", "The new rules are still a lid. My people will not spend another generation beneath it. Last company, to the ring."),
    Line("Issa", "Anyone who lays down their tools comes through. Hold the Keystone. "
                 "We promised the valley limits; we start with our own fire."),
)


MAW_DEBRIEF: Dialog = (
    Line("Sella", "I still think a dam invites the next council to bargain with a flood. You gave its keepers a right to refuse. "
                  "I will watch whether you honour it.", when="undertow_ending_sealed"),
    Line("Sella", "The lower works are gone. We opened the relief before the locks and gave the valley warning. "
                  "That was the choice I should have offered my crews.", when="undertow_ending_open"),
    Line("Sella", "The gauges are falling without a Step going under. I was missing the roots and the people to tend them. "
                  "Do not let another council call their work free.", when="undertow_ending_ground"),
    Line("Brakk", "The Saltmarches have a home above the pans. That is today's account, Captain."),
    Line("Brakk", "You heard us before choosing for us. I keep the paper; I no longer need it to make you listen.",
         when="undertow_mill_shuttered", unless="undertow_dam"),
    Line("Brakk", "Ashford stays in my pouch. So does your promise that we get a say. I will hold you to the new one.",
         when="undertow_mill_vault", unless="undertow_dam"),
    Line("Brakk", "Millfield lost its lock. We did not make that a reason to spend somebody else's camp. "
                  "I will remember that beside the receipt.", when="undertow_mill_lost", unless="undertow_dam"),
    Line("Brakk", "Millfield lost its water to buy our road. We owe Hasp a working mill. Put my name beside yours on that debt.",
         when="undertow_dam"),
    Line("Dagna", "The survey is public. The whole measure, my family's concealment, and the work we chose. "
                  "Every new council reads it before touching a valve."),
    Line("Dagna", "The refuge crew is through, with their gauges and drawings. They will work beside us, "
                  "with clearance times posted where everyone can read them.", when="undertow_sella_tower_spared"),
    Line("Dagna", "The refuge tower was destroyed. We can rebuild a gauge; we cannot recover every hand or drawing that was inside. "
                  "The names go in the account too.", unless="undertow_sella_tower_spared"),
)


EPILOGUE: Dialog = (
    Line("", "The Chain was resealed. Public gauges now govern its spell quotas, and each downstream keeper can refuse a vent. "
             "The Compact survives by accepting limits it once imposed only on other people.", when="undertow_ending_sealed"),
    Line("", "The Relief Sluice relieved the Weight before the Maw released. The lower works went under violet weather; the warned valley had a road out. "
             "Magic is free and wild, but the Hollow has mills, homes and livelihoods to rebuild.", when="undertow_ending_open"),
    Line("", "Root, stone and three drinking vaults ground the Maw's breath. The locks remain as plumbing, tended every day by all four peoples. "
             "Spell-light is dearer: the surplus that once bought it now keeps their valley habitable.", when="undertow_ending_ground"),
    Line("", "Millfield remembers the night its lock held, and the crew who stood by it. "
             "Its readings are no longer the small figures at the top of someone else's survey.", when="undertow_mill_vault"),
    Line("", "Millfield mills by daylight. Its shuttered vault stores grain now; Hasp calls that a useful spell.",
         when="undertow_mill_shuttered"),
    Line("", "Millfield rebuilt after its vault fell. Hasp hangs the old gauge beside the flour scales: a warning, not a medal.",
         when="undertow_mill_lost"),
    Line("", "The millpond never returned. Saltmarch hands help rebuild the mill, and Hasp keeps the cost of the dry years in their shared account.",
         when="undertow_dam"),
    Line("", "The grove's firebreak remains a stump-scar. Wrenna marks the growth each spring, and every keeper knows what those missing roots once drank.",
         when="undertow_grove_cut"),
    Line("", "The Deep Grove was kept whole. Its share of the valley's work is measured now, instead of being mistaken for endless generosity.",
         unless="undertow_grove_cut"),
    Line("", "The grove sent its eldest to the Maw. Wrenna leaves the Ancient's stone ring open: an offered road, rather than a cage.",
         when="undertow_guardian_ally"),
    Line("", "The Guardian's heart-stone is set in the new works, its warmth metered instead of spent in one blaze. Wrenna calls it a debt, still.",
         when="undertow_guardian_core"),
    Line("", "The capped seam sleeps beneath its vault. Dagna's full confession is read to every new Tarnlock council before any other business.",
         when="undertow_seam_capped"),
    Line("", "Seam-gold paid wages and built refuge walls. Every haul remains in the public account beside the pressure it added.",
         when="undertow_seam_mined"),
    Line("", "The guarded seam's face stays closed. The watch is posted in public; the council can no longer turn a 'survey' into another mine shift.",
         when="undertow_seam_guarded"),
    Line("", "The engineers spared at the refuge tower join the new works. Their first common rule is that no leader gets to improve a clearance time by lying about it.",
         when="undertow_sella_tower_spared"),
    Line("", "A list of the refuge tower's missing hangs beside the public survey. The valley records losses from its own guns in the same ink.",
         unless="undertow_sella_tower_spared"),
    Line("", "Sella Voss keeps a workshop above the Saltmarches and still argues with every keeper who brings a repair. "
             "The evacuation margins on her drawings are public now."),
    Line("", "Mother Hasp keeps a sack by the mill door marked 'for those coming uphill'. She charges the keepers for it, monthly, with receipts."),
)
