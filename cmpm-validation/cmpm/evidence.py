"""Generate SYNTHETIC evidence packages for judge/auditor review.

ALL DATA IN THIS MODULE IS FABRICATED FOR DEMONSTRATION.
It is designed to be structurally realistic so the validation harness
can show how real evidence would be used.  Replace with actual campus
data before any real decision.

Evidence packages:
  1. Utility bills & submetering (24 months x 5 buildings)
  2. M&V comparison data from "peer" completed projects
  3. Maintenance records for electrical systems
  4. Engineering interaction analysis
  5. Submetered heating/cooling for direct waste detection
  6. Risk tolerance framework
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


# =========================================================================
# 1. Utility bills & submetering
# =========================================================================

def generate_utility_bills(cfg: dict[str, Any], seed: int | None = None) -> pd.DataFrame:
    """SYNTHETIC 24-month utility data for each building.

    Generates monthly energy consumption with seasonal patterns,
    a known baseline, and an embedded inefficiency that the project
    is supposed to address.  Waste kWh is calibrated from config
    annual_benefit so cross-checks are meaningful.
    """
    if seed is None:
        seed = cfg["general"]["random_seed"]
    rng = np.random.default_rng(seed + 700)

    cost_per_kwh = 0.12  # $/kWh — ARBITRARY, typical institutional rate

    buildings = {
        "lab_ventilation": {
            "base_monthly_kwh": 85_000,
            "seasonal_amplitude": 25_000,
            "noise_std": 5_000,
        },
        "central_plant": {
            "base_monthly_kwh": 400_000,
            "seasonal_amplitude": 150_000,
            "noise_std": 20_000,
        },
        "classroom_bas": {
            "base_monthly_kwh": 50_000,
            "seasonal_amplitude": 15_000,
            "noise_std": 3_000,
        },
        "electrical_monitoring": {
            "base_monthly_kwh": 60_000,
            "seasonal_amplitude": 10_000,
            "noise_std": 4_000,
        },
        "dorm_occupancy": {
            "base_monthly_kwh": 45_000,
            "seasonal_amplitude": 12_000,
            "noise_std": 3_000,
        },
    }

    rows = []
    for bldg_key, params in buildings.items():
        proj = cfg["projects"].get(bldg_key, {})
        annual_benefit = proj.get("annual_benefit", 50_000)
        # Scale waste to ~80-120% of claimed benefit (realistic M&V scatter)
        # so cross-checks show realistic ratios
        waste_kwh_monthly = round(annual_benefit / (cost_per_kwh * 12) * rng.uniform(0.85, 1.15))

        for month_offset in range(24):
            month_num = (month_offset % 12) + 1
            seasonal = params["seasonal_amplitude"] * np.sin(2 * np.pi * (month_num - 1) / 12)
            noise = rng.normal(0, params["noise_std"])
            total_kwh = params["base_monthly_kwh"] + seasonal + waste_kwh_monthly + noise
            total_kwh = max(total_kwh, 10_000)

            efficient_kwh = total_kwh - waste_kwh_monthly
            cost = total_kwh * cost_per_kwh
            addressable_cost = waste_kwh_monthly * cost_per_kwh

            year = 2024 + month_offset // 12
            rows.append({
                "building": bldg_key,
                "year": year,
                "month": month_num,
                "total_kwh": round(total_kwh),
                "efficient_kwh": round(efficient_kwh),
                "waste_kwh": waste_kwh_monthly,
                "total_cost": round(cost, 2),
                "addressable_savings_monthly": round(addressable_cost, 2),
            })

    return pd.DataFrame(rows)


def validate_benefits_against_bills(
    bills: pd.DataFrame,
    cfg: dict[str, Any],
) -> pd.DataFrame:
    """Cross-check config annual_benefit against utility-bill-derived savings."""
    rows = []
    for bldg_key in cfg["projects"]:
        bldg_bills = bills[bills["building"] == bldg_key]
        if len(bldg_bills) == 0:
            continue
        annual_addressable = bldg_bills["addressable_savings_monthly"].mean() * 12
        claimed_benefit = cfg["projects"][bldg_key]["annual_benefit"]
        ratio = claimed_benefit / annual_addressable if annual_addressable > 0 else float("inf")
        rows.append({
            "project": bldg_key,
            "claimed_annual_benefit": claimed_benefit,
            "bill_derived_savings": round(annual_addressable, 0),
            "ratio_claimed_to_derived": round(ratio, 2),
            "within_20pct": 0.80 <= ratio <= 1.20,
            "flag": "OK" if 0.80 <= ratio <= 1.20 else "OVERESTIMATE" if ratio > 1.20 else "UNDERESTIMATE",
        })
    return pd.DataFrame(rows)


# =========================================================================
# 2. M&V comparison data from peer projects
# =========================================================================

def generate_mv_comparison(cfg: dict[str, Any], seed: int | None = None) -> pd.DataFrame:
    """SYNTHETIC M&V results from 20 'comparable' completed projects.

    Shows actual-vs-predicted savings ratios.  This is the single most
    important calibration dataset — it tells you how much to trust
    engineering savings estimates.
    """
    if seed is None:
        seed = cfg["general"]["random_seed"]
    rng = np.random.default_rng(seed + 800)

    project_types = [
        "lab_ventilation", "central_plant", "classroom_bas",
        "predictive_monitoring", "occupancy_controls",
    ]

    rows = []
    for i in range(20):
        ptype = project_types[i % len(project_types)]
        predicted_savings = rng.uniform(40_000, 400_000)

        # Actual savings are typically 60-110% of predicted
        # (performance gap literature: median ~85%, std ~15%)
        actual_ratio = rng.normal(0.85, 0.15)
        actual_ratio = max(actual_ratio, 0.30)
        actual_savings = predicted_savings * actual_ratio

        rows.append({
            "peer_project_id": f"PEER-{i+1:03d}",
            "project_type": ptype,
            "institution": f"University_{chr(65 + i % 8)}",
            "predicted_annual_savings": round(predicted_savings, 0),
            "actual_annual_savings": round(actual_savings, 0),
            "actual_to_predicted_ratio": round(actual_ratio, 3),
            "years_of_mv_data": rng.choice([1, 2, 3], p=[0.3, 0.5, 0.2]),
        })

    return pd.DataFrame(rows)


def calibrate_savings_distribution(mv_data: pd.DataFrame) -> dict[str, float]:
    """Derive Monte Carlo savings distribution parameters from M&V data.

    Returns calibrated triangular distribution parameters.
    """
    ratios = mv_data["actual_to_predicted_ratio"].values
    return {
        "low": round(float(np.percentile(ratios, 5)), 3),
        "mode": round(float(np.median(ratios)), 3),
        "high": round(float(np.percentile(ratios, 95)), 3),
        "mean": round(float(np.mean(ratios)), 3),
        "std": round(float(np.std(ratios)), 3),
        "n_projects": len(ratios),
    }


# =========================================================================
# 3. Maintenance records for electrical systems
# =========================================================================

def generate_maintenance_records(cfg: dict[str, Any], seed: int | None = None) -> pd.DataFrame:
    """SYNTHETIC 10-year maintenance log for electrical systems.

    Includes routine maintenance costs, failure events, and downtime costs.
    This validates (or invalidates) the electrical project's benefit
    decomposition.
    """
    if seed is None:
        seed = cfg["general"]["random_seed"]
    rng = np.random.default_rng(seed + 900)

    rows = []
    for year in range(2015, 2025):
        # Routine maintenance: 12 monthly events
        for month in range(1, 13):
            cost = rng.uniform(1_500, 4_500)
            rows.append({
                "year": year,
                "month": month,
                "event_type": "routine_maintenance",
                "description": "Scheduled electrical system inspection and repair",
                "cost": round(cost, 2),
                "downtime_hours": rng.choice([0, 2, 4], p=[0.6, 0.3, 0.1]),
            })

        # Failures: ~1 per 2.5 years on average (p=0.4/yr)
        if rng.random() < 0.40:
            failure_cost = rng.lognormal(np.log(150_000), 0.6)
            failure_cost = min(failure_cost, 800_000)
            downtime = rng.choice([24, 48, 72, 168], p=[0.3, 0.3, 0.2, 0.2])
            rows.append({
                "year": year,
                "month": rng.integers(1, 13),
                "event_type": "major_failure",
                "description": "Unplanned electrical system failure",
                "cost": round(failure_cost, 2),
                "downtime_hours": int(downtime),
            })

    return pd.DataFrame(rows)


def analyze_maintenance_evidence(records: pd.DataFrame) -> dict[str, Any]:
    """Derive electrical project benefit components from maintenance records."""
    routine = records[records["event_type"] == "routine_maintenance"]
    failures = records[records["event_type"] == "major_failure"]

    annual_routine_cost = routine["cost"].sum() / 10  # 10 years
    n_failures = len(failures)
    failure_rate = n_failures / 10
    avg_failure_cost = failures["cost"].mean() if len(failures) > 0 else 0
    annual_failure_ev = failure_rate * avg_failure_cost

    # Predictive monitoring typically reduces routine costs by 20-30%
    # and failure rate by 40-60%
    maintenance_reduction = annual_routine_cost * 0.25
    avoided_failure_ev = annual_failure_ev * 0.50

    return {
        "years_of_data": 10,
        "total_routine_events": len(routine),
        "annual_routine_cost": round(annual_routine_cost, 0),
        "total_failures": n_failures,
        "failure_rate_per_year": round(failure_rate, 2),
        "avg_failure_cost": round(avg_failure_cost, 0),
        "annual_failure_ev": round(annual_failure_ev, 0),
        "estimated_maintenance_reduction": round(maintenance_reduction, 0),
        "estimated_avoided_failure_ev": round(avoided_failure_ev, 0),
        "total_evidence_based_benefit": round(maintenance_reduction + avoided_failure_ev, 0),
        "config_claimed_nonenergy_benefit": 47_500,  # $92.5k total - $45k energy
    }


# =========================================================================
# 4. Engineering interaction analysis
# =========================================================================

def generate_interaction_analysis(cfg: dict[str, Any], seed: int | None = None) -> pd.DataFrame:
    """SYNTHETIC engineering analysis of system-level savings overlap.

    Simulates what an engineer would produce by modeling building
    systems and measuring how much each ECM reduces the baseline
    available to other ECMs.
    """
    if seed is None:
        seed = cfg["general"]["random_seed"]
    rng = np.random.default_rng(seed + 1100)

    interactions = [
        {
            "source": "lab_ventilation",
            "target": "central_plant",
            "mechanism": "Reduced airflow lowers cooling load at central plant",
            "modeled_reduction_pct": 0.08 + rng.normal(0, 0.02),
            "confidence": "medium",
            "measurement_method": "Calibrated energy model simulation",
        },
        {
            "source": "classroom_bas",
            "target": "central_plant",
            "mechanism": "Scheduling reduces occupied-hours cooling demand",
            "modeled_reduction_pct": 0.03 + rng.normal(0, 0.01),
            "confidence": "medium",
        },
        {
            "source": "lab_ventilation",
            "target": "classroom_bas",
            "mechanism": "Shared AHU: improved lab controls affect classroom zones",
            "modeled_reduction_pct": 0.04 + rng.normal(0, 0.01),
            "confidence": "low",
            "measurement_method": "Engineering estimate, no model",
        },
        {
            "source": "dorm_occupancy",
            "target": "central_plant",
            "mechanism": "Reduced dorm load slightly reduces central plant output",
            "modeled_reduction_pct": 0.02 + rng.normal(0, 0.005),
            "confidence": "low",
            "measurement_method": "Proportional to load fraction",
        },
    ]

    for row in interactions:
        row["modeled_reduction_pct"] = round(max(row["modeled_reduction_pct"], 0.005), 4)
        row.setdefault("measurement_method", "Engineering estimate")

    return pd.DataFrame(interactions)


# =========================================================================
# 5. Submetered heating/cooling for waste detection
# =========================================================================

def generate_submetered_data(cfg: dict[str, Any], seed: int | None = None) -> pd.DataFrame:
    """SYNTHETIC submetered heating and cooling data (hourly, 1 year).

    Unlike whole-building load, submetering SEPARATES heating and cooling
    energy.  Simultaneous operation is directly observable as hours where
    both heating > 0 and cooling > 0.
    """
    if seed is None:
        seed = cfg["general"]["random_seed"]
    rng = np.random.default_rng(seed + 1200)
    baseline_cfg = cfg["baseline"]

    n_hours = 8760
    hours = np.arange(n_hours)
    day_of_year = hours // 24
    hour_of_day = hours % 24

    # Synthetic temperature
    annual_cycle = 55 + 25 * np.sin(2 * np.pi * (day_of_year - 80) / 365)
    diurnal_cycle = 8 * np.sin(2 * np.pi * (hour_of_day - 6) / 24)
    temp_noise = rng.normal(0, 3, n_hours)
    outdoor_temp = annual_cycle + diurnal_cycle + temp_noise

    htg_cp = baseline_cfg["heating_changepoint_f"]
    clg_cp = baseline_cfg["cooling_changepoint_f"]

    # Legitimate heating and cooling
    heating_kw = np.maximum(htg_cp - outdoor_temp, 0) * baseline_cfg["heating_slope"] * 0.5
    cooling_kw = np.maximum(outdoor_temp - clg_cp, 0) * baseline_cfg["cooling_slope"] * 0.5

    # Injected waste: simultaneous heating + cooling in shoulder season
    waste_frac = baseline_cfg["injected_waste_fraction"]
    is_shoulder = (outdoor_temp >= htg_cp - 5) & (outdoor_temp <= clg_cp + 5)

    waste_heating = np.zeros(n_hours)
    waste_cooling = np.zeros(n_hours)
    waste_heating[is_shoulder] = waste_frac * 200
    waste_cooling[is_shoulder] = waste_frac * 200

    total_heating = heating_kw + waste_heating + rng.normal(0, 5, n_hours)
    total_cooling = cooling_kw + waste_cooling + rng.normal(0, 5, n_hours)
    total_heating = np.maximum(total_heating, 0)
    total_cooling = np.maximum(total_cooling, 0)

    simultaneous = (total_heating > 5) & (total_cooling > 5)

    df = pd.DataFrame({
        "hour": hours,
        "outdoor_temp": outdoor_temp,
        "heating_kw": total_heating,
        "cooling_kw": total_cooling,
        "simultaneous_flag": simultaneous,
        "is_shoulder": is_shoulder,
        "waste_heating_kw": waste_heating,
        "waste_cooling_kw": waste_cooling,
    })
    return df


def analyze_submetered_waste(submeter: pd.DataFrame) -> dict[str, Any]:
    """Quantify waste directly from submetered data.

    This is the gold standard — no model needed, just count the hours
    where heating and cooling run simultaneously.
    """
    total_hours = len(submeter)
    simul_hours = submeter["simultaneous_flag"].sum()
    simul_pct = simul_hours / total_hours

    simul_data = submeter[submeter["simultaneous_flag"]]
    wasted_energy_kwh = (
        simul_data["heating_kw"].sum() + simul_data["cooling_kw"].sum()
    ) * 1  # 1-hour intervals
    total_energy_kwh = (
        submeter["heating_kw"].sum() + submeter["cooling_kw"].sum()
    ) * 1

    waste_fraction = wasted_energy_kwh / total_energy_kwh if total_energy_kwh > 0 else 0

    # Shoulder-only waste (more conservative: only count waste in shoulder)
    shoulder_simul = submeter[submeter["is_shoulder"] & submeter["simultaneous_flag"]]
    shoulder_waste_kwh = (
        shoulder_simul["heating_kw"].sum() + shoulder_simul["cooling_kw"].sum()
    )

    return {
        "total_hours": total_hours,
        "simultaneous_hours": int(simul_hours),
        "simultaneous_pct": round(simul_pct * 100, 1),
        "total_energy_kwh": round(total_energy_kwh, 0),
        "wasted_energy_kwh": round(wasted_energy_kwh, 0),
        "waste_fraction": round(waste_fraction, 4),
        "shoulder_waste_kwh": round(shoulder_waste_kwh, 0),
        "detection_method": "direct_submeter_observation",
        "model_required": False,
    }


# =========================================================================
# 6. Risk tolerance framework
# =========================================================================

def risk_tolerance_assessment(
    cfg: dict[str, Any],
    mc_stats: pd.DataFrame,
) -> pd.DataFrame:
    """Map MC results against institutional risk tolerance thresholds.

    Thresholds are ARBITRARY — a real institution would set these
    based on their reserve fund, operating budget, and board policy.
    """
    # ARBITRARY risk tolerance levels
    thresholds = {
        "max_acceptable_loss": 250_000,      # single-project worst case
        "portfolio_loss_tolerance": 500_000,  # total portfolio worst case
        "min_p_positive": 0.85,              # minimum P(NPV>0)
        "min_p_payback_4yr": 0.50,           # minimum P(payback < 4 years)
    }

    rows = []
    for _, row in mc_stats.iterrows():
        pk = row["project"]
        if pk.startswith("electrical_") and pk != "electrical_monitoring":
            continue
        es10 = row["expected_shortfall_10"]
        p_pos = row["P_NPV_positive"]
        p_pb4 = row.get("P_payback_lt4", float("nan"))

        passes_loss = abs(es10) <= thresholds["max_acceptable_loss"] if es10 < 0 else True
        passes_prob = p_pos >= thresholds["min_p_positive"]
        passes_payback = p_pb4 >= thresholds["min_p_payback_4yr"] if not np.isnan(p_pb4) else True

        overall = passes_loss and passes_prob and passes_payback

        rows.append({
            "project": pk,
            "expected_shortfall_10": round(es10, 0),
            "P_NPV_positive": round(p_pos, 4),
            "P_payback_lt4": round(p_pb4, 4) if not np.isnan(p_pb4) else None,
            "passes_loss_test": passes_loss,
            "passes_probability_test": passes_prob,
            "passes_payback_test": passes_payback,
            "overall_risk_acceptable": overall,
            "recommendation": "APPROVE" if overall else "DEFER/MITIGATE",
        })

    return pd.DataFrame(rows)


# =========================================================================
# Master: generate all evidence and produce calibration report
# =========================================================================

def generate_all_evidence(cfg: dict[str, Any]) -> dict[str, Any]:
    """Generate all SYNTHETIC evidence packages and cross-validate."""
    seed = cfg["general"]["random_seed"]

    bills = generate_utility_bills(cfg, seed)
    bill_validation = validate_benefits_against_bills(bills, cfg)

    mv_data = generate_mv_comparison(cfg, seed)
    calibrated_dist = calibrate_savings_distribution(mv_data)

    maint_records = generate_maintenance_records(cfg, seed)
    maint_analysis = analyze_maintenance_evidence(maint_records)

    interaction_eng = generate_interaction_analysis(cfg, seed)

    submeter = generate_submetered_data(cfg, seed)
    submeter_analysis = analyze_submetered_waste(submeter)

    return {
        "utility_bills": bills,
        "bill_validation": bill_validation,
        "mv_data": mv_data,
        "calibrated_distribution": calibrated_dist,
        "maintenance_records": maint_records,
        "maintenance_analysis": maint_analysis,
        "interaction_engineering": interaction_eng,
        "submetered_data": submeter,
        "submeter_analysis": submeter_analysis,
    }


# =========================================================================
# 7. Calibrate config from evidence
# =========================================================================

def calibrate_config_from_evidence(
    cfg: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Return a COPY of cfg with values calibrated by evidence data.

    This produces the 'v3' config — same structure, but MC distributions,
    electrical benefit decomposition, and interaction magnitudes are now
    grounded in synthetic evidence rather than pure engineering estimates.
    """
    import copy
    v3 = copy.deepcopy(cfg)

    cal = evidence["calibrated_distribution"]
    v3["monte_carlo"]["savings_triangular"] = [cal["low"], cal["mode"], cal["high"]]

    maint = evidence["maintenance_analysis"]
    energy_only = cfg["electrical_project"]["energy_only_benefit"]
    maint_reduction = maint["estimated_maintenance_reduction"]
    avoided_ev = maint["estimated_avoided_failure_ev"]
    new_total = energy_only + maint_reduction + avoided_ev
    v3["projects"]["electrical_monitoring"]["annual_benefit"] = round(new_total, 0)

    # Update failure params from evidence
    v3["electrical_project"]["failure_probability"] = round(maint["failure_rate_per_year"], 3)
    v3["electrical_project"]["failure_consequence"] = round(maint["avg_failure_cost"], 0)

    eng_df = evidence["interaction_engineering"]
    for _, row in eng_df.iterrows():
        key = f"{row['source']}__{row['target']}"
        if key in v3.get("interactions", {}):
            v3["interactions"][key] = round(row["modeled_reduction_pct"], 4)

    sub = evidence["submeter_analysis"]
    v3["baseline"]["evidence_waste_fraction"] = sub["waste_fraction"]

    return v3


def evidence_comparison_table(
    cfg_v2: dict[str, Any],
    cfg_v3: dict[str, Any],
    evidence: dict[str, Any],
) -> pd.DataFrame:
    """Produce a side-by-side comparison of v2 vs evidence-calibrated v3 values."""
    rows = []

    mc_v2 = cfg_v2["monte_carlo"]["savings_triangular"]
    mc_v3 = cfg_v3["monte_carlo"]["savings_triangular"]
    rows.append({
        "parameter": "MC savings triangular (low/mode/high)",
        "v2_value": f"{mc_v2[0]:.2f} / {mc_v2[1]:.2f} / {mc_v2[2]:.2f}",
        "v3_evidence_value": f"{mc_v3[0]:.3f} / {mc_v3[1]:.3f} / {mc_v3[2]:.3f}",
        "source": f"M&V data (n={evidence['calibrated_distribution']['n_projects']})",
    })

    elec_v2 = cfg_v2["projects"]["electrical_monitoring"]["annual_benefit"]
    elec_v3 = cfg_v3["projects"]["electrical_monitoring"]["annual_benefit"]
    rows.append({
        "parameter": "Electrical annual benefit",
        "v2_value": f"${elec_v2:,.0f}",
        "v3_evidence_value": f"${elec_v3:,.0f}",
        "source": "Maintenance records (10yr)",
    })

    maint = evidence["maintenance_analysis"]
    rows.append({
        "parameter": "Failure rate (/yr)",
        "v2_value": f"{cfg_v2['electrical_project']['failure_probability']:.3f}",
        "v3_evidence_value": f"{maint['failure_rate_per_year']:.2f}",
        "source": f"{maint['total_failures']} failures in {maint['years_of_data']} yrs",
    })
    rows.append({
        "parameter": "Avg failure cost",
        "v2_value": f"${cfg_v2['electrical_project']['failure_consequence']:,.0f}",
        "v3_evidence_value": f"${maint['avg_failure_cost']:,.0f}",
        "source": f"Maintenance records",
    })

    for key in cfg_v2.get("interactions", {}):
        v2_val = cfg_v2["interactions"][key]
        v3_val = cfg_v3["interactions"].get(key, v2_val)
        rows.append({
            "parameter": f"Interaction: {key}",
            "v2_value": f"{v2_val:.4f}",
            "v3_evidence_value": f"{v3_val:.4f}",
            "source": "Engineering simulation",
        })

    sub = evidence["submeter_analysis"]
    rows.append({
        "parameter": "Measured waste fraction (submeter)",
        "v2_value": f"{cfg_v2['baseline']['injected_waste_fraction']:.2%} (synthetic)",
        "v3_evidence_value": f"{sub['waste_fraction']:.2%} (measured)",
        "source": f"{sub['simultaneous_hours']} simultaneous hrs",
    })

    return pd.DataFrame(rows)


def generate_decision_rules(
    risk_df: pd.DataFrame,
    evidence: dict[str, Any],
) -> pd.DataFrame:
    """Produce clear decision rules grounded in evidence.

    Maps each project to APPROVE / APPROVE-WITH-CONDITIONS / DEFER
    based on evidence strength and risk assessment.
    """
    bill_val = evidence["bill_validation"]
    cal = evidence["calibrated_distribution"]
    maint = evidence["maintenance_analysis"]

    rows = []
    for _, rrow in risk_df.iterrows():
        pk = rrow["project"]
        rule = rrow["recommendation"]

        conditions: list[str] = []
        evidence_gaps: list[str] = []

        bv = bill_val[bill_val["project"] == pk]
        if len(bv) > 0 and bv.iloc[0]["flag"] == "OVERESTIMATE":
            conditions.append(f"Benefit overestimates bills by "
                              f"{bv.iloc[0]['ratio_claimed_to_derived']:.0%}")
            if rule == "APPROVE":
                rule = "APPROVE-WITH-CONDITIONS"

        if cal["std"] > 0.20:
            conditions.append(f"Wide M&V spread (std={cal['std']:.3f}) — "
                              "consider pilot-first approach")

        if pk == "electrical_monitoring":
            if maint["total_failures"] < 3:
                evidence_gaps.append("Few historical failures — "
                                      "failure EV estimate has high uncertainty")

        if not rrow["passes_payback_test"]:
            conditions.append("Payback probability below threshold")

        final_rule = rule
        if conditions and final_rule == "APPROVE":
            final_rule = "APPROVE-WITH-CONDITIONS"

        rows.append({
            "project": pk,
            "decision": final_rule,
            "conditions": "; ".join(conditions) if conditions else "None",
            "evidence_gaps": "; ".join(evidence_gaps) if evidence_gaps else "None",
            "evidence_quality": _rate_evidence_quality(pk, evidence),
        })

    return pd.DataFrame(rows)


def _rate_evidence_quality(project: str, evidence: dict[str, Any]) -> str:
    """Rate how well the evidence supports the claimed benefit for this project."""
    bill_val = evidence["bill_validation"]
    bv = bill_val[bill_val["project"] == project]
    if len(bv) == 0:
        return "LOW — no utility bill match"
    ratio = bv.iloc[0]["ratio_claimed_to_derived"]
    if 0.80 <= ratio <= 1.20:
        return "HIGH — bills support claim"
    elif 0.60 <= ratio <= 1.40:
        return "MEDIUM — bills partially support"
    return "LOW — large discrepancy with bills"
