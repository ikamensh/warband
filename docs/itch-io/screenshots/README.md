# Itch.io gameplay assets

Captured from Warband **v0.2.280**, source commit
`c9d74d8ac74dcb8f389cac8ed16e1cfa0223d5d2`, with the genuine pyglet backend,
`saga2d==0.3.18` and clean sagaforge source
`69eb6690d7a312f8814b28df3b75b07785945ff3`.

The screenshots are 1600 × 1000 native game frames normalized from Retina device
scale. The gameplay GIF is a crop of native battle frames, exported at 800 × 500,
12 frames per second for two seconds. Its color palette is limited to 96
colors for download size. No unit art, effects, interface or other imagery is
composited into the captures.

These are deliberately staged, playable game states: starting resources,
buildings, armies, visibility and camera composition are set for a readable
storefront view. Harvesting, combat, healing, spell effects and dialogue run in
the actual release. Player saves and profile data are isolated in a temporary
directory. They do not assert a naturally played match or benchmark.

| File | Content |
| --- | --- |
| `01-build-your-kingdom.png` | Human settlement, working economy, full army, genuine Town Hall card |
| `02-armies-collide.png` | Human and orc forces with ranged, cavalry, flying and siege units |
| `03-command-the-aether.png` | Flame Strike landing in that same live battle |
| `04-dwarven-winter.png` | Dwarves fighting orcs in winter, including rune golems |
| `06-the-undertow-campaign.png` | Authored Millfield briefing with Issa, Hasp and the field chart |
| `warband-battle.gif` | Two seconds of the battle and Flame Strike, cropped from the real framebuffer |

Reproduce from this source checkout with its release dependencies installed:

```sh
caffeinate -u -t 180 python3 ~/saga/tools/slot.py -- \
  uv run --no-sync python tools/capture_storefront.py /tmp/warband-storefront
```

To regenerate only the animation, append `--animation-only`. Inspect every
capture before replacing these source assets. The five PNGs and the GIF were
visually inspected; successful native captures exercise real game rendering and
public simulation orders. Temporary candidate captures are disposable and do
not belong in this directory.
