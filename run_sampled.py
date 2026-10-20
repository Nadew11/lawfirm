#!/usr/bin/env python3
"""CMPM Validation Harness — Run with SAMPLED campus data.

When real campus data is unavailable, this runner samples realistic building
profiles from the Chicago Energy Benchmarking dataset (28,000+ real buildings)
and uses them as inputs. This is NOT synthetic/arbitrary data — it's real
energy data from real Chicago buildings matched to each project type.

Data source hierarchy:
  1. Real campus data (data/real/) — used if available
  2. Chicago Energy Benchmarking — sampled buildings for missing data
  3. Government benchmarks (EIA, CBECS, DOE, IEEE) — for rate/cost parameters

Usage:
    python3 run_sampled.py                  # full run with sampled campus
    python3 run_sampled.py --check          # show what would be sampled
    python3 run_sampled.py --seed 123       # different random campus sample
    python3 run_sampled.py --compare        # compare sampled vs original config
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
from cmpm.campus_sampler import (
    CampusProfile,
    apply_sampled_campus_to_config,
    compute_savings_from_sampled,
    generate_all_sampled_bills,
    generate_campus_report,
    get_building_type_stats,
    get_peer_comparison,
    sample_campus,
)
from cmpm.data_loader import (
    DataAvailability,
    discover_data,
    generate_load_from_real_data,
    load_weather,
    weather_to_hourly_series,
)
from cmpm.baseline import evaluate_waste_recovery, generate_synthetic_load
from cmpm.evidence import (
    analyze_maintenance_evidence,
    analyze_submetered_waste,
    calibrate_config_from_evidence,
    calibrate_savings_distribution,
    evidence_comparison_table,
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
    breakeven_benefit,
    compute_discounted_payback,
    compute_irr,
    compute_npv,
    compute_simple_payback,
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


def run_check(cfg: dict[str, Any], seed: int) -> None:
    """Show what buildings would be sampled and how they compare."""
    banner("CAMPUS SAMPLING CHECK")

    campus = sample_campus(cfg, seed=seed)
    print(f"Sampled {len(campus.buildings)} buildings (seed={seed})\n")

    for key, bldg in campus.buildings.items():
        peer = get_peer_comparison(key, bldg)
        print(f"  {key}:")
        print(f"    Matched to: {bldg.source_building_name} (ID {bldg.source_building_id})")
        print(f"    Type: {bldg.building_type}, {bldg.area_sqft:,.0f} sqft")
        print(f"    EUI: {bldg.site_eui_kbtu:.1f} kBtu/sqft "
              f"({peer['percentile_rank']:.0f}th pctl of {peer['n_peers']} peers)")
        print(f"    Annual: {bldg.annual_kwh:,.0f} kWh, {bldg.annual_therms:,.0f} therms")
        print(f"    Est. cost: ${bldg.annual_cost_estimate:,.0f}/yr")
        print()

    print("\nBuilding type distributions (from Chicago data):")
    for btype in ["College/University", "Residence Hall/Dormitory", "Laboratory"]:
        stats = get_building_type_stats(btype)
        if stats:
            print(f"\n  {btype} (n={stats['n_buildings']}):")
            print(f"    EUI: mean={stats['eui_mean']:.1f}, "
                  f"median={stats['eui_median']:.1f}, "
                  f"IQR=[{stats['eui_p25']:.1f}, {stats['eui_p75']:.1f}]")


def run_compare(cfg: dict[str, Any], seed: int) -> None:
    """Compare sampled building parameters against original config assumptions."""
    banner("SAMPLED vs. ORIGINAL CONFIG COMPARISON")

    campus = sample_campus(cfg, seed=seed)
    rate = get_eia_rate("IL")

    print(f"{'Project':<25} {'Config Benefit':>15} {'Sampled Annual $':>17} {'Sampled kWh':>15} {'EUI':>8}")
    print("-" * 85)

    for key in cfg["projects"]:
        proj = cfg["projects"][key]
        bldg = campus.buildings.get(key)
        if bldg is None:
            print(f"{key:<25} ${proj['annual_benefit']:>13,}  {'(no sample)':>17}")
            continue

        print(f"{key:<25} ${proj['annual_benefit']:>13,} ${bldg.annual_cost_estimate:>15,.0f} "
              f"{bldg.annual_kwh:>14,.0f} {bldg.site_eui_kbtu:>7.1f}")

    print()
    print("Note: 'Config Benefit' is the assumed annual savings in config.yaml.")
    print("      'Sampled Annual $' is the total energy cost of the sampled building.")
    print("      The savings fraction determines what portion is actually recoverable.")


def main() -> None:
    parser = argparse.ArgumentParser(description="CMPM Validation with Sampled Campus Data")
    parser.add_argument("--check", action="store_true", help="Show sampling preview")
    parser.add_argument("--compare", action="store_true", help="Compare sampled vs config")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for sampling")
    args = parser.parse_args()

    ensure_output_dir()
    cfg = load_config()

    if args.check:
        run_check(cfg, args.seed)
        return
    if args.compare:
        run_compare(cfg, args.seed)
        return

    banner("CMPM VALIDATION HARNESS — SAMPLED CAMPUS MODE")

    # ── Step 0a: Sample campus buildings from Chicago benchmarking ──
    section("Step 0a: Sample Campus from Chicago Energy Benchmarking")
    campus = sample_campus(cfg, seed=args.seed)
    cfg = apply_sampled_campus_to_config(cfg, campus)

    report = generate_campus_report(campus)
    (OUT / "sampled_campus_report.md").write_text(report)

    for prov in campus.provenance:
        print(f"  {prov}")
    print(f"\n  Campus report written to outputs/sampled_campus_report.md")

    # ── Step 0b: Government data integration ──
    section("Step 0b: Government Data Integration")
    cfg = apply_public_data_to_config(cfg)
    pub_report = generate_public_data_report(cfg)
    (OUT / "sampled_public_data_report.md").write_text(pub_report)

    eia_rate = get_eia_rate("IL")
    print(f"  EIA commercial rate (IL): ${eia_rate:.4f}/kWh")
    print(f"  EIA escalation rate: {cfg['frictions']['energy_escalation_rate']:.4%}/yr")
    print(f"  DOE M&V savings distribution: {cfg['monte_carlo']['savings_triangular']}")

    for change in cfg.get("_public_data_changes", []):
        print(f"  CHANGED {change['parameter']}: {change['old']} -> {change['new']} ({change['source']})")

    # ── Step 0c: Generate utility bills from sampled buildings ──
    section("Step 0c: Generate Utility Bills from Sampled Buildings")
    sampled_bills = generate_all_sampled_bills(campus, n_years=3)
    sampled_bills.to_csv(OUT / "sampled_utility_bills.csv", index=False)
    print(f"  Generated {len(sampled_bills)} monthly bill records for {len(campus.buildings)} buildings")
    for key, bldg in campus.buildings.items():
        bldg_bills = sampled_bills[sampled_bills["building"] == key]
        total_kwh = bldg_bills["total_kwh"].sum()
        total_cost = bldg_bills["total_cost"].sum()
        n_months = len(bldg_bills)
        print(f"  {key}: {n_months} months, {total_kwh:,.0f} kWh, ${total_cost:,.0f}")

    # ── Check for real data overlay ──
    real_data, avail = discover_data(cfg)
    real_count = sum(1 for v in avail.bills.values() if v)
    total = len(avail.bills)
    print(f"\n  Real campus data overlay: {real_count}/{total} buildings")
    if avail.weather:
        print("  Weather: REAL (NOAA ISD)")

    # ── Step 1: Economics ──
    fkw = base_friction_kwargs(cfg)
    rate = cfg["general"]["discount_rate"]
    life = cfg["general"]["analysis_life_years"]

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

        bldg = campus.buildings.get(pk)
        sampled_info = {}
        if bldg:
            sampled_info = {
                "sampled_building": bldg.source_building_name,
                "sampled_area_sqft": bldg.area_sqft,
                "sampled_annual_kwh": bldg.annual_kwh,
                "sampled_eui": bldg.site_eui_kbtu,
                "sampled_annual_cost": bldg.annual_cost_estimate,
            }

        rows.append({
            "project": pk,
            "npv_no_friction": npv_clean,
            "npv_with_friction": npv_friction,
            "npv_reduction_pct": (1 - npv_friction / npv_clean) * 100 if npv_clean != 0 else 0,
            "computed_payback": pb,
            "computed_irr": irr,
            "discounted_payback": dpb,
            "breakeven_benefit": be,
            **sampled_info,
        })
    replication = pd.DataFrame(rows)
    replication.to_csv(OUT / "sampled_step1_economics.csv", index=False)
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
    mc_stats.to_csv(OUT / "sampled_step2_mc_stats.csv", index=False)
    print(mc_stats[["project", "P10", "P50", "P90", "P_NPV_positive"]].to_string(index=False))

    # ── Step 3: Baseline ──
    section("Step 3: Baseline Model")
    if avail.weather and real_data.get("weather_temps") is not None:
        print("  Using REAL weather data (NOAA ISD)")
        temps = real_data["weather_temps"]
        baseline_data = generate_load_from_real_data(cfg, temps)
    else:
        print("  Using SYNTHETIC weather data")
        baseline_data = generate_synthetic_load(cfg)

    baseline_eval = evaluate_waste_recovery(baseline_data, cfg)
    baseline_eval["weather_source"] = "REAL" if avail.weather else "SYNTHETIC"
    baseline_eval.to_csv(OUT / "sampled_step3_baseline.csv", index=False)
    print(baseline_eval.to_string(index=False))

    # ── Step 4: Evidence ──
    section("Step 4: Evidence Generation")
    seed_val = cfg["general"]["random_seed"]

    bills = generate_utility_bills(cfg, seed_val)
    bill_validation = validate_benefits_against_bills(bills, cfg)
    mv_data = generate_mv_comparison(cfg, seed_val)
    calibrated_dist = calibrate_savings_distribution(mv_data)
    maint_records = generate_maintenance_records(cfg, seed_val)
    maint_analysis = analyze_maintenance_evidence(maint_records)
    interaction_eng = generate_interaction_analysis(cfg, seed_val)
    submeter = generate_submetered_data(cfg, seed_val)
    submeter_analysis = analyze_submetered_waste(submeter)

    bills.to_csv(OUT / "sampled_evidence_utility_bills.csv", index=False)
    bill_validation.to_csv(OUT / "sampled_evidence_bill_validation.csv", index=False)
    mv_data.to_csv(OUT / "sampled_evidence_mv_data.csv", index=False)
    maint_records.to_csv(OUT / "sampled_evidence_maintenance.csv", index=False)

    evidence = {
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

    risk_df = risk_tolerance_assessment(cfg, mc_stats)
    risk_df.to_csv(OUT / "sampled_evidence_risk.csv", index=False)

    cfg_v3 = calibrate_config_from_evidence(cfg, evidence)
    comparison = evidence_comparison_table(cfg, cfg_v3, evidence)
    comparison.to_csv(OUT / "sampled_evidence_comparison.csv", index=False)
    decisions = generate_decision_rules(risk_df, evidence)
    decisions.to_csv(OUT / "sampled_evidence_decisions.csv", index=False)

    print("\nBill validation:")
    print(bill_validation.to_string(index=False))
    print("\nDecisions:")
    print(decisions[["project", "decision", "evidence_quality"]].to_string(index=False))

    # ── Step 5: Scoring ──
    section("Step 5: Scoring & Rankings")
    ws_result = weight_stability_analysis(cfg)
    ws_result["summary"].to_csv(OUT / "sampled_step5_weight_stability.csv", index=False)
    norm_df = normalization_sensitivity(cfg)
    corr_result = correlation_double_counting(cfg)
    rank_df = rank_disagreement(cfg)
    rank_df.to_csv(OUT / "sampled_step5_rankings.csv", index=False)
    print(rank_df[["project", "score_rank", "pi_rank", "npv_rank"]].to_string(index=False))

    # ── Step 6: Interactions ──
    section("Step 6: Project Interactions")
    subset_df = enumerate_all_subsets(cfg)
    subset_df.to_csv(OUT / "sampled_step6_subsets.csv", index=False)
    seq_df = sequencing_analysis(cfg)
    seq_df.to_csv(OUT / "sampled_step6_sequencing.csv", index=False)
    print(subset_df.head(5)[["subset", "naive_npv", "adjusted_npv", "overstatement"]].to_string(index=False))

    # ── Step 7: Optimization ──
    section("Step 7: Budget Optimization")
    sweep_df = budget_sweep(cfg)
    sweep_df.to_csv(OUT / "sampled_step7_budget_sweep.csv", index=False)
    ef = efficient_frontier(sweep_df)
    my_result = multi_year_milp(cfg)
    print(f"Frontier flattens at budget = {format_currency(ef['flatten_budget'])}")

    # ── Step 8: Diagnostics ──
    section("Step 8: Diagnostics")
    diag_results = run_all_diagnostics(cfg)
    diag_report = format_diagnostic_report(diag_results, cfg)
    (OUT / "sampled_diagnostics_report.md").write_text(diag_report)

    gb_gap = diag_results["gradient_boosting"]["train_test_gap"]
    print(f"  GB overfit ratio: {gb_gap['overfit_ratio']:.3f} — {gb_gap['diagnosis']}")
    cp_diag = diag_results["changepoint_regression"]
    print(f"  CP lag-1 ACF: {cp_diag['lag1_autocorrelation']:.3f} — {cp_diag['diagnosis']}")

    # ── Provenance summary ──
    section("Data Provenance Summary")
    provenance_lines = [
        "# Data Provenance: Sampled Campus Mode",
        "",
        "## Building Profiles",
        "Source: Chicago Energy Benchmarking (city-mandated annual reporting)",
        f"Seed: {args.seed}",
        "",
    ]
    for key, bldg in campus.buildings.items():
        peer = get_peer_comparison(key, bldg)
        provenance_lines.append(
            f"- **{key}**: {bldg.source_building_name} (ID {bldg.source_building_id}), "
            f"{bldg.building_type}, {bldg.area_sqft:,.0f} sqft, "
            f"EUI={bldg.site_eui_kbtu:.1f} kBtu/sqft "
            f"({peer.get('percentile_rank', 0):.0f}th pctl)"
        )
    provenance_lines.extend([
        "",
        "## Economic Parameters",
        "Source: EIA Form 861, DOE ESPC FY2024, IEEE 493-2007",
        f"- Electricity rate: ${eia_rate:.4f}/kWh (EIA IL commercial 2020)",
        f"- Escalation: {cfg['frictions']['energy_escalation_rate']:.4%}/yr (EIA 10yr CAGR)",
        f"- M&V savings: {cfg['monte_carlo']['savings_triangular']} (DOE ESPC calibrated)",
        "",
        "## Weather",
        f"- {'REAL: NOAA ISD Chicago OHare 2024-2025' if avail.weather else 'SYNTHETIC'}",
        "",
        "## Evidence",
        "- Utility bills: SYNTHETIC (model-generated)",
        "- M&V data: SYNTHETIC",
        "- Maintenance: SYNTHETIC",
        "- Submeters: SYNTHETIC",
        "",
        "## What This Means",
        "Building energy profiles come from **real Chicago buildings** of the correct type.",
        "Economic parameters use **published government data** with citations.",
        "Weather uses **real NOAA observations** when available.",
        "Evidence packages are still synthetic — replace with real campus data when available.",
    ])
    provenance_text = "\n".join(provenance_lines)
    (OUT / "sampled_data_provenance.md").write_text(provenance_text)

    # ── Final summary ──
    banner("FINAL SUMMARY — SAMPLED CAMPUS MODE")

    print("\nSampled buildings:")
    for key, bldg in campus.buildings.items():
        print(f"  {key}: {bldg.source_building_name} ({bldg.building_type}, "
              f"{bldg.area_sqft:,.0f} sqft, EUI={bldg.site_eui_kbtu:.1f})")

    print(f"\nWeather: {'REAL (NOAA ISD)' if avail.weather else 'SYNTHETIC'}")
    print(f"Electricity rate: ${eia_rate:.4f}/kWh (EIA)")

    print("\nProject rankings:")
    print(rank_df[["project", "score_rank", "composite_score"]].to_string(index=False))

    print("\nDecision recommendations:")
    for _, r in decisions.iterrows():
        print(f"  {r['project']}: {r['decision']} ({r['evidence_quality']})")

    print(f"\nAll outputs written to {OUT}/")
    print("Files prefixed with 'sampled_' to distinguish from other runs.")
    print(f"\nTo re-run with a different campus sample: python3 run_sampled.py --seed {args.seed + 1}")


if __name__ == "__main__":
    main()
