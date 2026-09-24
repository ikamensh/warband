# Warband magic

Aether and the spells it pays for, built in three steps: WB-063 (the resource,
this note), WB-066 (the Mage Tower and the spells), WB-067 (the brains cast).

## Aether (WB-063)

Aether is the third resource and nobody carries it: no worker fetches it and
it is no `rules.Resource`. It rises from **ley rifts**, squares of ground the
size of a vault (2 × 2) that the map generator lays by every hall and, where a
cell has room, out in the shared ground (`docs/warband-maps.md`, *Ley rifts*).
`World.rifts` holds their top-left tiles, fixed for the match.

The **Aether Vault** (Arcane Vault, Spirit Cage, Moon Reliquary, Rune Vault:
2 × 2, 400 gold 200 lumber, needs a hall) is the one building a rift takes: any
other footprint on a rift, or a vault half on one, is refused, so a rift holds
one vault and nobody can deny one with a farm.

| rule | where |
|---|---|
| a finished vault standing square on a rift draws one aether every `[aether].every` seconds (2) into its owner's store | `World._draw_aether`, `Player.aether`, `Player.aether_charge` |
| the store holds `[aether].store` (100) for every finished vault; drawing stops at the cap and saves nothing up | `World.aether_cap` |
| a vault lost (razed, abandoned) lowers the cap at once and spills what no longer fits; its owner hears `spilled` | `World._spill` |
| a vault anywhere else stores and reaches, and draws nothing | `World.taps` |
| a point within `[aether].reach` tiles (10) of a finished vault's middle is in reach | `World.in_reach` |
| aether a second the player's vaults draw now | `World.aether_rate` |

The store is an integer and the charge counts whole steps (one per drawing
vault per step, `rules.AETHER_TICKS` of them an aether), so the draw is exact in
lockstep, in replays and in the compiled simulation. Saves carry the rifts, the
store and the charge. A seat's snapshot keeps a rival's store and charge
private, like its gold; the rifts are public ground, as the map it began with is.

**Seen.** The rift is a glowing crack that streams motes; a drawing vault's cube
glows and draws them in, and a vault of the player's whose store is full goes
dim (whether a rival's store is full is theirs to know: theirs are drawn
drawing). The HUD shows aether as *stored / cap* beside gold and lumber; the
vault's card says what it draws and whether it stands on a rift;
`MapView.draw_reach` washes a selected vault's reach violet, and WB-066 uses it
for an aimed spell. Placing a vault lights the free rifts the player knows,
snaps onto the one under the pointer and says when a site off them would not
draw. `tools/verify_aether.py` renders all of it.

**Not yet.** The brains build no vault: with nothing to spend aether on, one
would only cost them. WB-067 has them build one on their own rift.
