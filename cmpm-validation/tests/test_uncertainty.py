"""Step 3 tests: Monte Carlo reproducibility, distribution shapes, correlation."""
from __future__ import annotations

import numpy as np
import pytest

from cmpm.config_loader import load_config
from cmpm.uncertainty import (
    compute_mc_stats,
    correlation_impact,
    electrical_avoided_failure_mc,
    generate_correlated_draws,
    monte_carlo_npv,
    monte_carlo_payback,
    run_monte_carlo_all_projects,
)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


class TestSeedReproducibility:
    """Same seed -> identical draws."""

    def test_same_seed_same_draws(self, cfg):
        mc = cfg["monte_carlo"]
        d1 = generate_correlated_draws(500, mc["correlation_rho"], 42, mc)
        d2 = generate_correlated_draws(500, mc["correlation_rho"], 42, mc)
        np.testing.assert_array_equal(d1["savings_mult"], d2["savings_mult"])
        np.testing.assert_array_equal(d1["capex_mult"], d2["capex_mult"])

    def test_different_seed_different_draws(self, cfg):
        mc = cfg["monte_carlo"]
        d1 = generate_correlated_draws(500, mc["correlation_rho"], 42, mc)
        d2 = generate_correlated_draws(500, mc["correlation_rho"], 99, mc)
        assert not np.allclose(d1["savings_mult"], d2["savings_mult"])


class TestDistributionShapes:
    """Check that generated draws have expected statistical properties."""

    def test_savings_triangular_bounds(self, cfg):
        mc = cfg["monte_carlo"]
        draws = generate_correlated_draws(10000, mc["correlation_rho"], 42, mc)
        lo, mode, hi = mc["savings_triangular"]
        assert draws["savings_mult"].min() >= lo - 0.01
        assert draws["savings_mult"].max() <= hi + 0.01

    def test_capex_lognormal_right_skewed(self, cfg):
        mc = cfg["monte_carlo"]
        draws = generate_correlated_draws(10000, mc["correlation_rho"], 42, mc)
        assert np.mean(draws["capex_mult"]) > np.median(draws["capex_mult"])

    def test_delay_distribution(self, cfg):
        mc = cfg["monte_carlo"]
        draws = generate_correlated_draws(10000, mc["correlation_rho"], 42, mc)
        unique, counts = np.unique(draws["delay_years"], return_counts=True)
        fracs = dict(zip(unique, counts / len(draws["delay_years"])))
        assert abs(fracs.get(0, 0) - 0.6) < 0.05
        assert abs(fracs.get(1, 0) - 0.3) < 0.05
        assert abs(fracs.get(2, 0) - 0.1) < 0.05

    def test_discount_rate_bounds(self, cfg):
        mc = cfg["monte_carlo"]
        draws = generate_correlated_draws(10000, mc["correlation_rho"], 42, mc)
        lo, _, hi = mc["discount_triangular"]
        assert draws["discount_rate"].min() >= lo - 0.001
        assert draws["discount_rate"].max() <= hi + 0.001


class TestCorrelation:
    """Gaussian copula should induce the specified correlation."""

    def test_negative_correlation(self, cfg):
        mc = cfg["monte_carlo"]
        draws = generate_correlated_draws(50000, -0.2, 42, mc)
        rho_actual = np.corrcoef(draws["savings_mult"], draws["capex_mult"])[0, 1]
        assert -0.35 < rho_actual < -0.05, f"Got rho={rho_actual:.3f}"

    def test_zero_correlation(self, cfg):
        mc = cfg["monte_carlo"]
        draws = generate_correlated_draws(50000, 0.0, 42, mc)
        rho_actual = np.corrcoef(draws["savings_mult"], draws["capex_mult"])[0, 1]
        assert -0.05 < rho_actual < 0.05, f"Got rho={rho_actual:.3f}"


class TestElectricalAvoided:
    """Avoided-failure model sanity checks."""

    def test_full_greater_than_energy_only(self, cfg):
        elec_cfg = cfg["electrical_project"]
        mc_cfg = cfg["monte_carlo"]
        result = electrical_avoided_failure_mc(elec_cfg, mc_cfg, 5000, 42)
        assert np.mean(result["benefit_full"]) > np.mean(result["benefit_energy_only"])

    def test_avoided_failure_mean_near_expected(self, cfg):
        elec_cfg = cfg["electrical_project"]
        mc_cfg = cfg["monte_carlo"]
        result = electrical_avoided_failure_mc(elec_cfg, mc_cfg, 50000, 42)
        expected_ev = elec_cfg["failure_probability"] * elec_cfg["failure_consequence"]
        actual_mean = np.mean(result["avoided_failure_per_year"])
        assert abs(actual_mean - expected_ev) / expected_ev < 0.15


class TestMCStats:
    """compute_mc_stats correctness."""

    def test_percentile_ordering(self):
        npvs = np.random.default_rng(42).normal(500_000, 100_000, 10000)
        stats = compute_mc_stats(npvs)
        assert stats["P10"] < stats["P50"] < stats["P90"]

    def test_prob_positive_for_mostly_positive(self):
        npvs = np.random.default_rng(42).normal(500_000, 100_000, 10000)
        stats = compute_mc_stats(npvs)
        assert stats["P_NPV_positive"] > 0.99

    def test_expected_shortfall_less_than_p10(self):
        npvs = np.random.default_rng(42).normal(500_000, 100_000, 10000)
        stats = compute_mc_stats(npvs)
        assert stats["expected_shortfall_10"] <= stats["P10"]


class TestCorrelationImpact:
    """Correlation vs independence comparison runs without error."""

    def test_runs(self, cfg):
        result = correlation_impact(cfg, "lab_ventilation")
        assert "correlated" in result
        assert "independent" in result
        assert "P50" in result["correlated"]
