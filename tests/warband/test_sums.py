"""The compiled simulation adds as the source does: no module of ``fastsim.MODULES`` calls the built-in ``sum``, whose
float addition differs compiled (``model.plain_sum`` says how), and the plain loop that replaces it is the
uncompensated one."""

import ast
from pathlib import Path

import pytest

from warband.league import fastsim
from warband.sim.model import int_sum, plain_sum

PACKAGE = Path(fastsim.__file__).resolve().parents[1]


@pytest.mark.parametrize("module", fastsim.MODULES)
def test_a_compiled_module_calls_no_bare_sum(module: str) -> None:
    path = PACKAGE / fastsim.source(module)
    calls = [node.lineno for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "sum"]
    assert not calls, (f"warband/{fastsim.source(module)}, lines {calls}: sum() adds floats differently compiled; "
                       "use model.plain_sum for floats, model.int_sum for integers")


def test_plain_sum_adds_left_to_right_without_compensation() -> None:
    cancelling = [1e16, 1.0, -1e16]  # the 1.0 is below 1e16's last bit: plain addition loses it, compensation keeps it
    assert plain_sum(cancelling) == (1e16 + 1.0) + -1e16 == 0.0
    assert sum(cancelling) == 1.0
    assert plain_sum(iter([0.1, 0.2, 0.3])) == 0.1 + 0.2 + 0.3 != 0.6
    assert plain_sum([]) == 0.0


def test_int_sum_is_the_exact_total() -> None:
    assert int_sum(1 for n in range(10) if n % 3) == 6
    assert int_sum([2**62, 2**62, -5]) == 2**63 - 5
    assert int_sum([]) == 0
