"""Load real campus data from CSV files and prepare for model consumption.

Handles: weather, utility bills, submeter data, occupancy schedules,
and maintenance logs. Falls back to synthetic generation per-building
when real data is unavailable.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REAL_DIR = DATA_DIR / "real"
WEATHER_DIR = DATA_DIR / "weather"

REQUIRED_BILL_COLS = {"building", "year", "month", "total_kwh", "total_cost"}
REQUIRED_SUBMETER_COLS = {"building", "timestamp", "heating_kw", "cooling_kw"}
REQUIRED_OCCUPANCY_COLS = {"building", "day_type", "start_hour", "end_hour",
                           "occupancy_fraction", "period_start", "period_end"}
REQUIRED_MAINTENANCE_COLS = {"date", "event_type", "cost"}


class DataAvailability:
    """Tracks what real data is available per building."""

    def __init__(self) -> None:
        self.weather: bool = False
        self.bills: dict[str, bool] = {}
        self.submeters: dict[str, bool] = {}
        self.occupancy: dict[str, bool] = {}
        self.maintenance: bool = False

    def summary(self) -> dict[str, Any]:
        return {
            "weather": "REAL" if self.weather else "SYNTHETIC",
            "bills": {k: "REAL" if v else "SYNTHETIC" for k, v in self.bills.items()},
            "submeters": {k: "REAL" if v else "SYNTHETIC" for k, v in self.submeters.items()},
            "occupancy": {k: "REAL" if v else "SYNTHETIC" for k, v in self.occupancy.items()},
            "maintenance": "REAL" if self.maintenance else "SYNTHETIC",
        }

    def report(self) -> str:
        lines = ["Data Source Report:", "=" * 50]
        lines.append(f"  Weather:     {self.summary()['weather']}")
        lines.append(f"  Maintenance: {self.summary()['maintenance']}")
        for bldg in sorted(set(list(self.bills) + list(self.submeters) + list(self.occupancy))):
            b = self.bills.get(bldg, False)
            s = self.submeters.get(bldg, False)
            o = self.occupancy.get(bldg, False)
            lines.append(f"  {bldg}:")
            lines.append(f"    Bills={('REAL' if b else 'SYNTHETIC')}, "
                         f"Submeter={('REAL' if s else 'SYNTHETIC')}, "
                         f"Occupancy={('REAL' if o else 'SYNTHETIC')}")
        return "\n".join(lines)


def _validate_columns(df: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")


# =========================================================================
# Weather
# =========================================================================

def load_weather(path: Path | None = None) -> pd.DataFrame | None:
    """Load hourly weather data. Returns None if unavailable.

    Prefers Quad City airport (KMLI) data for Rock Island campus.
    Falls back to Chicago O'Hare if Quad City data unavailable.
    """
    if path is None:
        quad_city = WEATHER_DIR / "quad_city_hourly.csv"
        chicago = WEATHER_DIR / "hourly_weather.csv"
        path = quad_city if quad_city.exists() else chicago
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if "temp_f" not in df.columns:
        if "temp_c" in df.columns:
            df["temp_f"] = df["temp_c"] * 9 / 5 + 32
        else:
            return None
    return df


def weather_to_hourly_series(weather_df: pd.DataFrame, year: int | None = None) -> np.ndarray:
    """Convert weather DataFrame to 8760-element hourly temperature array.

    If weather data doesn't cover a full year, it wraps/interpolates to fill gaps.
    """
    if year is not None:
        subset = weather_df[weather_df["year"] == year].copy()
        if len(subset) >= 8000:
            weather_df = subset

    temps = weather_df["temp_f"].values

    if len(temps) >= 8760:
        return temps[:8760]

    # Pad by tiling if short
    repeats = (8760 // len(temps)) + 1
    padded = np.tile(temps, repeats)
    return padded[:8760]


# =========================================================================
# Utility bills
# =========================================================================

def load_utility_bills(path: Path | None = None) -> pd.DataFrame | None:
    """Load utility bill data from CSV or Excel."""
    if path is None:
        path = REAL_DIR / "utility_bills.csv"
    if not path.exists():
        xlsx = path.with_suffix(".xlsx")
        if xlsx.exists():
            path = xlsx
        else:
            return None
    if path.suffix == ".xlsx":
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)
    _validate_columns(df, REQUIRED_BILL_COLS, "Utility bills")
    return df


def bills_for_building(bills_df: pd.DataFrame, building: str) -> pd.DataFrame:
    """Filter bills to a single building."""
    return bills_df[bills_df["building"] == building].copy()


def bills_to_evidence_format(bills_df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Convert real bills into the format expected by evidence.validate_benefits_against_bills.

    The real bills may not have waste_kwh or addressable_savings_monthly columns,
    so we estimate them from total consumption and engineering benchmarks.
    """
    cost_per_kwh = 0.12

    rows = []
    for bldg in bills_df["building"].unique():
        bldg_bills = bills_df[bills_df["building"] == bldg]
        for _, row in bldg_bills.iterrows():
            total_kwh = row["total_kwh"]
            total_cost = row.get("total_cost", total_kwh * cost_per_kwh)

            if "waste_kwh" in row and pd.notna(row.get("waste_kwh")):
                waste = row["waste_kwh"]
            else:
                waste = 0

            if "addressable_savings_monthly" in row and pd.notna(row.get("addressable_savings_monthly")):
                addressable = row["addressable_savings_monthly"]
            else:
                addressable = waste * cost_per_kwh

            efficient = total_kwh - waste
            rows.append({
                "building": bldg,
                "year": int(row["year"]),
                "month": int(row["month"]),
                "total_kwh": round(total_kwh),
                "efficient_kwh": round(efficient),
                "waste_kwh": round(waste),
                "total_cost": round(total_cost, 2),
                "addressable_savings_monthly": round(addressable, 2),
            })
    return pd.DataFrame(rows)


# =========================================================================
# Submeter data
# =========================================================================

def load_submeter_data(path: Path | None = None) -> pd.DataFrame | None:
    """Load submetered interval data."""
    if path is None:
        path = REAL_DIR / "submeter_data.csv"
    if not path.exists():
        xlsx = path.with_suffix(".xlsx")
        if xlsx.exists():
            path = xlsx
        else:
            return None
    if path.suffix == ".xlsx":
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)
    _validate_columns(df, REQUIRED_SUBMETER_COLS, "Submeter data")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def submeter_for_building(submeter_df: pd.DataFrame, building: str) -> pd.DataFrame:
    """Filter submeter data to a single building."""
    return submeter_df[submeter_df["building"] == building].copy()


# =========================================================================
# Occupancy
# =========================================================================

def load_occupancy_schedule(path: Path | None = None) -> pd.DataFrame | None:
    """Load occupancy schedule data."""
    if path is None:
        path = REAL_DIR / "occupancy_schedule.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    _validate_columns(df, REQUIRED_OCCUPANCY_COLS, "Occupancy schedule")
    df["period_start"] = pd.to_datetime(df["period_start"])
    df["period_end"] = pd.to_datetime(df["period_end"])
    return df


def occupancy_to_hourly_array(
    occ_df: pd.DataFrame,
    building: str,
    n_hours: int = 8760,
    year: int = 2024,
) -> np.ndarray:
    """Convert occupancy schedule to hourly occupancy fraction array.

    For each hour, finds the matching schedule row (day_type + period)
    and returns the occupancy_fraction if within occupied hours, else
    a reduced fraction.
    """
    bldg_occ = occ_df[occ_df["building"] == building].copy()
    if len(bldg_occ) == 0:
        return np.ones(n_hours)

    bldg_occ["period_start"] = pd.to_datetime(bldg_occ["period_start"])
    bldg_occ["period_end"] = pd.to_datetime(bldg_occ["period_end"])

    occ = np.ones(n_hours) * 0.2

    timestamps = pd.date_range(start=f"{year}-01-01", periods=n_hours, freq="h")
    hours_of_day = timestamps.hour
    day_types = np.where(timestamps.dayofweek >= 5, "weekend", "weekday")

    for _, row in bldg_occ.iterrows():
        dt_mask = (
            (day_types == row["day_type"])
            & (timestamps >= row["period_start"])
            & (timestamps <= row["period_end"])
        )
        occupied_mask = dt_mask & (hours_of_day >= row["start_hour"]) & (hours_of_day <= row["end_hour"])
        unoccupied_mask = dt_mask & ~occupied_mask

        occ[occupied_mask] = row["occupancy_fraction"]
        occ[unoccupied_mask] = row["occupancy_fraction"] * 0.2

    return occ


# =========================================================================
# Maintenance
# =========================================================================

def load_maintenance_log(path: Path | None = None) -> pd.DataFrame | None:
    """Load maintenance log data."""
    if path is None:
        path = REAL_DIR / "maintenance_log.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    _validate_columns(df, REQUIRED_MAINTENANCE_COLS, "Maintenance log")
    df["date"] = pd.to_datetime(df["date"])
    return df


# =========================================================================
# Integrated load generation from real data
# =========================================================================

def generate_load_from_real_data(
    cfg: dict[str, Any],
    weather_temps: np.ndarray,
    occupancy: np.ndarray | None = None,
) -> pd.DataFrame:
    """Generate the load DataFrame using REAL weather data and occupancy.

    Replaces generate_synthetic_load() when real data is available.
    Uses the same baseline model parameters but with real weather driving
    the simulation. This produces a more realistic baseline for waste
    detection testing.
    """
    baseline_cfg = cfg["baseline"]
    rng = np.random.default_rng(cfg["general"]["random_seed"] + 500)

    n_hours = len(weather_temps)
    hours = np.arange(n_hours)
    day_of_year = hours // 24
    hour_of_day = hours % 24
    day_of_week = (day_of_year % 7)

    outdoor_temp = weather_temps[:n_hours]

    if occupancy is None:
        is_weekday = day_of_week < 5
        is_work_hours = (hour_of_day >= 7) & (hour_of_day <= 22)
        is_semester = (
            ((day_of_year >= 15) & (day_of_year <= 130))
            | ((day_of_year >= 240) & (day_of_year <= 345))
        )
        occ = np.ones(n_hours)
        occupied = is_weekday & is_work_hours & is_semester
        occ[~occupied] = 1.0 / baseline_cfg["occupancy_multiplier"]
    else:
        occ = occupancy[:n_hours]

    base_load = baseline_cfg["base_load_kw"] * occ

    htg_cp = baseline_cfg["heating_changepoint_f"]
    clg_cp = baseline_cfg["cooling_changepoint_f"]
    htg_slope = baseline_cfg["heating_slope"]
    clg_slope = baseline_cfg["cooling_slope"]

    heating_load = np.maximum(htg_cp - outdoor_temp, 0) * htg_slope * occ
    cooling_load = np.maximum(outdoor_temp - clg_cp, 0) * clg_slope * occ

    waste_frac = baseline_cfg["injected_waste_fraction"]
    is_shoulder = (outdoor_temp >= htg_cp - 5) & (outdoor_temp <= clg_cp + 5)
    waste_load = np.zeros(n_hours)
    waste_load[is_shoulder] = waste_frac * (
        base_load[is_shoulder] + heating_load[is_shoulder] + cooling_load[is_shoulder]
    )

    noise = rng.normal(0, baseline_cfg["noise_std_kw"], n_hours)
    total_load = base_load + heating_load + cooling_load + waste_load + noise
    total_load = np.maximum(total_load, 0)

    clean_load = base_load + heating_load + cooling_load + noise
    clean_load = np.maximum(clean_load, 0)

    return pd.DataFrame({
        "hour": hours,
        "day_of_year": day_of_year,
        "hour_of_day": hour_of_day,
        "day_of_week": day_of_week,
        "outdoor_temp": outdoor_temp,
        "occupancy": occ,
        "total_load_kw": total_load,
        "clean_load_kw": clean_load,
        "waste_load_kw": waste_load,
        "is_shoulder": is_shoulder,
    })


# =========================================================================
# Master: discover and load all available data
# =========================================================================

def discover_data(cfg: dict[str, Any]) -> tuple[dict[str, Any], DataAvailability]:
    """Discover all available real data and load what exists.

    Returns a dict of loaded data and a DataAvailability tracker.
    """
    avail = DataAvailability()
    data: dict[str, Any] = {}
    project_keys = list(cfg["projects"].keys())

    # Weather
    weather_df = load_weather()
    if weather_df is not None and len(weather_df) > 0:
        avail.weather = True
        data["weather"] = weather_df
        data["weather_temps"] = weather_to_hourly_series(weather_df)
    else:
        data["weather"] = None
        data["weather_temps"] = None

    # Utility bills
    bills_df = load_utility_bills()
    if bills_df is not None:
        data["bills"] = bills_df
        for pk in project_keys:
            bldg_bills = bills_for_building(bills_df, pk)
            avail.bills[pk] = len(bldg_bills) >= 12
    else:
        data["bills"] = None
        for pk in project_keys:
            avail.bills[pk] = False

    # Submeter data
    submeter_df = load_submeter_data()
    if submeter_df is not None:
        data["submeters"] = submeter_df
        for pk in project_keys:
            bldg_sub = submeter_for_building(submeter_df, pk)
            avail.submeters[pk] = len(bldg_sub) >= 720  # ~1 month minimum
    else:
        data["submeters"] = None
        for pk in project_keys:
            avail.submeters[pk] = False

    # Occupancy
    occ_df = load_occupancy_schedule()
    if occ_df is not None:
        data["occupancy"] = occ_df
        for pk in project_keys:
            bldg_occ = occ_df[occ_df["building"] == pk]
            avail.occupancy[pk] = len(bldg_occ) > 0
    else:
        data["occupancy"] = None
        for pk in project_keys:
            avail.occupancy[pk] = False

    # Maintenance
    maint_df = load_maintenance_log()
    if maint_df is not None:
        data["maintenance"] = maint_df
        avail.maintenance = True
    else:
        data["maintenance"] = None

    return data, avail
