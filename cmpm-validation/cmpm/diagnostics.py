"""Overfitting & circularity diagnostics for the CMPM validation harness.

Checks every model layer for:
  - Overfitting (train vs test gap, learning curves)
  - Circularity (synthetic evidence that confirms its own inputs)
  - Parameter sensitivity (how much do conclusions shift with assumptions?)
  - Structural limitations (model form vs data generating process)
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_squared_error

from cmpm.baseline import changepoint_regression, generate_synthetic_load
from cmpm.economics import compute_npv
from cmpm.evidence import (
    calibrate_savings_distribution,
    generate_all_evidence,
    generate_mv_comparison,
    generate_utility_bills,
    validate_benefits_against_bills,
)
from cmpm.interactions import (
    adjusted_portfolio_npv,
    interaction_matrix_from_config,
    naive_portfolio_npv,
)
from cmpm.uncertainty import (
    compute_mc_stats,
    generate_correlated_draws,
    monte_carlo_npv,
    monte_carlo_payback,
)
from cmpm.utils import build_cashflows


# =========================================================================
# 1. Gradient Boosting: train vs test gap and learning curves
# =========================================================================

def gb_train_test_gap(
    data: pd.DataFrame,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Measure in-sample vs out-of-sample RMSE for the gradient boosting model.

    A large gap (train RMSE << test RMSE) signals overfitting.
    """
    baseline_cfg = cfg["baseline"]
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
    split = int(0.8 * n)

    gb = GradientBoostingRegressor(
        n_estimators=baseline_cfg["gb_n_estimators"],
        max_depth=baseline_cfg["gb_max_depth"],
        learning_rate=baseline_cfg["gb_learning_rate"],
        random_state=cfg["general"]["random_seed"],
    )
    gb.fit(X[:split], y[:split])

    train_pred = gb.predict(X[:split])
    test_pred = gb.predict(X[split:])

    train_rmse = np.sqrt(mean_squared_error(y[:split], train_pred))
    test_rmse = np.sqrt(mean_squared_error(y[split:], test_pred))
    total_mean = np.mean(y)

    train_resid = y[:split] - train_pred
    test_resid = y[split:] - test_pred

    shoulder_train = data["is_shoulder"].values[:split]
    shoulder_test = data["is_shoulder"].values[split:]

    train_shoulder_excess = np.mean(train_resid[shoulder_train]) / total_mean
    test_shoulder_excess = np.mean(test_resid[shoulder_test]) / total_mean

    overfit_ratio = test_rmse / train_rmse if train_rmse > 0 else float("inf")

    return {
        "train_rmse": round(train_rmse, 2),
        "test_rmse": round(test_rmse, 2),
        "overfit_ratio": round(overfit_ratio, 3),
        "train_cvrmse": round(train_rmse / total_mean, 4),
        "test_cvrmse": round(test_rmse / total_mean, 4),
        "train_shoulder_waste_est": round(train_shoulder_excess, 4),
        "test_shoulder_waste_est": round(test_shoulder_excess, 4),
        "diagnosis": _diagnose_overfit(overfit_ratio),
        "feature_importances": dict(zip(
            ["outdoor_temp", "hour_of_day", "day_of_week", "occupancy",
             "is_shoulder_flag", "htg_clg_overlap"],
            gb.feature_importances_.tolist(),
        )),
    }


def _diagnose_overfit(ratio: float) -> str:
    if ratio > 3.0:
        return "SEVERE overfitting: test RMSE > 3x train RMSE"
    elif ratio > 2.0:
        return "MODERATE overfitting: test RMSE > 2x train RMSE"
    elif ratio > 1.5:
        return "MILD overfitting: test RMSE notably exceeds train"
    elif ratio < 0.8:
        return "SUSPICIOUS: test RMSE < train — possible data leakage or non-stationarity"
    return "OK: train/test gap within normal range"


def gb_learning_curve(
    data: pd.DataFrame,
    cfg: dict[str, Any],
    n_estimator_values: list[int] | None = None,
) -> pd.DataFrame:
    """Compute train/test RMSE at various n_estimators to detect overfitting onset."""
    if n_estimator_values is None:
        n_estimator_values = [10, 25, 50, 100, 200, 300, 500, 750, 1000]

    baseline_cfg = cfg["baseline"]
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
    split = int(0.8 * n)

    rows = []
    for n_est in n_estimator_values:
        gb = GradientBoostingRegressor(
            n_estimators=n_est,
            max_depth=baseline_cfg["gb_max_depth"],
            learning_rate=baseline_cfg["gb_learning_rate"],
            random_state=cfg["general"]["random_seed"],
        )
        gb.fit(X[:split], y[:split])

        train_rmse = np.sqrt(mean_squared_error(y[:split], gb.predict(X[:split])))
        test_rmse = np.sqrt(mean_squared_error(y[split:], gb.predict(X[split:])))

        rows.append({
            "n_estimators": n_est,
            "train_rmse": round(train_rmse, 2),
            "test_rmse": round(test_rmse, 2),
            "gap": round(test_rmse - train_rmse, 2),
            "ratio": round(test_rmse / train_rmse if train_rmse > 0 else float("inf"), 3),
        })

    return pd.DataFrame(rows)


# =========================================================================
# 2. Changepoint regression: residual diagnostics
# =========================================================================

def cp_residual_diagnostics(data: pd.DataFrame) -> dict[str, Any]:
    """Analyze changepoint regression residuals for non-randomness.

    Autocorrelated residuals signal the model is missing a systematic pattern.
    """
    result = changepoint_regression(data)
    residuals = data["total_load_kw"].values - result["predictions"]
    n = len(residuals)

    # Lag-1 autocorrelation
    mean_r = np.mean(residuals)
    autocov_0 = np.sum((residuals - mean_r) ** 2)
    autocov_1 = np.sum((residuals[:-1] - mean_r) * (residuals[1:] - mean_r))
    lag1_acf = autocov_1 / autocov_0 if autocov_0 > 0 else 0.0

    # Durbin-Watson statistic: 2.0 = no autocorrelation, <1.5 = positive autocorrelation
    dw = np.sum(np.diff(residuals) ** 2) / np.sum(residuals ** 2)

    # Shoulder vs non-shoulder residuals
    shoulder = data["is_shoulder"].values
    shoulder_mean = np.mean(residuals[shoulder])
    non_shoulder_mean = np.mean(residuals[~shoulder])

    # Residual normality (Jarque-Bera-like)
    skew = float(pd.Series(residuals).skew())
    kurtosis = float(pd.Series(residuals).kurtosis())

    return {
        "lag1_autocorrelation": round(lag1_acf, 4),
        "durbin_watson": round(dw, 4),
        "shoulder_residual_mean": round(shoulder_mean, 2),
        "non_shoulder_residual_mean": round(non_shoulder_mean, 2),
        "residual_skewness": round(skew, 3),
        "residual_kurtosis": round(kurtosis, 3),
        "cp_params": result["params"],
        "diagnosis": _diagnose_residuals(lag1_acf, dw, shoulder_mean),
    }


def _diagnose_residuals(acf: float, dw: float, shoulder_mean: float) -> str:
    issues = []
    if abs(acf) > 0.3:
        issues.append(f"HIGH autocorrelation (lag-1={acf:.3f}) — model misses time-dependent pattern")
    if dw < 1.5:
        issues.append(f"Durbin-Watson={dw:.2f} < 1.5 — positive serial correlation in residuals")
    if abs(shoulder_mean) > 10:
        issues.append(f"Shoulder residual bias={shoulder_mean:.1f} kW — systematic under/over-prediction")
    if not issues:
        return "OK: residuals appear random"
    return "; ".join(issues)


# =========================================================================
# 3. Monte Carlo: distribution sensitivity and bootstrap stability
# =========================================================================

def mc_distribution_sensitivity(
    cfg: dict[str, Any],
    project_key: str = "lab_ventilation",
) -> pd.DataFrame:
    """Test how MC conclusions change when the savings mode shifts ±0.05.

    If P(NPV>0) swings dramatically, the conclusion is fragile.
    """
    seed = cfg["general"]["random_seed"]
    n = cfg["general"]["monte_carlo_draws"]
    life = cfg["general"]["analysis_life_years"]
    mc_cfg = cfg["monte_carlo"]
    rho = mc_cfg["correlation_rho"]
    pdata = cfg["projects"][project_key]
    tri = mc_cfg["savings_triangular"]

    shifts = [-0.15, -0.10, -0.05, 0.0, +0.05, +0.10, +0.15]
    rows = []
    for shift in shifts:
        import copy
        mc_shifted = copy.deepcopy(mc_cfg)
        new_mode = tri[1] + shift
        new_mode = max(tri[0] + 0.01, min(tri[2] - 0.01, new_mode))
        mc_shifted["savings_triangular"] = [tri[0], new_mode, tri[2]]

        draws = generate_correlated_draws(n, rho, seed, mc_shifted)
        npvs = monte_carlo_npv(pdata["capex"], pdata["annual_benefit"], life, draws)
        paybacks = monte_carlo_payback(pdata["capex"], pdata["annual_benefit"], draws)
        stats = compute_mc_stats(npvs, paybacks)
        rows.append({
            "mode_shift": shift,
            "savings_mode": round(new_mode, 3),
            "P_NPV_positive": round(stats["P_NPV_positive"], 4),
            "P50_NPV": round(stats["P50"], 0),
            "expected_shortfall_10": round(stats["expected_shortfall_10"], 0),
        })

    return pd.DataFrame(rows)


def mc_bootstrap_stability(
    cfg: dict[str, Any],
    project_key: str = "lab_ventilation",
    n_bootstrap: int = 50,
) -> dict[str, Any]:
    """Bootstrap the MC simulation to measure how stable the stats are.

    Runs MC with different seeds and reports variability in key stats.
    """
    base_seed = cfg["general"]["random_seed"]
    n = cfg["general"]["monte_carlo_draws"]
    life = cfg["general"]["analysis_life_years"]
    mc_cfg = cfg["monte_carlo"]
    rho = mc_cfg["correlation_rho"]
    pdata = cfg["projects"][project_key]

    p_pos_list = []
    p50_list = []
    es10_list = []

    for i in range(n_bootstrap):
        draws = generate_correlated_draws(n, rho, base_seed + i * 1000, mc_cfg)
        npvs = monte_carlo_npv(pdata["capex"], pdata["annual_benefit"], life, draws)
        stats = compute_mc_stats(npvs)
        p_pos_list.append(stats["P_NPV_positive"])
        p50_list.append(stats["P50"])
        es10_list.append(stats["expected_shortfall_10"])

    return {
        "project": project_key,
        "n_bootstrap": n_bootstrap,
        "P_NPV_positive": {
            "mean": round(np.mean(p_pos_list), 4),
            "std": round(np.std(p_pos_list), 4),
            "range": [round(min(p_pos_list), 4), round(max(p_pos_list), 4)],
        },
        "P50_NPV": {
            "mean": round(np.mean(p50_list), 0),
            "std": round(np.std(p50_list), 0),
            "range": [round(min(p50_list), 0), round(max(p50_list), 0)],
        },
        "ES10": {
            "mean": round(np.mean(es10_list), 0),
            "std": round(np.std(es10_list), 0),
            "range": [round(min(es10_list), 0), round(max(es10_list), 0)],
        },
        "diagnosis": _diagnose_mc_stability(np.std(p_pos_list)),
    }


def _diagnose_mc_stability(p_pos_std: float) -> str:
    if p_pos_std > 0.05:
        return "UNSTABLE: P(NPV>0) std > 5pp — increase draws or reduce distribution width"
    elif p_pos_std > 0.02:
        return "MODERATE: P(NPV>0) std 2-5pp — results somewhat seed-dependent"
    return "STABLE: P(NPV>0) std < 2pp"


# =========================================================================
# 4. Evidence circularity audit
# =========================================================================

def evidence_circularity_audit(cfg: dict[str, Any]) -> pd.DataFrame:
    """Quantify how much each evidence generator is tethered to its own inputs.

    A circularity score of 1.0 means the output is mechanically determined
    by the config input — the "evidence" adds no independent information.
    """
    seed = cfg["general"]["random_seed"]
    rows = []

    # (a) Utility bills: waste derived FROM config benefit
    rows.append({
        "evidence_package": "utility_bills",
        "circularity_score": 0.95,
        "mechanism": "waste_kwh = annual_benefit / (rate * 12) * U(0.85,1.15) — "
                     "output is mechanically tied to config benefit",
        "independent_info": "Only the ±15% random scatter is independent",
        "severity": "CRITICAL",
    })

    # (b) M&V data: actual/predicted ratio drawn from N(0.85, 0.15)
    mv = generate_mv_comparison(cfg, seed)
    cal = calibrate_savings_distribution(mv)
    rows.append({
        "evidence_package": "mv_comparison",
        "circularity_score": 0.70,
        "mechanism": f"Ratios drawn from N(0.85, 0.15) — hardcoded assumption. "
                     f"Calibrated mode={cal['mode']:.3f} always near 0.85",
        "independent_info": "Shape/spread come from literature, not campus data",
        "severity": "HIGH",
    })

    # (c) Maintenance records: failure rate=0.40, costs from lognormal(150k, 0.6)
    rows.append({
        "evidence_package": "maintenance_records",
        "circularity_score": 0.80,
        "mechanism": "Failure rate (p=0.40/yr) and cost distribution (lognormal) "
                     "are hardcoded assumptions, not derived from data",
        "independent_info": "Random variation only; generation parameters determine the conclusion",
        "severity": "HIGH",
    })

    # (d) Submetered data: uses SAME waste_fraction and changepoints from config
    rows.append({
        "evidence_package": "submetered_data",
        "circularity_score": 0.90,
        "mechanism": "Waste injected using config waste_fraction and changepoints — "
                     "submeter will always 'detect' waste because it was programmatically injected",
        "independent_info": "None — the data generator and the detector share the same source",
        "severity": "CRITICAL",
    })

    # (e) Interaction analysis: noise around config interaction values
    rows.append({
        "evidence_package": "interaction_analysis",
        "circularity_score": 0.85,
        "mechanism": "Generated as config_value + N(0, ~0.01-0.02) — "
                     "engineering analysis will always confirm config interactions",
        "independent_info": "Only the gaussian noise is independent",
        "severity": "HIGH",
    })

    # (f) Risk tolerance: hardcoded thresholds
    rows.append({
        "evidence_package": "risk_tolerance",
        "circularity_score": 0.60,
        "mechanism": "Thresholds are ARBITRARY ($250k loss, P>0.85) — "
                     "conclusions change entirely with different thresholds",
        "independent_info": "MC stats feed in, but threshold choice drives the conclusion",
        "severity": "MEDIUM",
    })

    # (g) Decision rules: combine circular evidence
    rows.append({
        "evidence_package": "decision_rules",
        "circularity_score": 0.85,
        "mechanism": "Combines circular evidence packages — APPROVE/DEFER driven by "
                     "arbitrary thresholds applied to circularly-generated data",
        "independent_info": "None beyond what individual packages provide",
        "severity": "HIGH",
    })

    return pd.DataFrame(rows)


# =========================================================================
# 5. Scoring: Dirichlet concentration sensitivity
# =========================================================================

def dirichlet_concentration_sensitivity(
    cfg: dict[str, Any],
    concentrations: list[float] | None = None,
) -> pd.DataFrame:
    """Test how the Dirichlet concentration parameter affects rank stability.

    Low concentration = wide perturbation, high = tight. The "stability"
    result is almost entirely determined by this parameter, not the data.
    """
    if concentrations is None:
        concentrations = [5, 10, 20, 50, 100, 200, 500]

    import copy
    projects = cfg["projects"]
    weights = cfg["score_weights"]
    weight_keys = list(weights.keys())
    proj_keys = list(projects.keys())
    seed = cfg["general"]["random_seed"]
    n_draws = 5000

    rows = []
    for conc in concentrations:
        rng = np.random.default_rng(seed + 200)
        alpha = np.array([weights[k] * conc for k in weight_keys])

        baseline_scores = []
        for pk in proj_keys:
            ss = projects[pk]["sub_scores"]
            baseline_scores.append(sum(ss[k] * weights[k] for k in weight_keys))
        baseline_rank = np.argsort(np.argsort(-np.array(baseline_scores))) + 1

        rank_unchanged_count = 0
        top1_same_count = 0
        for _ in range(n_draws):
            w_draw = rng.dirichlet(alpha)
            w_dict = {weight_keys[j]: w_draw[j] for j in range(len(weight_keys))}
            scores = [sum(projects[pk]["sub_scores"][k] * w_dict[k] for k in weight_keys)
                      for pk in proj_keys]
            rank = np.argsort(np.argsort(-np.array(scores))) + 1
            if np.array_equal(rank, baseline_rank):
                rank_unchanged_count += 1
            if rank[0] == baseline_rank[0]:
                top1_same_count += 1

        rows.append({
            "concentration": conc,
            "P_rank_unchanged": round(rank_unchanged_count / n_draws, 4),
            "P_top1_same": round(top1_same_count / n_draws, 4),
            "diagnosis": "artificially stable" if conc > 100 else
                         "realistic spread" if 20 <= conc <= 100 else
                         "very wide — may exaggerate instability",
        })

    return pd.DataFrame(rows)


# =========================================================================
# 6. Interaction magnitude sensitivity
# =========================================================================

def interaction_magnitude_sweep(
    cfg: dict[str, Any],
    multipliers: list[float] | None = None,
) -> pd.DataFrame:
    """Sweep all interaction magnitudes by a common multiplier.

    Shows how sensitive the overstatement conclusion is to the
    assumed interaction strengths.
    """
    if multipliers is None:
        multipliers = [0.0, 0.25, 0.50, 0.75, 1.0, 1.5, 2.0, 3.0]

    import copy
    projects = cfg["projects"]
    rate = cfg["general"]["discount_rate"]
    life = cfg["general"]["analysis_life_years"]
    all_keys = list(projects.keys())

    naive = naive_portfolio_npv(all_keys, projects, rate, life)

    rows = []
    for mult in multipliers:
        scaled_cfg = copy.deepcopy(cfg)
        for k in scaled_cfg["interactions"]:
            scaled_cfg["interactions"][k] *= mult
        imat = interaction_matrix_from_config(scaled_cfg)
        adj = adjusted_portfolio_npv(all_keys, projects, imat, rate, life)
        overstatement = naive - adj
        rows.append({
            "interaction_multiplier": mult,
            "naive_npv": round(naive, 0),
            "adjusted_npv": round(adj, 0),
            "overstatement": round(overstatement, 0),
            "overstatement_pct": round(overstatement / abs(naive) * 100, 2) if naive != 0 else 0,
        })

    return pd.DataFrame(rows)


# =========================================================================
# 7. Full diagnostic report
# =========================================================================

def run_all_diagnostics(cfg: dict[str, Any]) -> dict[str, Any]:
    """Run every diagnostic check and return a structured results dict."""
    data = generate_synthetic_load(cfg)

    gb_gap = gb_train_test_gap(data, cfg)
    gb_curve = gb_learning_curve(data, cfg)
    cp_diag = cp_residual_diagnostics(data)
    mc_sens = mc_distribution_sensitivity(cfg)
    mc_boot = mc_bootstrap_stability(cfg)
    ev_audit = evidence_circularity_audit(cfg)
    dir_sens = dirichlet_concentration_sensitivity(cfg)
    int_sweep = interaction_magnitude_sweep(cfg)

    # Also run per marginal project
    mc_boot_dorm = mc_bootstrap_stability(cfg, project_key="dorm_occupancy")
    mc_sens_plant = mc_distribution_sensitivity(cfg, project_key="central_plant")

    return {
        "gradient_boosting": {
            "train_test_gap": gb_gap,
            "learning_curve": gb_curve,
        },
        "changepoint_regression": cp_diag,
        "monte_carlo": {
            "distribution_sensitivity_lab": mc_sens,
            "distribution_sensitivity_plant": mc_sens_plant,
            "bootstrap_stability_lab": mc_boot,
            "bootstrap_stability_dorm": mc_boot_dorm,
        },
        "evidence_circularity": ev_audit,
        "scoring_dirichlet": dir_sens,
        "interaction_sweep": int_sweep,
    }


def format_diagnostic_report(results: dict[str, Any], cfg: dict[str, Any] | None = None) -> str:
    """Format diagnostics as a markdown report."""
    lines: list[str] = []
    lines.append("# CMPM Diagnostic Report: Overfitting & Circularity Audit\n")

    # 1. Gradient Boosting
    gb = results["gradient_boosting"]
    gap = gb["train_test_gap"]
    lines.append("## 1. Gradient Boosting Overfitting Check\n")
    lines.append(f"- Train RMSE: {gap['train_rmse']} kW")
    lines.append(f"- Test RMSE: {gap['test_rmse']} kW")
    lines.append(f"- Overfit ratio (test/train): **{gap['overfit_ratio']}**")
    lines.append(f"- Train CVRMSE: {gap['train_cvrmse']:.4f}")
    lines.append(f"- Test CVRMSE: {gap['test_cvrmse']:.4f}")
    lines.append(f"- Train shoulder waste estimate: {gap['train_shoulder_waste_est']:.4f}")
    lines.append(f"- Test shoulder waste estimate: {gap['test_shoulder_waste_est']:.4f}")
    lines.append(f"- **Diagnosis**: {gap['diagnosis']}")

    lines.append("\n### Feature Importances\n")
    lines.append("| Feature | Importance |")
    lines.append("|---------|-----------|")
    for feat, imp in sorted(gap["feature_importances"].items(), key=lambda x: -x[1]):
        lines.append(f"| {feat} | {imp:.4f} |")

    curve = gb["learning_curve"]
    lines.append("\n### Learning Curve\n")
    lines.append("| n_estimators | Train RMSE | Test RMSE | Gap | Ratio |")
    lines.append("|-------------|-----------|----------|-----|-------|")
    for _, row in curve.iterrows():
        lines.append(f"| {row['n_estimators']} | {row['train_rmse']} | "
                     f"{row['test_rmse']} | {row['gap']} | {row['ratio']} |")

    # 2. Changepoint Regression
    cp = results["changepoint_regression"]
    lines.append("\n## 2. Changepoint Regression Residuals\n")
    lines.append(f"- Lag-1 autocorrelation: **{cp['lag1_autocorrelation']}**")
    lines.append(f"- Durbin-Watson statistic: **{cp['durbin_watson']}**")
    lines.append(f"- Shoulder residual mean: {cp['shoulder_residual_mean']} kW")
    lines.append(f"- Non-shoulder residual mean: {cp['non_shoulder_residual_mean']} kW")
    lines.append(f"- Residual skewness: {cp['residual_skewness']}")
    lines.append(f"- Residual kurtosis: {cp['residual_kurtosis']}")
    lines.append(f"- **Diagnosis**: {cp['diagnosis']}")

    # 3. Monte Carlo
    mc = results["monte_carlo"]
    lines.append("\n## 3. Monte Carlo Stability & Sensitivity\n")

    for label, sens_df in [("Lab Ventilation", mc["distribution_sensitivity_lab"]),
                            ("Central Plant", mc["distribution_sensitivity_plant"])]:
        lines.append(f"\n### Distribution Sensitivity — {label}\n")
        lines.append("| Mode Shift | Savings Mode | P(NPV>0) | P50 NPV | ES10 |")
        lines.append("|-----------|-------------|----------|---------|------|")
        for _, row in sens_df.iterrows():
            lines.append(f"| {row['mode_shift']:+.2f} | {row['savings_mode']:.3f} | "
                         f"{row['P_NPV_positive']:.4f} | ${row['P50_NPV']:,.0f} | "
                         f"${row['expected_shortfall_10']:,.0f} |")

    for label, boot in [("Lab Ventilation", mc["bootstrap_stability_lab"]),
                         ("Dorm Occupancy", mc["bootstrap_stability_dorm"])]:
        lines.append(f"\n### Bootstrap Stability — {label}\n")
        lines.append(f"- P(NPV>0): mean={boot['P_NPV_positive']['mean']:.4f}, "
                     f"std={boot['P_NPV_positive']['std']:.4f}, "
                     f"range=[{boot['P_NPV_positive']['range'][0]:.4f}, "
                     f"{boot['P_NPV_positive']['range'][1]:.4f}]")
        lines.append(f"- P50 NPV: mean=${boot['P50_NPV']['mean']:,.0f}, "
                     f"std=${boot['P50_NPV']['std']:,.0f}")
        lines.append(f"- **Diagnosis**: {boot['diagnosis']}")

    # 4. Evidence Circularity
    ev = results["evidence_circularity"]
    lines.append("\n## 4. Evidence Circularity Audit\n")
    lines.append("| Package | Circularity | Severity | Mechanism |")
    lines.append("|---------|------------|----------|-----------|")
    for _, row in ev.iterrows():
        lines.append(f"| {row['evidence_package']} | {row['circularity_score']:.2f} | "
                     f"**{row['severity']}** | {row['mechanism'][:80]}... |")
    lines.append("")
    mean_circ = ev["circularity_score"].mean()
    lines.append(f"**Mean circularity score: {mean_circ:.2f}** "
                 f"(1.0 = fully circular, 0.0 = fully independent)")
    if mean_circ > 0.7:
        lines.append("\n> **WARNING**: The evidence packages are predominantly circular. "
                     "They confirm their own input assumptions rather than providing "
                     "independent validation. Replace ALL synthetic generators with "
                     "real campus data before using for decisions.\n")

    # 5. Scoring Dirichlet
    dir_df = results["scoring_dirichlet"]
    lines.append("\n## 5. Scoring Weight Stability — Dirichlet Concentration Sensitivity\n")
    lines.append("| Concentration | P(rank unchanged) | P(#1 same) | Diagnosis |")
    lines.append("|--------------|------------------|-----------|-----------|")
    for _, row in dir_df.iterrows():
        lines.append(f"| {row['concentration']} | {row['P_rank_unchanged']:.4f} | "
                     f"{row['P_top1_same']:.4f} | {row['diagnosis']} |")
    if cfg is not None:
        lines.append(f"\nConfig uses concentration={cfg['scoring']['dirichlet_concentration']}.")
    else:
        lines.append("")

    # 6. Interaction Sweep
    int_df = results["interaction_sweep"]
    lines.append("\n## 6. Interaction Magnitude Sensitivity\n")
    lines.append("| Multiplier | Adjusted NPV | Overstatement | Overstatement % |")
    lines.append("|-----------|-------------|--------------|----------------|")
    for _, row in int_df.iterrows():
        lines.append(f"| {row['interaction_multiplier']:.2f}x | "
                     f"${row['adjusted_npv']:,.0f} | "
                     f"${row['overstatement']:,.0f} | {row['overstatement_pct']:.2f}% |")

    # 7. Summary
    lines.append("\n## 7. Summary of Findings\n")
    issues = []

    if gap["overfit_ratio"] > 1.5:
        issues.append(("GRADIENT BOOSTING", gap["diagnosis"], "HIGH"))

    if abs(cp["lag1_autocorrelation"]) > 0.3 or cp["durbin_watson"] < 1.5:
        issues.append(("CHANGEPOINT REGRESSION", cp["diagnosis"], "HIGH"))

    lab_boot = mc["bootstrap_stability_lab"]
    if lab_boot["P_NPV_positive"]["std"] > 0.02:
        issues.append(("MC STABILITY", lab_boot["diagnosis"], "MEDIUM"))

    crit_ev = ev[ev["severity"].isin(["CRITICAL", "HIGH"])]
    if len(crit_ev) > 0:
        issues.append(("EVIDENCE CIRCULARITY",
                       f"{len(crit_ev)} of {len(ev)} packages have HIGH/CRITICAL circularity",
                       "CRITICAL"))

    if not issues:
        lines.append("No significant overfitting or circularity issues detected.")
    else:
        lines.append("| Component | Issue | Severity |")
        lines.append("|-----------|-------|----------|")
        for comp, issue, sev in issues:
            lines.append(f"| {comp} | {issue} | **{sev}** |")

    return "\n".join(lines)
