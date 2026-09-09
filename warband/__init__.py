"""Warband — a Warcraft 2-style real-time strategy game built on saga2d.

``python -m warband`` starts it.  Package layout:

* ``rules``    — data tables: terrain, units, buildings, costs, timings.
* ``path``     — A* over the tile grid.
* ``model``    — the world state, orders and the fixed-step simulation.
* ``mapgen``   — procedural maps with two bases, gold mines and forests.
* ``ai``       — the computer opponent.
* ``textures`` — ground, trees, buildings and units pre-rendered with ``sagaforge.render3d``.
* ``view``     — sprite reconciliation, fog of war and the world-space overlays.
* ``scene``    — saga2d scenes: the game, its HUD and command card, pause and help.
* ``title``    — title screen and match setup.
* ``sound``    — the sound bank: synthesised effects, cached music, the hooks scenes call.
* ``music``    — the score: a suite per race, the title's night watch, two endings, and the director that plays them by mood.
* ``instruments`` — the orchestra the music is written for.
"""
