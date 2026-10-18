"""Step 7 tests: synthetic load generation, waste recovery by models."""
from __future__ import annotations

import pytest

from cmpm.baseline import (
    changepoint_regression,
    evaluate_waste_recovery,
    generate_synthetic_load,
    gradient_boosting_model,
)
from cmpm.config_loader import load_config


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def synthetic_data(cfg):
    return generate_synthetic_load(cfg)


class TestSyntheticLoad:
    def test_8760_hours(self, synthetic_data):
        assert len(synthetic_data) == 8760

    def test_waste_present(self, synthetic_data):
        assert synthetic_data["waste_load_kw"].sum() > 0

    def test_load_nonneg(self, synthetic_data):
        assert (synthetic_data["total_load_kw"] >= 0).all()

    def test_shoulder_periods_exist(self, synthetic_data):
        assert synthetic_data["is_shoulder"].sum() > 100


class TestChangePointRegression:
    def test_cvrmse_reasonable(self, synthetic_data):
        result = changepoint_regression(synthetic_data)
        assert result["cvrmse"] < 0.50

    def test_estimates_positive_waste(self, synthetic_data):
        result = changepoint_regression(synthetic_data)
        assert result["estimated_waste_pct"] > 0


class TestGradientBoosting:
    def test_cvrmse_reasonable(self, synthetic_data, cfg):
        result = gradient_boosting_model(synthetic_data, cfg)
        assert result["cvrmse"] < 0.50

    def test_feature_importances(self, synthetic_data, cfg):
        result = gradient_boosting_model(synthetic_data, cfg)
        assert "outdoor_temp" in result["feature_importances"]
        assert result["feature_importances"]["outdoor_temp"] > 0.1


class TestWasteRecovery:
    def test_evaluation_runs(self, synthetic_data, cfg):
        df = evaluate_waste_recovery(synthetic_data, cfg)
        assert len(df) == 2
        assert "bias" in df.columns

    def test_true_waste_near_12pct(self, synthetic_data, cfg):
        df = evaluate_waste_recovery(synthetic_data, cfg)
        assert 0.01 < df["true_waste_pct"].iloc[0] < 0.25
