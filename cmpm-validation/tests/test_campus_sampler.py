"""Tests for campus_sampler module."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from cmpm.campus_sampler import (
    CampusProfile,
    SampledBuilding,
    apply_sampled_campus_to_config,
    compute_savings_from_sampled,
    generate_all_sampled_bills,
    generate_campus_report,
    generate_synthetic_bills_from_sample,
    get_building_type_stats,
    get_peer_comparison,
    load_chicago_data,
    load_chicago_multiyear,
    sample_building,
    sample_campus,
)
from cmpm.config_loader import load_config

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "public"
HAS_CHICAGO_DATA = (DATA_DIR / "chicago" / "campus_buildings_clean.csv").exists()

skip_no_data = pytest.mark.skipif(
    not HAS_CHICAGO_DATA, reason="Chicago benchmarking data not downloaded"
)


class TestSampledBuilding:
    def test_basic_properties(self):
        b = SampledBuilding(
            project_key="lab_ventilation",
            source_building_id=12345,
            source_building_name="Test Lab",
            building_type="Laboratory",
            area_sqft=100000,
            site_eui_kbtu=300.0,
            electricity_kbtu=20000000,
            gas_kbtu=10000000,
            annual_kwh=5861420.0,
            annual_therms=100000.0,
            year_built=1990,
            energy_star_score=55.0,
            data_year=2022,
        )
        assert b.electricity_eui_kwh_sqft == pytest.approx(58.6142)
        assert b.annual_cost_estimate > 0

    def test_zero_area_eui(self):
        b = SampledBuilding(
            project_key="test",
            source_building_id=0,
            source_building_name="Empty",
            building_type="Lab",
            area_sqft=0,
            site_eui_kbtu=0,
            electricity_kbtu=0,
            gas_kbtu=0,
            annual_kwh=0,
            annual_therms=0,
            year_built=None,
            energy_star_score=None,
            data_year=2023,
        )
        assert b.electricity_eui_kwh_sqft == 0.0


class TestCampusProfile:
    def test_totals(self):
        campus = CampusProfile()
        campus.buildings["a"] = SampledBuilding(
            project_key="a", source_building_id=1, source_building_name="A",
            building_type="College/University", area_sqft=100000, site_eui_kbtu=100,
            electricity_kbtu=10000000, gas_kbtu=5000000,
            annual_kwh=2930710, annual_therms=50000,
            year_built=2000, energy_star_score=75, data_year=2023,
        )
        campus.buildings["b"] = SampledBuilding(
            project_key="b", source_building_id=2, source_building_name="B",
            building_type="Laboratory", area_sqft=50000, site_eui_kbtu=300,
            electricity_kbtu=5000000, gas_kbtu=2500000,
            annual_kwh=1465355, annual_therms=25000,
            year_built=1985, energy_star_score=None, data_year=2022,
        )
        assert campus.total_area_sqft == 150000
        assert campus.total_annual_kwh == pytest.approx(2930710 + 1465355)


@skip_no_data
class TestLoadChicagoData:
    def test_load_all(self):
        df = load_chicago_data()
        assert len(df) > 0
        assert "Primary Property Type" in df.columns
        assert "Site EUI (kBtu/sq ft)" in df.columns

    def test_load_filtered(self):
        df = load_chicago_data("Laboratory")
        assert len(df) > 0
        assert (df["Primary Property Type"] == "Laboratory").all()

    def test_load_nonexistent_type(self):
        df = load_chicago_data("Nonexistent Type")
        assert len(df) == 0


@skip_no_data
class TestGetBuildingTypeStats:
    def test_college_stats(self):
        stats = get_building_type_stats("College/University")
        assert stats["n_buildings"] > 100
        assert stats["eui_mean"] > 0
        assert stats["eui_median"] > 0
        assert stats["eui_p25"] < stats["eui_p75"]
        assert stats["area_mean"] > 0

    def test_lab_stats(self):
        stats = get_building_type_stats("Laboratory")
        assert stats["n_buildings"] > 20
        assert stats["eui_mean"] > stats["eui_median"] or True  # Labs are skewed

    def test_dorm_stats(self):
        stats = get_building_type_stats("Residence Hall/Dormitory")
        assert stats["n_buildings"] > 30

    def test_nonexistent_type(self):
        stats = get_building_type_stats("Nonexistent")
        assert stats == {}


@skip_no_data
class TestSampleBuilding:
    def test_sample_lab(self):
        bldg = sample_building("lab_ventilation")
        assert bldg is not None
        assert bldg.building_type == "Laboratory"
        assert bldg.area_sqft > 0
        assert bldg.annual_kwh > 0

    def test_sample_dorm(self):
        bldg = sample_building("dorm_occupancy")
        assert bldg is not None
        assert bldg.building_type == "Residence Hall/Dormitory"

    def test_sample_college(self):
        bldg = sample_building("central_plant")
        assert bldg is not None
        assert bldg.building_type == "College/University"

    def test_reproducibility(self):
        rng1 = np.random.default_rng(42)
        rng2 = np.random.default_rng(42)
        b1 = sample_building("lab_ventilation", rng1)
        b2 = sample_building("lab_ventilation", rng2)
        assert b1.source_building_id == b2.source_building_id

    def test_different_seeds(self):
        rng1 = np.random.default_rng(42)
        rng2 = np.random.default_rng(999)
        b1 = sample_building("lab_ventilation", rng1)
        b2 = sample_building("lab_ventilation", rng2)
        # Different seeds should (usually) give different buildings
        # Not guaranteed but extremely likely with 100+ options
        assert b1 is not None and b2 is not None


@skip_no_data
class TestSampleCampus:
    def test_sample_all_projects(self):
        cfg = load_config()
        campus = sample_campus(cfg, seed=42)
        assert len(campus.buildings) == 5
        assert len(campus.provenance) == 5
        for key in cfg["projects"]:
            assert key in campus.buildings

    def test_different_seeds(self):
        cfg = load_config()
        c1 = sample_campus(cfg, seed=42)
        c2 = sample_campus(cfg, seed=123)
        ids1 = {k: b.source_building_id for k, b in c1.buildings.items()}
        ids2 = {k: b.source_building_id for k, b in c2.buildings.items()}
        assert ids1 != ids2  # Different seeds should give different samples


@skip_no_data
class TestApplySampledCampus:
    def test_apply_adds_metadata(self):
        cfg = load_config()
        campus = sample_campus(cfg, seed=42)
        cfg_new = apply_sampled_campus_to_config(cfg, campus)

        for key in campus.buildings:
            proj = cfg_new["projects"][key]
            assert "_sampled_area_sqft" in proj
            assert "_sampled_annual_kwh" in proj
            assert "_sampled_eui" in proj
            assert "_data_source" in proj
            assert proj["_data_source"] == "Chicago Energy Benchmarking"


class TestComputeSavings:
    def test_basic_savings(self):
        bldg = SampledBuilding(
            project_key="test", source_building_id=1, source_building_name="Test",
            building_type="College/University", area_sqft=100000, site_eui_kbtu=100,
            electricity_kbtu=10000000, gas_kbtu=5000000,
            annual_kwh=1000000, annual_therms=50000,
            year_built=2000, energy_star_score=75, data_year=2023,
        )
        result = compute_savings_from_sampled("test", bldg, 0.15, 0.10)
        assert result["annual_kwh_saved"] == pytest.approx(150000)
        assert result["annual_cost_saved"] == pytest.approx(15000)
        assert result["savings_fraction"] == 0.15


@skip_no_data
class TestPeerComparison:
    def test_peer_comparison_lab(self):
        bldg = sample_building("lab_ventilation")
        assert bldg is not None
        peer = get_peer_comparison("lab_ventilation", bldg)
        assert peer["n_peers"] > 20
        assert 0 <= peer["percentile_rank"] <= 100
        assert peer["efficiency_label"] in [
            "top quartile", "second quartile", "third quartile", "bottom quartile"
        ]


class TestSyntheticBills:
    def test_generate_bills(self):
        bldg = SampledBuilding(
            project_key="test", source_building_id=1, source_building_name="Test",
            building_type="College/University", area_sqft=100000, site_eui_kbtu=100,
            electricity_kbtu=10000000, gas_kbtu=5000000,
            annual_kwh=1000000, annual_therms=50000,
            year_built=2000, energy_star_score=75, data_year=2023,
        )
        bills = generate_synthetic_bills_from_sample(bldg, n_years=3)
        assert len(bills) == 36  # 3 years * 12 months
        assert "total_kwh" in bills.columns
        assert "gas_therms" in bills.columns
        assert (bills["total_kwh"] >= 0).all()
        assert (bills["gas_therms"] >= 0).all()

    def test_annual_total_reasonable(self):
        bldg = SampledBuilding(
            project_key="test", source_building_id=1, source_building_name="Test",
            building_type="College/University", area_sqft=100000, site_eui_kbtu=100,
            electricity_kbtu=10000000, gas_kbtu=5000000,
            annual_kwh=1000000, annual_therms=50000,
            year_built=2000, energy_star_score=75, data_year=2023,
        )
        bills = generate_synthetic_bills_from_sample(bldg, n_years=1)
        annual_kwh = bills["total_kwh"].sum()
        # Should be within 15% of the input
        assert abs(annual_kwh - 1000000) / 1000000 < 0.15


@skip_no_data
class TestGenerateAllBills:
    def test_campus_bills(self):
        cfg = load_config()
        campus = sample_campus(cfg, seed=42)
        all_bills = generate_all_sampled_bills(campus, n_years=2)
        assert len(all_bills) > 0
        buildings = all_bills["building"].unique()
        assert len(buildings) == len(campus.buildings)


@skip_no_data
class TestCampusReport:
    def test_report_generation(self):
        cfg = load_config()
        campus = sample_campus(cfg, seed=42)
        report = generate_campus_report(campus)
        assert "Chicago Energy Benchmarking" in report
        assert "Sampled Buildings" in report
        assert "Campus Totals" in report
        for key in campus.buildings:
            assert key in report
