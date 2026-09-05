"""Where Warband's sound events go.

The scene calls :func:`play_sound` with an event name; ``__main__`` points
:data:`sound_hook` at a bank so it is heard, while tests leave it ``None``.
"""

from __future__ import annotations

from typing import Callable

#: ``play_sound(name)`` forwards here when set; ``None`` is silent.
sound_hook: Callable[[str], None] | None = None
volume_hook: Callable[[str, float], None] | None = None

EVENTS = (
    "select", "command", "attack_command", "hit", "arrow", "death", "chop", "gold", "build_start", "built", "trained",
    "under_attack", "error", "button", "victory", "defeat", "destroyed",
)


def play_sound(name: str) -> None:
    if sound_hook is not None:
        sound_hook(name)


def apply_volumes(music: float, sfx: float) -> None:
    if volume_hook is not None:
        volume_hook("music", music)
        volume_hook("sfx", sfx)
