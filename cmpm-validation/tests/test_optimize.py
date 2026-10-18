"""Step 5 tests: MILP correctness, budget sweep, constraint enforcement."""
from __future__ import annotations

import pytest

from cmpm.config_loader import load_config
from cmpm.optimize import (
    budget_sweep,
    efficient_frontier,
    heuristic_greedy_by_score,
    milp_optimize,
    multi_year_milp,
    shadow_prices,
)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


class TestMILPvsBruteForce:
    """MILP solution must match brute-force enumeration."""

    @pytest.mark.parametrize("budget", [500_000, 1_000_000, 1_500_000, 2_000_000, 2_500_000])
    def test_milp_matches_enum(self, cfg, budget):
        result = milp_optimize(cfg, budget)
        assert abs(result["milp_npv"] - result["enum_npv"]) < 100, (
            f"Budget={budget}: MILP NPV={result['milp_npv']:.0f} vs "
            f"enum NPV={result['enum_npv']:.0f}"
        )

    def test_budget_respected(self, cfg):
        budget = 1_000_000
        result = milp_optimize(cfg, budget)
        projects = cfg["projects"]
        total = sum(projects[k]["capex"] for k in result["milp_selected"])
        assert total <= budget + 1


class TestConstraints:
    """Dependency and mutual-exclusion constraints are enforced."""

    def test_dependency_enforced(self, cfg):
        result = milp_optimize(cfg, 2_500_000, apply_dependency=True)
        dep = cfg["optimization"]["dependency"]
        for proj, req in dep.items():
            if proj in result["milp_selected"]:
                assert req in result["milp_selected"], (
                    f"{proj} selected without required {req}"
                )

    def test_exclusion_enforced(self, cfg):
        result = milp_optimize(cfg, 2_500_000, apply_exclusion=True)
        for group in cfg["optimization"]["mutual_exclusion"]:
            count = sum(1 for p in group if p in result["milp_selected"])
            assert count <= 1, f"Mutual exclusion violated: {group}"


class TestBudgetSweep:
    def test_sweep_produces_rows(self, cfg):
        df = budget_sweep(cfg)
        assert len(df) > 10

    def test_optimal_ge_heuristic(self, cfg):
        df = budget_sweep(cfg)
        assert (df["optimal_npv"] >= df["heuristic_npv"] - 1).all()


class TestShadowPrices:
    def test_constraint_costs_nonneg(self, cfg):
        df = shadow_prices(cfg, 2_000_000)
        assert (df["cost"] >= -1).all()


class TestMultiYear:
    def test_runs_and_selects(self, cfg):
        result = multi_year_milp(cfg)
        assert len(result["selected"]) > 0
        assert result["total_npv"] > 0


class TestEfficientFrontier:
    def test_frontier(self, cfg):
        df = budget_sweep(cfg)
        ef = efficient_frontier(df)
        assert len(ef["frontier_budgets"]) > 0
        assert ef["flatten_budget"] > 0
