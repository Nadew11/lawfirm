"""Baseline model sanity check: synthetic load, waste injection, recovery testing."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_squared_error


def generate_synthetic_load(
    cfg: dict[str, Any],
    seed: int | None = None,
) -> pd.DataFrame:
    """Generate SYNTHETIC hourly building load for one year (8760 hours).

    Includes weather-driven heating/cooling, occupancy schedule, noise,
    and a KNOWN injected waste of simultaneous heating/cooling.

    ALL OUTPUT IS SYNTHETIC — NOT REAL BUILDING DATA.
    """
    baseline_cfg = cfg["baseline"]
    if seed is None:
        seed = cfg["general"]["random_seed"]
    rng = np.random.default_rng(seed + 500)

    n_hours = 8760
    hours = np.arange(n_hours)
    day_of_year = hours // 24
    hour_of_day = hours % 24
    day_of_week = (day_of_year % 7)

    # Synthetic outdoor temperature: sinusoidal annual + diurnal + noise
    annual_cycle = 55 + 25 * np.sin(2 * np.pi * (day_of_year - 80) / 365)
    diurnal_cycle = 8 * np.sin(2 * np.pi * (hour_of_day - 6) / 24)
    temp_noise = rng.normal(0, 5, n_hours)
    outdoor_temp = annual_cycle + diurnal_cycle + temp_noise

    # Occupancy: weekday 7am-10pm during semester, reduced during breaks
    is_weekday = day_of_week < 5
    is_work_hours = (hour_of_day >= 7) & (hour_of_day <= 22)
    is_semester = (
        ((day_of_year >= 15) & (day_of_year <= 130))   # spring
        | ((day_of_year >= 240) & (day_of_year <= 345))  # fall
    )
    occupancy = np.ones(n_hours)
    occupied = is_weekday & is_work_hours & is_semester
    occupancy[~occupied] = 1.0 / baseline_cfg["occupancy_multiplier"]

    # Base load
    base_load = baseline_cfg["base_load_kw"] * occupancy

    # Heating and cooling
    htg_cp = baseline_cfg["heating_changepoint_f"]
    clg_cp = baseline_cfg["cooling_changepoint_f"]
    htg_slope = baseline_cfg["heating_slope"]
    clg_slope = baseline_cfg["cooling_slope"]

    heating_load = np.maximum(htg_cp - outdoor_temp, 0) * htg_slope * occupancy
    cooling_load = np.maximum(outdoor_temp - clg_cp, 0) * clg_slope * occupancy

    # Injected waste: simultaneous heating + cooling during shoulder seasons
    waste_frac = baseline_cfg["injected_waste_fraction"]
    is_shoulder = (outdoor_temp >= htg_cp - 5) & (outdoor_temp <= clg_cp + 5)
    waste_load = np.zeros(n_hours)
    waste_load[is_shoulder] = waste_frac * (base_load[is_shoulder] + heating_load[is_shoulder] + cooling_load[is_shoulder])

    noise = rng.normal(0, baseline_cfg["noise_std_kw"], n_hours)
    total_load = base_load + heating_load + cooling_load + waste_load + noise
    total_load = np.maximum(total_load, 0)

    clean_load = base_load + heating_load + cooling_load + noise
    clean_load = np.maximum(clean_load, 0)

    df = pd.DataFrame({
        "hour": hours,
        "day_of_year": day_of_year,
        "hour_of_day": hour_of_day,
        "day_of_week": day_of_week,
        "outdoor_temp": outdoor_temp,
        "occupancy": occupancy,
        "total_load_kw": total_load,
        "clean_load_kw": clean_load,
        "waste_load_kw": waste_load,
        "is_shoulder": is_shoulder,
    })
    return df


def changepoint_regression(
    data: pd.DataFrame,
) -> dict[str, Any]:
    """Fit a piecewise-linear (3-parameter change-point) model.

    Model: load = base + htg_slope * max(htg_cp - T, 0) + clg_slope * max(T - clg_cp, 0)
    Estimate waste as excess energy in shoulder season not explained by model.
    """
    temp = data["outdoor_temp"].values
    load = data["total_load_kw"].values

    def model(params: np.ndarray) -> np.ndarray:
        base, hs, cs, hcp, ccp = params
        return base + hs * np.maximum(hcp - temp, 0) + cs * np.maximum(temp - ccp, 0)

    def objective(params: np.ndarray) -> float:
        pred = model(params)
        return float(np.sum((load - pred) ** 2))

    x0 = np.array([500, 10, 10, 55, 65])
    bounds = [(100, 2000), (0, 100), (0, 100), (30, 70), (50, 90)]
    result = minimize(objective, x0, bounds=bounds, method="L-BFGS-B")
    params = result.x

    pred = model(params)
    residuals = load - pred

    shoulder_mask = data["is_shoulder"].values
    shoulder_excess = np.mean(residuals[shoulder_mask])
    total_mean = np.mean(load)
    estimated_waste_pct = shoulder_excess / total_mean if total_mean > 0 else 0

    rmse = np.sqrt(np.mean(residuals ** 2))
    cvrmse = rmse / np.mean(load) if np.mean(load) > 0 else np.inf

    return {
        "params": {"base": params[0], "htg_slope": params[1], "clg_slope": params[2],
                    "htg_cp": params[3], "clg_cp": params[4]},
        "estimated_waste_pct": estimated_waste_pct,
        "rmse": rmse,
        "cvrmse": cvrmse,
        "predictions": pred,
    }


def gradient_boosting_model(
    data: pd.DataFrame,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Fit gradient boosting with rolling-origin cross-validation.

    Uses time-ordered splits — NO random shuffling.
    """
    baseline_cfg = cfg["baseline"]
    features = ["outdoor_temp", "hour_of_day", "day_of_week", "occupancy", "is_shoulder_flag",
                "htg_clg_overlap"]

    htg_cp = baseline_cfg["heating_changepoint_f"]
    clg_cp = baseline_cfg["cooling_changepoint_f"]
    temp = data["outdoor_temp"].values

    feature_df = data[["outdoor_temp", "hour_of_day", "day_of_week", "occupancy"]].copy()
    feature_df["is_shoulder_flag"] = data["is_shoulder"].astype(float).values
    feature_df["htg_clg_overlap"] = (
        np.maximum(htg_cp - temp, 0) * np.maximum(temp - clg_cp, 0)
    )

    X = feature_df.values
    y = data["total_load_kw"].values
    n = len(y)

    min_train = baseline_cfg["rolling_origin_min_train_days"] * 24
    step = baseline_cfg["rolling_origin_step_days"] * 24

    fold_rmses = []
    fold_starts = list(range(min_train, n - step, step))

    for start in fold_starts:
        end = min(start + step, n)
        X_train, y_train = X[:start], y[:start]
        X_test, y_test = X[start:end], y[start:end]

        gb = GradientBoostingRegressor(
            n_estimators=baseline_cfg["gb_n_estimators"],
            max_depth=baseline_cfg["gb_max_depth"],
            learning_rate=baseline_cfg["gb_learning_rate"],
            random_state=cfg["general"]["random_seed"],
        )
        gb.fit(X_train, y_train)
        pred = gb.predict(X_test)
        rmse = np.sqrt(mean_squared_error(y_test, pred))
        fold_rmses.append(rmse)

    # Final model on full data for waste estimation
    gb_final = GradientBoostingRegressor(
        n_estimators=baseline_cfg["gb_n_estimators"],
        max_depth=baseline_cfg["gb_max_depth"],
        learning_rate=baseline_cfg["gb_learning_rate"],
        random_state=cfg["general"]["random_seed"],
    )
    # Train on first 80% (time-ordered)
    split = int(0.8 * n)
    gb_final.fit(X[:split], y[:split])
    pred_all = gb_final.predict(X)

    residuals = y - pred_all
    shoulder_mask = data["is_shoulder"].values
    shoulder_excess = np.mean(residuals[shoulder_mask])
    total_mean = np.mean(y)
    estimated_waste_pct = shoulder_excess / total_mean if total_mean > 0 else 0

    mean_rmse = np.mean(fold_rmses)
    cvrmse = mean_rmse / total_mean if total_mean > 0 else np.inf

    return {
        "estimated_waste_pct": estimated_waste_pct,
        "mean_cv_rmse": mean_rmse,
        "cvrmse": cvrmse,
        "fold_rmses": fold_rmses,
        "feature_importances": dict(zip(features, gb_final.feature_importances_.tolist())),
    }


def evaluate_waste_recovery(
    data: pd.DataFrame,
    cfg: dict[str, Any],
) -> pd.DataFrame:
    """Run both models and compare estimated waste vs true injected waste.

    Reports bias and CVRMSE per model.
    """
    true_waste_frac = cfg["baseline"]["injected_waste_fraction"]
    true_waste_kw = data["waste_load_kw"].sum()
    total_load = data["total_load_kw"].sum()
    true_waste_pct = true_waste_kw / total_load if total_load > 0 else 0

    cp_result = changepoint_regression(data)
    gb_result = gradient_boosting_model(data, cfg)

    rows = [
        {
            "model": "change_point_regression",
            "estimated_waste_pct": cp_result["estimated_waste_pct"],
            "true_waste_pct": true_waste_pct,
            "bias": cp_result["estimated_waste_pct"] - true_waste_pct,
            "cvrmse": cp_result["cvrmse"],
            "detects_waste": cp_result["estimated_waste_pct"] > 0.02,
        },
        {
            "model": "gradient_boosting",
            "estimated_waste_pct": gb_result["estimated_waste_pct"],
            "true_waste_pct": true_waste_pct,
            "bias": gb_result["estimated_waste_pct"] - true_waste_pct,
            "cvrmse": gb_result["cvrmse"],
            "detects_waste": gb_result["estimated_waste_pct"] > 0.02,
        },
    ]
    return pd.DataFrame(rows)
