# Warband procedural art

`warband/textures.py` owns the art recipes. All geometry is rasterized once
through Saga2D's existing low-poly renderer and then drawn as atlas sprites.
No source image files, new runtime dependencies, or simulation/save fields are needed.

## Resource scenery

- **20 trees per theme.** Fir and spruce grow progressively shorter branch
  whorls around a leaning leader. Oak and birch recursively split tapered
  branches, then grow crowns at the terminal buds. Each seed changes height,
  lean, branch direction, crown size and foliage. Winter adds snow to the
  same skeleton; wasteland exposes bare branches.
- **20 crystal colonies per theme.** Six-sided prisms have leaning growth
  axes, pointed terminal facets, dominant crystals and smaller satellites.
  Cool teal, blue and violet minerals distinguish these blocking rocks from
  the gold resource. Winter adds snow to their stone bases.
- **20 gold outcrops.** Warm amber crystals grow out of irregular stone
  clusters around a timbered entrance and mine track. These retain the
  Gold Mine's original rules and footprint.

Tile-coordinate hashes choose variants without touching the simulation RNG.
A save reload therefore reconstructs the same scenery. The bounded resource
image cache reuses immutable renders across matches; mines register on demand.

## Readable roles

Town halls use twin gate towers and a civic roof; barracks expose a training
yard, targets and weapons; farms have wheat rows and hay. Guard towers have
crenellations and buttresses. Lumber mills expose a toothed saw and stacked
logs; blacksmiths have an open furnace, tall chimney, anvil and quench tub.
Stables surround a horse paddock; workshops have a crane and siege chassis;
churches have a cross-topped spire and buttressed nave.

Unit equipment remains readable across eight facings: workers have straw hats
and aprons; footmen have plate shoulders and kite shields; archers have hoods,
quivers and longbows. Scouts ride light horses under cloaks, knights ride
armored horses with lances and plumes, catapults have spoked wheels and a
throwing spoon, and clerics wear white robes with a mitre and sun staff.

Workers rotate an axe and gripping hand through four chopping poses. The
view uses the authoritative harvest timer for the swing and contact chips,
so pausing freezes the action and carrying wood replaces the tool. Animation
images warm incrementally during the match opening.

## Verification

```sh
uv run python -m pytest tests/warband tests/framework/test_render3d.py -q
uv run python tools/verify_warband_art.py /tmp/warband-art
```

The native verifier uses the same registered images and MapView as gameplay.
Inspect the generated catalogs, settlement screenshots and chopping animation
after changing a recipe. Mock tests cover image registration, stable variant
selection through save/load, harvesting poses, carried logs, pause behavior,
and incremental warm-up; the PNGs establish visual quality.
