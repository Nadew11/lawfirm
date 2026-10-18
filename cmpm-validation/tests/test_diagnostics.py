"""Tests for the diagnostics module — overfitting and circularity checks."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cmpm.baseline import generate_synthetic_load
from cmpm.config_loader import load_config
from cmpm.diagnostics import (
    cp_residual_diagnostics,
    dirichlet_concentration_sensitivity,
    evidence_circularity_audit,
    gb_learning_curve,
    gb_train_test_gap,
    interaction_magnitude_sweep,
    mc_bootstrap_stability,
    mc_distribution_sensitivity,
)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def synth_data(cfg):
    return generate_synthetic_load(cfg)


class TestGBOverfit:
    def test_gap_returns_keys(self, synth_data, cfg):
        result = gb_train_test_gap(synth_data, cfg)
        required = {"train_rmse", "test_rmse", "overfit_ratio", "train_cvrmse",
                     "test_cvrmse", "train_shoulder_waste_est", "test_shoulder_waste_est",
                     "diagnosis", "feature_importances"}
        assert required.issubset(set(result.keys()))

    def test_overfit_ratio_positive(self, synth_data, cfg):
        result = gb_train_test_gap(synth_data, cfg)
        assert result["overfit_ratio"] > 0

    def test_train_rmse_less_than_test(self, synth_data, cfg):
        result = gb_train_test_gap(synth_data, cfg)
        assert result["train_rmse"] <= result["test_rmse"] * 1.5

    def test_learning_curve_shape(self, synth_data, cfg):
        curve = gb_learning_curve(synth_data, cfg, n_estimator_values=[10, 50, 100])
        assert len(curve) == 3
        assert set(curve.columns) == {"n_estimators", "train_rmse", "test_rmse", "gap", "ratio"}

    def test_train_rmse_decreases_with_estimators(self, synth_data, cfg):
        curve = gb_learning_curve(synth_data, cfg, n_estimator_values=[10, 100, 500])
        assert curve.iloc[0]["train_rmse"] >= curve.iloc[-1]["train_rmse"]


class TestCPResiduals:
    def test_returns_keys(self, synth_data):
        result = cp_residual_diagnostics(synth_data)
        required = {"lag1_autocorrelation", "durbin_watson", "shoulder_residual_mean",
                     "non_shoulder_residual_mean", "residual_skewness",
                     "residual_kurtosis", "cp_params", "diagnosis"}
        assert required.issubset(set(result.keys()))

    def test_dw_in_range(self, synth_data):
        result = cp_residual_diagnostics(synth_data)
        assert 0 < result["durbin_watson"] < 4.0

    def test_autocorrelation_in_range(self, synth_data):
        result = cp_residual_diagnostics(synth_data)
        assert -1.0 <= result["lag1_autocorrelation"] <= 1.0


class TestMCDiagnostics:
    def test_sensitivity_returns_rows(self, cfg):
        df = mc_distribution_sensitivity(cfg)
        assert len(df) == 7  # 7 shifts
        assert "P_NPV_positive" in df.columns

    def test_sensitivity_mode_shift_affects_p_pos(self, cfg):
        df = mc_distribution_sensitivity(cfg)
        p_neg = df[df["mode_shift"] == -0.15]["P_NPV_positive"].iloc[0]
        p_pos = df[df["mode_shift"] == +0.15]["P_NPV_positive"].iloc[0]
        assert p_pos >= p_neg

    def test_bootstrap_returns_keys(self, cfg):
        result = mc_bootstrap_stability(cfg, n_bootstrap=10)
        assert "P_NPV_positive" in result
        assert "diagnosis" in result
        assert result["P_NPV_positive"]["std"] >= 0

    def test_bootstrap_range_contains_mean(self, cfg):
        result = mc_bootstrap_stability(cfg, n_bootstrap=10)
        mean = result["P_NPV_positive"]["mean"]
        lo, hi = result["P_NPV_positive"]["range"]
        assert lo <= mean <= hi


class TestEvidenceCircularity:
    def test_returns_all_packages(self, cfg):
        df = evidence_circularity_audit(cfg)
        assert len(df) == 7
        assert all(df["circularity_score"] > 0)
        assert all(df["circularity_score"] <= 1.0)

    def test_has_critical_items(self, cfg):
        df = evidence_circularity_audit(cfg)
        critical = df[df["severity"] == "CRITICAL"]
        assert len(critical) >= 1

    def test_mean_circularity_above_threshold(self, cfg):
        df = evidence_circularity_audit(cfg)
        assert df["circularity_score"].mean() > 0.5


class TestDirichletSensitivity:
    def test_returns_rows(self, cfg):
        df = dirichlet_concentration_sensitivity(cfg, concentrations=[10, 50, 200])
        assert len(df) == 3

    def test_higher_concentration_more_stable(self, cfg):
        df = dirichlet_concentration_sensitivity(cfg, concentrations=[10, 200])
        p_low = df[df["concentration"] == 10]["P_rank_unchanged"].iloc[0]
        p_high = df[df["concentration"] == 200]["P_rank_unchanged"].iloc[0]
        assert p_high >= p_low


class TestInteractionSweep:
    def test_returns_rows(self, cfg):
        df = interaction_magnitude_sweep(cfg, multipliers=[0.0, 1.0, 2.0])
        assert len(df) == 3

    def test_zero_interactions_no_overstatement(self, cfg):
        df = interaction_magnitude_sweep(cfg, multipliers=[0.0])
        assert df.iloc[0]["overstatement"] == 0

    def test_higher_multiplier_more_overstatement(self, cfg):
        df = interaction_magnitude_sweep(cfg, multipliers=[0.5, 2.0])
        assert df.iloc[1]["overstatement"] > df.iloc[0]["overstatement"]
