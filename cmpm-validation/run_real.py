#!/usr/bin/env python3
"""CMPM Validation Harness — Run with REAL data where available.

Uses real weather, utility bills, submeter, occupancy, and maintenance
data from data/real/. Falls back to synthetic generation per-building
when real data is missing. Every output is tagged with its data source.

Usage:
    python3 run_real.py              # full run, auto-detect real data
    python3 run_real.py --check      # just report what data is available
    python3 run_real.py --building lab_ventilation  # run single building
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cmpm.config_loader import load_config
from cmpm.data_loader import (
    DataAvailability,
    bills_for_building,
    bills_to_evidence_format,
    discover_data,
    generate_load_from_real_data,
    load_weather,
    occupancy_to_hourly_array,
    submeter_for_building,
    weather_to_hourly_series,
)
from cmpm.baseline import (
    evaluate_waste_recovery,
    generate_synthetic_load,
)
from cmpm.evidence import (
    analyze_maintenance_evidence,
    analyze_submetered_waste,
    calibrate_config_from_evidence,
    calibrate_savings_distribution,
    evidence_comparison_table,
    generate_all_evidence,
    generate_decision_rules,
    generate_interaction_analysis,
    generate_maintenance_records,
    generate_mv_comparison,
    generate_submetered_data,
    generate_utility_bills,
    risk_tolerance_assessment,
    validate_benefits_against_bills,
)
from cmpm.economics import (
    base_friction_kwargs,
    compute_npv,
    compute_irr,
    compute_simple_payback,
    compute_discounted_payback,
    breakeven_benefit,
)
from cmpm.uncertainty import run_monte_carlo_all_projects
from cmpm.interactions import enumerate_all_subsets, sequencing_analysis
from cmpm.optimize import budget_sweep, efficient_frontier, multi_year_milp, shadow_prices
from cmpm.scoring import (
    correlation_double_counting,
    normalization_sensitivity,
    rank_disagreement,
    weight_stability_analysis,
)
from cmpm.diagnostics import format_diagnostic_report, run_all_diagnostics
from cmpm.utils import format_currency, format_pct
from cmpm.public_data import (
    apply_public_data_to_config,
    building_eui_comparison,
    generate_public_data_report,
    get_eia_rate,
)

OUT = Path(__file__).resolve().parent / "outputs"


def ensure_output_dir() -> None:
    OUT.mkdir(exist_ok=True)


def banner(msg: str) -> None:
    print(f"\n{'='*70}")
    print(msg)
    print(f"{'='*70}")


def section(msg: str) -> None:
    print(f"\n--- {msg} ---")


# =========================================================================
# Baseline with real weather
# =========================================================================

def build_baseline_data(
    cfg: dict[str, Any],
    real_data: dict[str, Any],
    avail: DataAvailability,
) -> pd.DataFrame:
    """Build the baseline load dataset using real weather if available."""
    if avail.weather and real_data.get("weather_temps") is not None:
        print("  Using REAL weather data (NOAA ISD)")
        temps = real_data["weather_temps"]
        data = generate_load_from_real_data(cfg, temps)
        return data
    else:
        print("  Using SYNTHETIC weather data")
        return generate_synthetic_load(cfg)


# =========================================================================
# Evidence with real data
# =========================================================================

def build_evidence(
    cfg: dict[str, Any],
    real_data: dict[str, Any],
    avail: DataAvailability,
    baseline_data: pd.DataFrame,
) -> dict[str, Any]:
    """Build evidence packages, using real data where available."""
    seed = cfg["general"]["random_seed"]
    sources: dict[str, str] = {}

    # Utility bills
    if real_data.get("bills") is not None and any(avail.bills.values()):
        real_bills = bills_to_evidence_format(real_data["bills"], cfg)
        synth_bills = generate_utility_bills(cfg, seed)
        # Merge: use real where available, synthetic for gaps
        real_buildings = set(real_bills["building"].unique())
        synth_fill = synth_bills[~synth_bills["building"].isin(real_buildings)]
        bills = pd.concat([real_bills, synth_fill], ignore_index=True)
        for bldg in cfg["projects"]:
            sources[f"bills_{bldg}"] = "REAL" if bldg in real_buildings else "SYNTHETIC"
        print(f"  Utility bills: {len(real_buildings)} REAL, "
              f"{len(cfg['projects']) - len(real_buildings)} SYNTHETIC")
    else:
        bills = generate_utility_bills(cfg, seed)
        for bldg in cfg["projects"]:
            sources[f"bills_{bldg}"] = "SYNTHETIC"
        print("  Utility bills: ALL SYNTHETIC")

    bill_validation = validate_benefits_against_bills(bills, cfg)

    # M&V comparison — always synthetic until real M&V data is provided
    mv_data = generate_mv_comparison(cfg, seed)
    calibrated_dist = calibrate_savings_distribution(mv_data)
    sources["mv_data"] = "SYNTHETIC"
    print("  M&V data: SYNTHETIC")

    # Maintenance records
    if avail.maintenance and real_data.get("maintenance") is not None:
        maint_records = real_data["maintenance"]
        sources["maintenance"] = "REAL"
        print("  Maintenance records: REAL")
    else:
        maint_records = generate_maintenance_records(cfg, seed)
        sources["maintenance"] = "SYNTHETIC"
        print("  Maintenance records: SYNTHETIC")

    maint_analysis = analyze_maintenance_evidence(maint_records)

    # Interaction analysis — always engineering estimate
    interaction_eng = generate_interaction_analysis(cfg, seed)
    sources["interactions"] = "ENGINEERING_ESTIMATE"

    # Submeter data
    if real_data.get("submeters") is not None and any(avail.submeters.values()):
        real_sub_buildings = [b for b, v in avail.submeters.items() if v]
        # Use real submeter for the first available building
        bldg = real_sub_buildings[0]
        submeter = submeter_for_building(real_data["submeters"], bldg)
        # Convert to expected format
        submeter = submeter.rename(columns={"outdoor_temp_f": "outdoor_temp"})
        if "simultaneous_flag" not in submeter.columns:
            submeter["simultaneous_flag"] = (submeter["heating_kw"] > 5) & (submeter["cooling_kw"] > 5)
        if "is_shoulder" not in submeter.columns:
            htg_cp = cfg["baseline"]["heating_changepoint_f"]
            clg_cp = cfg["baseline"]["cooling_changepoint_f"]
            if "outdoor_temp" in submeter.columns:
                submeter["is_shoulder"] = (
                    (submeter["outdoor_temp"] >= htg_cp - 5) & (submeter["outdoor_temp"] <= clg_cp + 5)
                )
            else:
                submeter["is_shoulder"] = False
        if "waste_heating_kw" not in submeter.columns:
            submeter["waste_heating_kw"] = 0
            submeter["waste_cooling_kw"] = 0
        if "hour" not in submeter.columns:
            submeter["hour"] = range(len(submeter))
        sources["submeter"] = f"REAL ({bldg})"
        print(f"  Submeter data: REAL ({bldg})")
    else:
        submeter = generate_submetered_data(cfg, seed)
        sources["submeter"] = "SYNTHETIC"
        print("  Submeter data: SYNTHETIC")

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
        "data_sources": sources,
    }


# =========================================================================
# Report generation
# =========================================================================

def generate_data_source_report(avail: DataAvailability, sources: dict[str, str]) -> str:
    """Generate a detailed report on data provenance."""
    lines = [
        "# Data Source Report",
        "",
        "This section documents the source of every data input used in this analysis.",
        "Items marked **REAL** use actual campus data. Items marked **SYNTHETIC** use",
        "fabricated data for demonstration — those results should NOT be used for decisions.",
        "",
    ]

    lines.append("## Weather Data")
    lines.append(f"- Source: **{'REAL (NOAA ISD)' if avail.weather else 'SYNTHETIC'}**")
    if avail.weather:
        lines.append("- Station: Chicago O'Hare (725300-94846)")
        lines.append("- Period: 2024-2025 hourly observations")
    lines.append("")

    lines.append("## Building Data")
    lines.append("")
    lines.append("| Building | Utility Bills | Submeter | Occupancy |")
    lines.append("|----------|--------------|----------|-----------|")
    for bldg in sorted(avail.bills.keys()):
        b = "REAL" if avail.bills.get(bldg) else "SYNTHETIC"
        s = "REAL" if avail.submeters.get(bldg) else "SYNTHETIC"
        o = "REAL" if avail.occupancy.get(bldg) else "SYNTHETIC"
        lines.append(f"| {bldg} | **{b}** | **{s}** | **{o}** |")
    lines.append("")

    lines.append("## Other Data")
    lines.append(f"- Maintenance records: **{'REAL' if avail.maintenance else 'SYNTHETIC'}**")
    lines.append(f"- M&V comparison: **{sources.get('mv_data', 'SYNTHETIC')}**")
    lines.append(f"- Interaction analysis: **{sources.get('interactions', 'ENGINEERING_ESTIMATE')}**")
    lines.append("")

    real_count = sum(1 for v in avail.bills.values() if v)
    total = len(avail.bills)
    pct = (real_count / total * 100) if total > 0 else 0
    lines.append(f"## Coverage: {real_count}/{total} buildings have real utility data ({pct:.0f}%)")
    lines.append("")

    if pct < 100:
        missing = [b for b, v in avail.bills.items() if not v]
        lines.append(f"**Still needed:** Real utility bills for: {', '.join(missing)}")
        lines.append("")

    return "\n".join(lines)


# =========================================================================
# Main pipeline
# =========================================================================

def run_check_only(cfg: dict[str, Any]) -> None:
    """Just report what data is available without running the model."""
    banner("DATA AVAILABILITY CHECK")
    _, avail = discover_data(cfg)
    print(avail.report())

    print("\nFiles found in data/real/:")
    real_dir = Path(__file__).resolve().parent / "data" / "real"
    if real_dir.exists():
        for f in sorted(real_dir.iterdir()):
            if f.is_file():
                size = f.stat().st_size
                print(f"  {f.name} ({size:,} bytes)")
    else:
        print("  (no files)")

    print("\nWeather data:")
    weather_dir = Path(__file__).resolve().parent / "data" / "weather"
    if weather_dir.exists():
        for f in sorted(weather_dir.iterdir()):
            if f.is_file():
                size = f.stat().st_size
                print(f"  {f.name} ({size:,} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(description="CMPM Validation with Real Data")
    parser.add_argument("--check", action="store_true", help="Only check data availability")
    parser.add_argument("--building", type=str, help="Run for a single building")
    args = parser.parse_args()

    ensure_output_dir()
    cfg = load_config()

    if args.check:
        run_check_only(cfg)
        return

    banner("CMPM VALIDATION HARNESS — REAL DATA MODE")
    real_data, avail = discover_data(cfg)
    print(avail.report())

    # ── Apply public government data ──
    section("Step 0: Government Data Integration")
    cfg = apply_public_data_to_config(cfg)
    pub_report = generate_public_data_report(cfg)
    (OUT / "real_public_data_report.md").write_text(pub_report)

    eui_comp = building_eui_comparison(cfg)
    eui_comp.to_csv(OUT / "real_cbecs_eui_comparison.csv", index=False)

    eia_rate = get_eia_rate("IL")
    print(f"  EIA commercial rate (IL): ${eia_rate:.4f}/kWh")
    print(f"  EIA escalation rate (IL 10yr CAGR): {cfg['frictions']['energy_escalation_rate']:.4%}/yr")
    print(f"  IEEE campus failure rate: {cfg['electrical_project']['failure_probability']:.4f}/yr")
    print(f"  DOE M&V savings distribution: {cfg['monte_carlo']['savings_triangular']}")
    print(f"  CBECS EUI comparison:")
    print(eui_comp[["project", "cbecs_type", "cbecs_eui_mean_kbtu", "cbecs_elec_eui_kwh_sf"]].to_string(index=False))

    for change in cfg.get("_public_data_changes", []):
        print(f"  CHANGED {change['parameter']}: {change['old']} -> {change['new']} ({change['source']})")

    fkw = base_friction_kwargs(cfg)
    rate = cfg["general"]["discount_rate"]
    life = cfg["general"]["analysis_life_years"]

    # ── Step 1: Economics (uses config values, not data) ──
    section("Step 1: Deterministic Economics")
    rows = []
    for pk in cfg["projects"]:
        p = cfg["projects"][pk]
        npv_clean = compute_npv(p["capex"], p["annual_benefit"], rate, life, cross_check=False)
        irr = compute_irr(p["capex"], p["annual_benefit"], life)
        pb = compute_simple_payback(p["capex"], p["annual_benefit"])
        npv_friction = compute_npv(
            p["capex"], p["annual_benefit"], rate, life, cross_check=False, **fkw
        ) if fkw else npv_clean
        dpb = compute_discounted_payback(p["capex"], p["annual_benefit"], rate, life, **fkw)
        be = breakeven_benefit(p["capex"], rate, life)
        rows.append({
            "project": pk,
            "npv_no_friction": npv_clean,
            "npv_with_friction": npv_friction,
            "npv_reduction_pct": (1 - npv_friction / npv_clean) * 100 if npv_clean != 0 else 0,
            "computed_payback": pb,
            "computed_irr": irr,
            "discounted_payback": dpb,
            "breakeven_benefit": be,
        })
    replication = pd.DataFrame(rows)
    replication.to_csv(OUT / "real_step1_economics.csv", index=False)
    print(replication[["project", "npv_no_friction", "npv_with_friction", "npv_reduction_pct"]].to_string(index=False))

    # ── Step 2: Monte Carlo ──
    section("Step 2: Monte Carlo Simulation")
    mc_results = run_monte_carlo_all_projects(cfg)
    mc_rows = []
    for pk, res in mc_results.items():
        row = {"project": pk}
        row.update(res["stats"])
        mc_rows.append(row)
    mc_stats = pd.DataFrame(mc_rows)
    mc_stats.to_csv(OUT / "real_step2_mc_stats.csv", index=False)
    print(mc_stats[["project", "P10", "P50", "P90", "P_NPV_positive"]].to_string(index=False))

    # ── Step 3: Baseline with real weather ──
    section("Step 3: Baseline Model (Real Weather)")
    baseline_data = build_baseline_data(cfg, real_data, avail)
    baseline_eval = evaluate_waste_recovery(baseline_data, cfg)
    baseline_eval["weather_source"] = "REAL" if avail.weather else "SYNTHETIC"
    baseline_eval.to_csv(OUT / "real_step3_baseline.csv", index=False)
    print(baseline_eval.to_string(index=False))

    # ── Step 4: Evidence packages ──
    section("Step 4: Evidence Generation")
    evidence = build_evidence(cfg, real_data, avail, baseline_data)
    sources = evidence.get("data_sources", {})

    evidence["utility_bills"].to_csv(OUT / "real_evidence_utility_bills.csv", index=False)
    evidence["bill_validation"].to_csv(OUT / "real_evidence_bill_validation.csv", index=False)
    evidence["mv_data"].to_csv(OUT / "real_evidence_mv_data.csv", index=False)
    evidence["maintenance_records"].to_csv(OUT / "real_evidence_maintenance.csv", index=False)
    evidence["interaction_engineering"].to_csv(OUT / "real_evidence_interactions.csv", index=False)

    # Risk assessment
    risk_df = risk_tolerance_assessment(cfg, mc_stats)
    risk_df.to_csv(OUT / "real_evidence_risk.csv", index=False)

    # Calibrate v3
    cfg_v3 = calibrate_config_from_evidence(cfg, evidence)
    comparison = evidence_comparison_table(cfg, cfg_v3, evidence)
    comparison.to_csv(OUT / "real_evidence_comparison.csv", index=False)

    decisions = generate_decision_rules(risk_df, evidence)
    decisions.to_csv(OUT / "real_evidence_decisions.csv", index=False)

    print("\nBill validation:")
    print(evidence["bill_validation"].to_string(index=False))
    print("\nRisk assessment:")
    print(risk_df[["project", "recommendation"]].to_string(index=False))
    print("\nDecision rules:")
    print(decisions[["project", "decision", "evidence_quality"]].to_string(index=False))

    # ── Step 5: Scoring ──
    section("Step 5: Scoring & Rankings")
    ws_result = weight_stability_analysis(cfg)
    ws_result["summary"].to_csv(OUT / "real_step5_weight_stability.csv", index=False)
    norm_df = normalization_sensitivity(cfg)
    corr_result = correlation_double_counting(cfg)
    rank_df = rank_disagreement(cfg)
    rank_df.to_csv(OUT / "real_step5_rankings.csv", index=False)
    print(rank_df[["project", "score_rank", "pi_rank", "npv_rank"]].to_string(index=False))

    # ── Step 6: Interactions ──
    section("Step 6: Project Interactions")
    subset_df = enumerate_all_subsets(cfg)
    subset_df.to_csv(OUT / "real_step6_subsets.csv", index=False)
    seq_df = sequencing_analysis(cfg)
    seq_df.to_csv(OUT / "real_step6_sequencing.csv", index=False)
    print(subset_df.head(5)[["subset", "naive_npv", "adjusted_npv", "overstatement"]].to_string(index=False))

    # ── Step 7: Optimization ──
    section("Step 7: Budget Optimization")
    sweep_df = budget_sweep(cfg)
    sweep_df.to_csv(OUT / "real_step7_budget_sweep.csv", index=False)
    ef = efficient_frontier(sweep_df)
    my_result = multi_year_milp(cfg)
    print(f"Frontier flattens at budget = {format_currency(ef['flatten_budget'])}")

    # ── Step 8: Diagnostics ──
    section("Step 8: Diagnostics")
    diag_results = run_all_diagnostics(cfg)
    diag_report = format_diagnostic_report(diag_results, cfg)
    (OUT / "real_diagnostics_report.md").write_text(diag_report)

    gb_gap = diag_results["gradient_boosting"]["train_test_gap"]
    print(f"  GB overfit ratio: {gb_gap['overfit_ratio']:.3f} — {gb_gap['diagnosis']}")
    cp_diag = diag_results["changepoint_regression"]
    print(f"  CP lag-1 ACF: {cp_diag['lag1_autocorrelation']:.3f} — {cp_diag['diagnosis']}")

    # ── Data provenance report ──
    section("Data Provenance Report")
    provenance = generate_data_source_report(avail, sources)
    (OUT / "real_data_provenance.md").write_text(provenance)
    print(provenance)

    # ── Final summary ──
    banner("FINAL SUMMARY")

    evidence_result = {
        "evidence": evidence,
        "risk": risk_df,
        "cfg_v3": cfg_v3,
        "comparison": comparison,
        "decisions": decisions,
    }

    # Generate full report
    from run_all import generate_report
    sensitivity_stub = {
        "survival": pd.DataFrame(),
        "tornado": pd.DataFrame(),
        "frictions": pd.DataFrame(),
        "tornado_dfs": {},
    }
    interact_stub = {"subsets": subset_df, "sequencing": seq_df}
    opt_stub = {"sweep": sweep_df, "shadow_prices": pd.DataFrame(),
                "multi_year": my_result, "frontier": ef}
    scoring_stub = {
        "weight_stability": ws_result, "normalization": norm_df,
        "correlation": corr_result, "rank_disagreement": rank_df,
    }

    # Count real vs synthetic
    real_count = sum(1 for v in avail.bills.values() if v)
    total = len(avail.bills)
    print(f"\nBuildings with REAL utility data: {real_count}/{total}")
    print(f"Weather: {'REAL (NOAA ISD)' if avail.weather else 'SYNTHETIC'}")
    print(f"Maintenance: {'REAL' if avail.maintenance else 'SYNTHETIC'}")

    print("\nProject rankings (final):")
    print(rank_df[["project", "score_rank", "composite_score"]].to_string(index=False))

    print("\nDecision recommendations:")
    for _, r in decisions.iterrows():
        print(f"  {r['project']}: {r['decision']} ({r['evidence_quality']})")

    if real_count < total:
        missing = [b for b, v in avail.bills.items() if not v]
        print(f"\n⚠ Still need real utility data for: {', '.join(missing)}")
        print("  Drop CSV files in data/real/ and re-run.")

    print(f"\nAll outputs written to {OUT}/")
    print("Files prefixed with 'real_' to distinguish from synthetic-only runs.")


if __name__ == "__main__":
    main()
