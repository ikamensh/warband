"""Warband — a Warcraft 2-style real-time strategy game built on saga2d.

``python -m warband`` starts it.  The package's folders go by what their modules are, lowest first:

* ``sim``     — the rules and the simulation the online authority runs; imports nothing above it.
* ``brains``  — the computer players.
* ``records`` — the profile, the local top ten and replays.
* ``league``  — the arena, the balance league and the compiled simulation, for measuring the game.
* ``online``  — the server's authoritative match and a headless online player.
* ``art`` and ``audio`` — what the game looks and sounds like.
* ``ui``      — the saga2d scenes: the match and its HUD, the title and every screen.
* ``story``   — the campaign.

``tests/warband/test_layers.py`` holds each folder to what it may import.
"""
