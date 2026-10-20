"""Step 6 tests: scoring validity — weighted scores, weight stability, normalization."""
from __future__ import annotations

import numpy as np
import pytest

from cmpm.config_loader import load_config
from cmpm.scoring import (
    correlation_double_counting,
    normalization_sensitivity,
    rank_disagreement,
    reverse_engineer_subscores,
    weight_stability_analysis,
    weighted_score,
)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


class TestWeightedScore:
    def test_known_composite(self):
        sub = {"a": 100, "b": 0}
        w = {"a": 0.6, "b": 0.4}
        assert abs(weighted_score(sub, w) - 60.0) < 1e-6

    def test_equal_weights(self):
        sub = {"a": 80, "b": 60, "c": 40}
        w = {"a": 1/3, "b": 1/3, "c": 1/3}
        assert abs(weighted_score(sub, w) - 60.0) < 1e-6


class TestReverseEngineerSubscores:
    def test_reproduces_targets(self, cfg):
        projects = cfg["projects"]
        weights = cfg["score_weights"]
        targets = {pk: float(projects[pk]["strategic_score"]) for pk in projects}
        result = reverse_engineer_subscores(targets, weights)
        for pk in targets:
            composite = weighted_score(result[pk], weights)
            assert abs(composite - targets[pk]) < 1.0, (
                f"{pk}: composite={composite:.1f}, target={targets[pk]}"
            )

    def test_subscores_in_range(self, cfg):
        projects = cfg["projects"]
        weights = cfg["score_weights"]
        targets = {pk: float(projects[pk]["strategic_score"]) for pk in projects}
        result = reverse_engineer_subscores(targets, weights)
        for pk in result:
            for criterion, val in result[pk].items():
                assert 0 <= val <= 100, f"{pk}.{criterion} = {val}"


class TestWeightStability:
    def test_rank_distribution_sums_to_1(self, cfg):
        result = weight_stability_analysis(cfg)
        rd = result["rank_distribution"]
        row_sums = rd.sum(axis=1)
        np.testing.assert_allclose(row_sums, 1.0, atol=1e-6)

    def test_p_top2_bounded(self, cfg):
        result = weight_stability_analysis(cfg)
        summary = result["summary"]
        assert (summary["P_top2"] >= 0).all()
        assert (summary["P_top2"] <= 1).all()

    def test_kendall_tau_positive(self, cfg):
        result = weight_stability_analysis(cfg)
        assert result["summary"]["mean_kendall_tau"].iloc[0] > 0


class TestNormalizationSensitivity:
    def test_produces_comparison(self, cfg):
        df = normalization_sensitivity(cfg)
        assert len(df) == 3
        assert "top5_changed" in df.columns

    def test_overlap_bounded(self, cfg):
        df = normalization_sensitivity(cfg)
        assert (df["top5_overlap"] >= 0).all()
        assert (df["top5_overlap"] <= 5).all()


class TestCorrelationDoubleCounting:
    def test_vif_summary(self, cfg):
        result = correlation_double_counting(cfg)
        vif_df = result["vif_summary"]
        assert len(vif_df) == 5
        assert (vif_df["VIF"] >= 1.0).all()

    def test_effective_weights_sum_to_1(self, cfg):
        result = correlation_double_counting(cfg)
        vif_df = result["vif_summary"]
        assert abs(vif_df["effective_weight"].sum() - 1.0) < 1e-6


class TestRankDisagreement:
    def test_produces_rankings(self, cfg):
        df = rank_disagreement(cfg)
        assert len(df) == 5
        assert "score_rank" in df.columns
        assert "pi_rank" in df.columns

    def test_tau_in_range(self, cfg):
        df = rank_disagreement(cfg)
        for key in ["tau_score_vs_pi", "tau_score_vs_npv", "tau_pi_vs_npv"]:
            tau = df.attrs[key]
            assert -1 <= tau <= 1
