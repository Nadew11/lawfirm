"""Tests for cmpm.data_loader — real data loading and format validation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from cmpm.data_loader import (
    DataAvailability,
    _validate_columns,
    bills_for_building,
    bills_to_evidence_format,
    discover_data,
    generate_load_from_real_data,
    load_weather,
    occupancy_to_hourly_array,
    weather_to_hourly_series,
)
from cmpm.config_loader import load_config


@pytest.fixture
def cfg() -> dict[str, Any]:
    return load_config()


@pytest.fixture
def sample_weather() -> pd.DataFrame:
    rows = []
    for h in range(8760):
        day = h // 24
        hour = h % 24
        temp_f = 55 + 25 * np.sin(2 * np.pi * (day - 80) / 365) + 8 * np.sin(2 * np.pi * (hour - 6) / 24)
        rows.append({"year": 2024, "month": (day // 30) + 1, "day": (day % 30) + 1,
                      "hour": hour, "temp_c": (temp_f - 32) * 5 / 9, "temp_f": temp_f})
    return pd.DataFrame(rows)


@pytest.fixture
def sample_bills() -> pd.DataFrame:
    rows = []
    for month in range(1, 13):
        rows.append({
            "building": "lab_ventilation", "year": 2024, "month": month,
            "total_kwh": 80000 + month * 1000, "demand_kw": 250,
            "gas_therms": max(0, 1200 - month * 100), "total_cost": 12000.0,
        })
    for month in range(1, 13):
        rows.append({
            "building": "central_plant", "year": 2024, "month": month,
            "total_kwh": 350000 + month * 5000, "demand_kw": 1100,
            "gas_therms": 5000, "total_cost": 52000.0,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def sample_occupancy() -> pd.DataFrame:
    return pd.DataFrame([
        {"building": "lab_ventilation", "day_type": "weekday",
         "start_hour": 7, "end_hour": 22, "occupancy_fraction": 1.0,
         "period_start": "2024-01-15", "period_end": "2024-12-15"},
        {"building": "lab_ventilation", "day_type": "weekend",
         "start_hour": 0, "end_hour": 23, "occupancy_fraction": 0.15,
         "period_start": "2024-01-01", "period_end": "2024-12-31"},
    ])


class TestValidateColumns:
    def test_passes_with_all_required(self):
        df = pd.DataFrame({"a": [1], "b": [2], "c": [3]})
        _validate_columns(df, {"a", "b"}, "test")

    def test_raises_on_missing(self):
        df = pd.DataFrame({"a": [1]})
        with pytest.raises(ValueError, match="missing required columns"):
            _validate_columns(df, {"a", "b"}, "test")


class TestWeather:
    def test_load_real_weather(self):
        df = load_weather()
        if df is not None:
            assert "temp_f" in df.columns
            assert len(df) > 0

    def test_hourly_series_length(self, sample_weather):
        temps = weather_to_hourly_series(sample_weather)
        assert len(temps) == 8760

    def test_hourly_series_short_data_pads(self):
        short = pd.DataFrame({"temp_f": [50.0, 60.0, 70.0]})
        temps = weather_to_hourly_series(short)
        assert len(temps) == 8760


class TestBills:
    def test_bills_for_building(self, sample_bills):
        lab = bills_for_building(sample_bills, "lab_ventilation")
        assert len(lab) == 12
        assert all(lab["building"] == "lab_ventilation")

    def test_bills_for_missing_building(self, sample_bills):
        result = bills_for_building(sample_bills, "nonexistent")
        assert len(result) == 0

    def test_evidence_format(self, sample_bills, cfg):
        result = bills_to_evidence_format(sample_bills, cfg)
        assert "building" in result.columns
        assert "total_kwh" in result.columns
        assert "addressable_savings_monthly" in result.columns
        assert len(result) == 24


class TestOccupancy:
    def test_hourly_array_shape(self, sample_occupancy):
        occ = occupancy_to_hourly_array(sample_occupancy, "lab_ventilation")
        assert len(occ) == 8760

    def test_missing_building_returns_ones(self, sample_occupancy):
        occ = occupancy_to_hourly_array(sample_occupancy, "nonexistent")
        assert len(occ) == 8760
        assert np.all(occ == 1.0)


class TestGenerateLoadFromRealData:
    def test_produces_dataframe(self, cfg, sample_weather):
        temps = weather_to_hourly_series(sample_weather)
        data = generate_load_from_real_data(cfg, temps)
        assert isinstance(data, pd.DataFrame)
        assert "total_load_kw" in data.columns
        assert "outdoor_temp" in data.columns
        assert "waste_load_kw" in data.columns
        assert len(data) == 8760

    def test_real_temps_in_output(self, cfg, sample_weather):
        temps = weather_to_hourly_series(sample_weather)
        data = generate_load_from_real_data(cfg, temps)
        np.testing.assert_array_almost_equal(data["outdoor_temp"].values, temps, decimal=1)

    def test_with_occupancy(self, cfg, sample_weather, sample_occupancy):
        temps = weather_to_hourly_series(sample_weather)
        occ = occupancy_to_hourly_array(sample_occupancy, "lab_ventilation")
        data = generate_load_from_real_data(cfg, temps, occupancy=occ)
        assert len(data) == 8760
        assert data["total_load_kw"].sum() > 0

    def test_waste_is_injected(self, cfg, sample_weather):
        temps = weather_to_hourly_series(sample_weather)
        data = generate_load_from_real_data(cfg, temps)
        assert data["waste_load_kw"].sum() > 0


class TestDataAvailability:
    def test_initial_state(self):
        avail = DataAvailability()
        assert not avail.weather
        assert not avail.maintenance

    def test_summary(self):
        avail = DataAvailability()
        avail.weather = True
        avail.bills["lab"] = True
        avail.bills["dorm"] = False
        s = avail.summary()
        assert s["weather"] == "REAL"
        assert s["bills"]["lab"] == "REAL"
        assert s["bills"]["dorm"] == "SYNTHETIC"

    def test_report_string(self):
        avail = DataAvailability()
        avail.weather = True
        avail.bills["lab"] = True
        report = avail.report()
        assert "REAL" in report
        assert "Weather" in report


class TestDiscover:
    def test_discover_returns_dict_and_avail(self, cfg):
        data, avail = discover_data(cfg)
        assert isinstance(data, dict)
        assert isinstance(avail, DataAvailability)
        assert "weather" in data
        # Weather should be real since we downloaded NOAA data
        if data["weather"] is not None:
            assert avail.weather
