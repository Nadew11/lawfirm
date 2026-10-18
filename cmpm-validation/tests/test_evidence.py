"""Tests for the evidence module — synthetic data generators and analysis functions."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cmpm.config_loader import load_config
from cmpm.evidence import (
    analyze_maintenance_evidence,
    analyze_submetered_waste,
    calibrate_savings_distribution,
    generate_all_evidence,
    generate_interaction_analysis,
    generate_maintenance_records,
    generate_mv_comparison,
    generate_submetered_data,
    generate_utility_bills,
    risk_tolerance_assessment,
    validate_benefits_against_bills,
)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def seed(cfg):
    return cfg["general"]["random_seed"]


class TestUtilityBills:
    def test_shape(self, cfg, seed):
        df = generate_utility_bills(cfg, seed)
        assert len(df) == 5 * 24  # 5 buildings x 24 months

    def test_columns(self, cfg, seed):
        df = generate_utility_bills(cfg, seed)
        expected = {"building", "year", "month", "total_kwh", "efficient_kwh",
                    "waste_kwh", "total_cost", "addressable_savings_monthly"}
        assert set(df.columns) == expected

    def test_all_buildings_present(self, cfg, seed):
        df = generate_utility_bills(cfg, seed)
        assert set(df["building"].unique()) == set(cfg["projects"].keys())

    def test_total_exceeds_efficient(self, cfg, seed):
        df = generate_utility_bills(cfg, seed)
        assert (df["total_kwh"] >= df["efficient_kwh"]).all()

    def test_positive_values(self, cfg, seed):
        df = generate_utility_bills(cfg, seed)
        assert (df["total_kwh"] > 0).all()
        assert (df["total_cost"] > 0).all()

    def test_reproducible(self, cfg, seed):
        df1 = generate_utility_bills(cfg, seed)
        df2 = generate_utility_bills(cfg, seed)
        pd.testing.assert_frame_equal(df1, df2)


class TestBillValidation:
    def test_validation_all_projects(self, cfg, seed):
        bills = generate_utility_bills(cfg, seed)
        val = validate_benefits_against_bills(bills, cfg)
        assert len(val) == len(cfg["projects"])

    def test_ratio_is_positive(self, cfg, seed):
        bills = generate_utility_bills(cfg, seed)
        val = validate_benefits_against_bills(bills, cfg)
        assert (val["ratio_claimed_to_derived"] > 0).all()

    def test_flag_values(self, cfg, seed):
        bills = generate_utility_bills(cfg, seed)
        val = validate_benefits_against_bills(bills, cfg)
        assert set(val["flag"].unique()).issubset({"OK", "OVERESTIMATE", "UNDERESTIMATE"})


class TestMVComparison:
    def test_20_peers(self, cfg, seed):
        df = generate_mv_comparison(cfg, seed)
        assert len(df) == 20

    def test_ratio_range(self, cfg, seed):
        df = generate_mv_comparison(cfg, seed)
        assert (df["actual_to_predicted_ratio"] >= 0.30).all()
        assert (df["actual_to_predicted_ratio"] < 2.0).all()

    def test_median_near_85pct(self, cfg, seed):
        df = generate_mv_comparison(cfg, seed)
        median_ratio = df["actual_to_predicted_ratio"].median()
        assert 0.60 < median_ratio < 1.10

    def test_reproducible(self, cfg, seed):
        df1 = generate_mv_comparison(cfg, seed)
        df2 = generate_mv_comparison(cfg, seed)
        pd.testing.assert_frame_equal(df1, df2)


class TestCalibrateSavings:
    def test_keys(self, cfg, seed):
        mv = generate_mv_comparison(cfg, seed)
        cal = calibrate_savings_distribution(mv)
        assert set(cal.keys()) == {"low", "mode", "high", "mean", "std", "n_projects"}

    def test_low_lt_mode_lt_high(self, cfg, seed):
        mv = generate_mv_comparison(cfg, seed)
        cal = calibrate_savings_distribution(mv)
        assert cal["low"] < cal["mode"] < cal["high"]

    def test_n_projects(self, cfg, seed):
        mv = generate_mv_comparison(cfg, seed)
        cal = calibrate_savings_distribution(mv)
        assert cal["n_projects"] == 20


class TestMaintenanceRecords:
    def test_contains_both_event_types(self, cfg, seed):
        df = generate_maintenance_records(cfg, seed)
        assert "routine_maintenance" in df["event_type"].values
        assert "major_failure" in df["event_type"].values

    def test_10_years_of_routine(self, cfg, seed):
        df = generate_maintenance_records(cfg, seed)
        routine = df[df["event_type"] == "routine_maintenance"]
        assert len(routine) == 10 * 12  # 12 per year for 10 years

    def test_positive_costs(self, cfg, seed):
        df = generate_maintenance_records(cfg, seed)
        assert (df["cost"] > 0).all()

    def test_reproducible(self, cfg, seed):
        df1 = generate_maintenance_records(cfg, seed)
        df2 = generate_maintenance_records(cfg, seed)
        pd.testing.assert_frame_equal(df1, df2)


class TestMaintenanceAnalysis:
    def test_keys(self, cfg, seed):
        records = generate_maintenance_records(cfg, seed)
        analysis = analyze_maintenance_evidence(records)
        required = {"years_of_data", "total_routine_events", "annual_routine_cost",
                     "total_failures", "failure_rate_per_year", "avg_failure_cost",
                     "annual_failure_ev", "estimated_maintenance_reduction",
                     "estimated_avoided_failure_ev", "total_evidence_based_benefit",
                     "config_claimed_nonenergy_benefit"}
        assert required.issubset(set(analysis.keys()))

    def test_failure_rate_reasonable(self, cfg, seed):
        records = generate_maintenance_records(cfg, seed)
        analysis = analyze_maintenance_evidence(records)
        assert 0 <= analysis["failure_rate_per_year"] <= 1.0

    def test_benefit_decomposition_positive(self, cfg, seed):
        records = generate_maintenance_records(cfg, seed)
        analysis = analyze_maintenance_evidence(records)
        assert analysis["estimated_maintenance_reduction"] > 0
        assert analysis["total_evidence_based_benefit"] > 0


class TestInteractionAnalysis:
    def test_four_interactions(self, cfg, seed):
        df = generate_interaction_analysis(cfg, seed)
        assert len(df) == 4

    def test_reduction_positive(self, cfg, seed):
        df = generate_interaction_analysis(cfg, seed)
        assert (df["modeled_reduction_pct"] > 0).all()

    def test_sources_and_targets(self, cfg, seed):
        df = generate_interaction_analysis(cfg, seed)
        assert "lab_ventilation" in df["source"].values
        assert "central_plant" in df["target"].values


class TestSubmeteredData:
    def test_8760_hours(self, cfg, seed):
        df = generate_submetered_data(cfg, seed)
        assert len(df) == 8760

    def test_columns(self, cfg, seed):
        df = generate_submetered_data(cfg, seed)
        expected = {"hour", "outdoor_temp", "heating_kw", "cooling_kw",
                    "simultaneous_flag", "is_shoulder", "waste_heating_kw", "waste_cooling_kw"}
        assert set(df.columns) == expected

    def test_nonneg_energy(self, cfg, seed):
        df = generate_submetered_data(cfg, seed)
        assert (df["heating_kw"] >= 0).all()
        assert (df["cooling_kw"] >= 0).all()

    def test_simultaneous_hours_exist(self, cfg, seed):
        df = generate_submetered_data(cfg, seed)
        assert df["simultaneous_flag"].sum() > 0


class TestSubmeteredWasteAnalysis:
    def test_keys(self, cfg, seed):
        df = generate_submetered_data(cfg, seed)
        result = analyze_submetered_waste(df)
        required = {"total_hours", "simultaneous_hours", "simultaneous_pct",
                     "total_energy_kwh", "wasted_energy_kwh", "waste_fraction",
                     "shoulder_waste_kwh", "detection_method", "model_required"}
        assert required.issubset(set(result.keys()))

    def test_waste_detected(self, cfg, seed):
        df = generate_submetered_data(cfg, seed)
        result = analyze_submetered_waste(df)
        assert result["waste_fraction"] > 0.01  # should be detectable

    def test_no_model_required(self, cfg, seed):
        df = generate_submetered_data(cfg, seed)
        result = analyze_submetered_waste(df)
        assert result["model_required"] is False

    def test_shoulder_waste_positive(self, cfg, seed):
        df = generate_submetered_data(cfg, seed)
        result = analyze_submetered_waste(df)
        assert result["shoulder_waste_kwh"] > 0


class TestRiskTolerance:
    def test_returns_dataframe(self, cfg, seed):
        mc_stats = pd.DataFrame([
            {"project": "lab_ventilation", "expected_shortfall_10": -50_000,
             "P_NPV_positive": 0.95, "P_payback_lt4": 0.80},
            {"project": "central_plant", "expected_shortfall_10": -200_000,
             "P_NPV_positive": 0.80, "P_payback_lt4": 0.40},
            {"project": "dorm_occupancy", "expected_shortfall_10": -100_000,
             "P_NPV_positive": 0.70, "P_payback_lt4": 0.30},
        ])
        result = risk_tolerance_assessment(cfg, mc_stats)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3

    def test_recommendation_values(self, cfg, seed):
        mc_stats = pd.DataFrame([
            {"project": "lab_ventilation", "expected_shortfall_10": -10_000,
             "P_NPV_positive": 0.98, "P_payback_lt4": 0.90},
        ])
        result = risk_tolerance_assessment(cfg, mc_stats)
        assert result.iloc[0]["recommendation"] in ("APPROVE", "DEFER/MITIGATE")

    def test_high_risk_deferred(self, cfg, seed):
        mc_stats = pd.DataFrame([
            {"project": "dorm_occupancy", "expected_shortfall_10": -500_000,
             "P_NPV_positive": 0.40, "P_payback_lt4": 0.10},
        ])
        result = risk_tolerance_assessment(cfg, mc_stats)
        assert result.iloc[0]["recommendation"] == "DEFER/MITIGATE"
        assert not result.iloc[0]["overall_risk_acceptable"]


class TestGenerateAllEvidence:
    def test_all_keys_present(self, cfg):
        result = generate_all_evidence(cfg)
        expected_keys = {"utility_bills", "bill_validation", "mv_data",
                          "calibrated_distribution", "maintenance_records",
                          "maintenance_analysis", "interaction_engineering",
                          "submetered_data", "submeter_analysis"}
        assert expected_keys.issubset(set(result.keys()))

    def test_all_dataframes(self, cfg):
        result = generate_all_evidence(cfg)
        for k in ("utility_bills", "bill_validation", "mv_data",
                   "maintenance_records", "interaction_engineering", "submetered_data"):
            assert isinstance(result[k], pd.DataFrame), f"{k} should be a DataFrame"

    def test_calibrated_distribution_is_dict(self, cfg):
        result = generate_all_evidence(cfg)
        assert isinstance(result["calibrated_distribution"], dict)

    def test_maintenance_analysis_is_dict(self, cfg):
        result = generate_all_evidence(cfg)
        assert isinstance(result["maintenance_analysis"], dict)

    def test_submeter_analysis_is_dict(self, cfg):
        result = generate_all_evidence(cfg)
        assert isinstance(result["submeter_analysis"], dict)


class TestCalibrateConfig:
    def test_v3_has_different_mc_savings(self, cfg):
        from cmpm.evidence import calibrate_config_from_evidence
        evidence = generate_all_evidence(cfg)
        v3 = calibrate_config_from_evidence(cfg, evidence)
        assert v3["monte_carlo"]["savings_triangular"] != cfg["monte_carlo"]["savings_triangular"]

    def test_v3_electrical_benefit_differs(self, cfg):
        from cmpm.evidence import calibrate_config_from_evidence
        evidence = generate_all_evidence(cfg)
        v3 = calibrate_config_from_evidence(cfg, evidence)
        assert v3["projects"]["electrical_monitoring"]["annual_benefit"] != \
               cfg["projects"]["electrical_monitoring"]["annual_benefit"]

    def test_v3_does_not_mutate_original(self, cfg):
        from cmpm.evidence import calibrate_config_from_evidence
        original_benefit = cfg["projects"]["electrical_monitoring"]["annual_benefit"]
        evidence = generate_all_evidence(cfg)
        _ = calibrate_config_from_evidence(cfg, evidence)
        assert cfg["projects"]["electrical_monitoring"]["annual_benefit"] == original_benefit


class TestEvidenceComparison:
    def test_returns_dataframe(self, cfg):
        from cmpm.evidence import calibrate_config_from_evidence, evidence_comparison_table
        evidence = generate_all_evidence(cfg)
        v3 = calibrate_config_from_evidence(cfg, evidence)
        comp = evidence_comparison_table(cfg, v3, evidence)
        assert isinstance(comp, pd.DataFrame)
        assert len(comp) > 5  # at least MC + electrical + failure + interactions


class TestDecisionRules:
    def test_returns_dataframe(self, cfg):
        from cmpm.evidence import generate_decision_rules
        evidence = generate_all_evidence(cfg)
        mc_stats = pd.DataFrame([
            {"project": "lab_ventilation", "expected_shortfall_10": -50_000,
             "P_NPV_positive": 0.95, "P_payback_lt4": 0.80},
            {"project": "central_plant", "expected_shortfall_10": -200_000,
             "P_NPV_positive": 0.80, "P_payback_lt4": 0.40},
        ])
        risk = risk_tolerance_assessment(cfg, mc_stats)
        decisions = generate_decision_rules(risk, evidence)
        assert isinstance(decisions, pd.DataFrame)
        assert len(decisions) == 2

    def test_decision_values(self, cfg):
        from cmpm.evidence import generate_decision_rules
        evidence = generate_all_evidence(cfg)
        mc_stats = pd.DataFrame([
            {"project": "lab_ventilation", "expected_shortfall_10": -10_000,
             "P_NPV_positive": 0.99, "P_payback_lt4": 0.95},
        ])
        risk = risk_tolerance_assessment(cfg, mc_stats)
        decisions = generate_decision_rules(risk, evidence)
        assert decisions.iloc[0]["decision"] in ("APPROVE", "APPROVE-WITH-CONDITIONS", "DEFER/MITIGATE")
