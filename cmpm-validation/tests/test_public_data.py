"""Tests for cmpm.public_data — government data integration."""
from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from cmpm.public_data import (
    ASHRAE_EQUIPMENT_LIFE,
    ASHRAE_OM_PCT,
    CBECS_ELECTRICITY_EUI,
    CBECS_SITE_EUI,
    DOE_ESPC_MV,
    EIA_COMMERCIAL_RATES,
    IEEE_EQUIPMENT_RELIABILITY,
    apply_public_data_to_config,
    building_eui_comparison,
    generate_public_data_report,
    get_campus_system_failure_rate,
    get_cbecs_electricity_eui,
    get_cbecs_eui,
    get_eia_escalation_rate,
    get_eia_rate,
    get_mv_realization_distribution,
    kbtu_to_kwh,
)
from cmpm.config_loader import load_config


@pytest.fixture
def cfg() -> dict[str, Any]:
    return load_config()


class TestEIA:
    def test_rate_il_is_reasonable(self):
        rate = get_eia_rate("IL")
        assert 0.05 < rate < 0.20

    def test_rate_us_is_reasonable(self):
        rate = get_eia_rate("US")
        assert 0.05 < rate < 0.20

    def test_rate_returns_dollars_not_cents(self):
        rate = get_eia_rate("IL")
        assert rate < 1.0

    def test_escalation_rate_positive(self):
        esc = get_eia_escalation_rate("IL")
        assert esc > -0.05
        assert esc < 0.10

    def test_rates_cover_multiple_years(self):
        assert len(EIA_COMMERCIAL_RATES["IL"]) >= 10
        assert len(EIA_COMMERCIAL_RATES["US"]) >= 10

    def test_unknown_state_falls_back_to_us(self):
        rate = get_eia_rate("XX")
        us_rate = get_eia_rate("US")
        assert rate == us_rate


class TestCBECS:
    def test_eui_college_has_required_fields(self):
        eui = get_cbecs_eui("college_university")
        assert "p50" in eui
        assert "mean" in eui
        assert "n" in eui
        assert eui["n"] > 0

    def test_eui_percentiles_ordered(self):
        for btype in CBECS_SITE_EUI:
            data = CBECS_SITE_EUI[btype]
            assert data["p10"] <= data["p25"] <= data["p50"] <= data["p75"] <= data["p90"]

    def test_electricity_eui_positive(self):
        for btype in CBECS_ELECTRICITY_EUI:
            data = CBECS_ELECTRICITY_EUI[btype]
            assert data["mean"] > 0
            assert data["median"] > 0

    def test_lab_eui_higher_than_classroom(self):
        lab = CBECS_SITE_EUI["laboratory"]["mean"]
        classroom = CBECS_SITE_EUI["classroom"]["mean"]
        assert lab > classroom

    def test_kbtu_to_kwh_conversion(self):
        assert abs(kbtu_to_kwh(1) - 0.293071) < 0.001
        assert abs(kbtu_to_kwh(100) - 29.3071) < 0.01


class TestDOE:
    def test_mv_realization(self):
        mv = get_mv_realization_distribution()
        assert mv["low"] < mv["mode"] < mv["high"]
        assert mv["mode"] >= 0.95

    def test_espc_data_has_required_fields(self):
        assert DOE_ESPC_MV["n_reports"] == 205
        assert DOE_ESPC_MV["n_projects"] == 200
        assert DOE_ESPC_MV["site_energy_realization_pct"] > 1.0


class TestIEEE:
    def test_transformer_failure_rate(self):
        t = IEEE_EQUIPMENT_RELIABILITY["transformer"]
        assert t["failure_rate_per_year"] < 0.05
        assert t["mtbf_years"] > 50

    def test_switchgear_failure_rate(self):
        s = IEEE_EQUIPMENT_RELIABILITY["switchgear_480v_bare_bus"]
        assert s["failure_rate_per_year"] < 0.05

    def test_campus_system_failure_rate(self):
        result = get_campus_system_failure_rate()
        assert 0.01 < result["failure_probability_per_year"] < 0.20
        assert result["avg_failure_cost_estimate"] > 0

    def test_utility_most_unreliable(self):
        utility = IEEE_EQUIPMENT_RELIABILITY["utility_mv_source"]["failure_rate_per_year"]
        transformer = IEEE_EQUIPMENT_RELIABILITY["transformer"]["failure_rate_per_year"]
        assert utility > transformer


class TestASHRAE:
    def test_equipment_life_positive(self):
        for equip, data in ASHRAE_EQUIPMENT_LIFE.items():
            assert data["median_years"] > 0
            assert data["range"][0] < data["range"][1]

    def test_om_pct_reasonable(self):
        for system, pct in ASHRAE_OM_PCT.items():
            if system == "source":
                continue
            assert 0 < pct < 0.10


class TestApplyPublicData:
    def test_produces_modified_config(self, cfg):
        cfg_pub = apply_public_data_to_config(cfg)
        assert "_public_data_changes" in cfg_pub
        assert len(cfg_pub["_public_data_changes"]) > 0

    def test_escalation_rate_changed(self, cfg):
        cfg_pub = apply_public_data_to_config(cfg)
        assert cfg_pub["frictions"]["energy_escalation_rate"] != 0.02

    def test_savings_distribution_changed(self, cfg):
        cfg_pub = apply_public_data_to_config(cfg)
        tri = cfg_pub["monte_carlo"]["savings_triangular"]
        assert tri[0] == 0.80
        assert tri[1] == 1.00
        assert tri[2] == 1.15

    def test_failure_rate_from_ieee(self, cfg):
        cfg_pub = apply_public_data_to_config(cfg)
        fr = cfg_pub["electrical_project"]["failure_probability"]
        assert 0.01 < fr < 0.20


class TestBuildingEUIComparison:
    def test_produces_dataframe(self, cfg):
        df = building_eui_comparison(cfg)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == len(cfg["projects"])
        assert "cbecs_eui_mean_kbtu" in df.columns

    def test_lab_maps_to_laboratory(self, cfg):
        df = building_eui_comparison(cfg)
        lab = df[df["project"] == "lab_ventilation"].iloc[0]
        assert lab["cbecs_type"] == "laboratory"


class TestReport:
    def test_report_is_string(self, cfg):
        cfg_pub = apply_public_data_to_config(cfg)
        report = generate_public_data_report(cfg_pub)
        assert isinstance(report, str)
        assert "EIA" in report
        assert "CBECS" in report
        assert "IEEE" in report
        assert "DOE" in report


class TestRateNormalization:
    def test_ma_rate_higher_than_il(self):
        from cmpm.public_data import get_eia_rate
        il = get_eia_rate("IL")
        ma = get_eia_rate("MA")
        assert ma > il * 1.5  # MA should be at least 50% higher

    def test_normalization_table(self, cfg):
        from cmpm.public_data import rate_normalization_table
        df = rate_normalization_table(cfg, "MA")
        assert len(df) == len(cfg["projects"])
        assert all(df["multiplier"] > 1.5)
        assert all(df["npv_target"] > df["npv_IL"])


class TestFinancingAnalysis:
    def test_produces_dataframe(self, cfg):
        from cmpm.public_data import financing_analysis
        df = financing_analysis(cfg)
        assert len(df) == len(cfg["projects"])
        assert "npv_direct_purchase" in df.columns
        assert "npv_epc_guaranteed" in df.columns
        assert "npv_combined_best" in df.columns

    def test_incentive_reduces_effective_capex(self, cfg):
        from cmpm.public_data import financing_analysis
        df = financing_analysis(cfg)
        assert all(df["npv_with_incentive"] >= df["npv_direct_purchase"])
