"""The map strategy sample stays paired across layouts, races and starting seats."""

import pytest

from tools import map_strategy_report
from warband.sim.rules import Layout


def test_specs_compare_the_same_pair_on_every_layout_from_both_seats() -> None:
    specs = map_strategy_report.matchup_specs(range(2000, 2002), ("rush", "boom"))
    assert len(specs) == 2 * 5 * 2
    for seed in (2000, 2001):
        by_seed = [spec for spec in specs if spec.seed == seed]
        assert {spec.layout for spec in by_seed} == {layout.value for layout in Layout}
        assert {spec.agents for spec in by_seed} == {("rush", "boom"), ("boom", "rush")}
        assert len({(spec.width, spec.height, spec.races) for spec in by_seed}) == 1
    map_strategy_report.validate_pairs(specs, ("rush", "boom"))


def test_a_refused_map_removes_its_seed_from_every_layout(monkeypatch) -> None:
    specs = map_strategy_report.matchup_specs(range(2000, 2002), ("rush", "boom"))
    monkeypatch.setattr(map_strategy_report, "playable",
                        lambda spec: not (spec.seed == 2000 and spec.layout == Layout.FOREST.value))
    paired = map_strategy_report.complete_seeds(specs)
    assert {spec.seed for spec in paired} == {2001}
    assert len(paired) == 2 * len(Layout)


def test_an_interrupted_match_file_cannot_report_skewed_scores() -> None:
    specs = map_strategy_report.matchup_specs(range(2000, 2002), ("rush", "boom"))
    with pytest.raises(ValueError, match="complete layout"):
        map_strategy_report.validate_pairs(specs[:-1], ("rush", "boom"))
