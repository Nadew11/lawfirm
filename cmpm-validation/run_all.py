#!/usr/bin/env python3
"""CMPM Validation Harness — Run All Steps and generate report.

v2: frictions in base case, tiered scenarios, decomposed electrical benefit,
    widened MC, rebalanced scoring, expanded interactions, improved waste detection.
"""
from __future__ import annotations

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
from cmpm.economics import (
    base_friction_kwargs,
    breakeven_benefit,
    compute_discounted_payback,
    compute_irr,
    compute_npv,
    compute_simple_payback,
    friction_comparison,
    survival_table,
    tornado_analysis,
)
from cmpm.uncertainty import (
    correlation_impact,
    run_monte_carlo_all_projects,
)
from cmpm.interactions import (
    enumerate_all_subsets,
    sequencing_analysis,
)
from cmpm.optimize import (
    budget_sweep,
    efficient_frontier,
    multi_year_milp,
    shadow_prices,
)
from cmpm.scoring import (
    correlation_double_counting,
    normalization_sensitivity,
    rank_disagreement,
    weight_stability_analysis,
    weighted_score,
)
from cmpm.baseline import (
    evaluate_waste_recovery,
    generate_synthetic_load,
)
from cmpm.evidence import (
    calibrate_config_from_evidence,
    evidence_comparison_table,
    generate_all_evidence,
    generate_decision_rules,
    risk_tolerance_assessment,
)
from cmpm.utils import format_currency, format_pct

OUT = Path(__file__).resolve().parent / "outputs"


def ensure_output_dir() -> None:
    OUT.mkdir(exist_ok=True)


# v1 claimed values (the original illustrative numbers, no frictions)
CLAIMED_V1 = {
    "lab_ventilation":       {"npv": 633_000, "payback": 2.15, "irr": 0.45},
    "central_plant":         {"npv": 1_118_000, "payback": 3.64, "irr": 0.24},
    "classroom_bas":         {"npv": 241_000, "payback": 3.00, "irr": 0.31},
    "electrical_monitoring": {"npv": 809_000, "payback": 2.12, "irr": 0.46},
    "dorm_occupancy":        {"npv": 166_000, "payback": 4.00, "irr": 0.21},
}


# =========================================================================
# Step 1: Deterministic Replication
# =========================================================================

def step1_replication(cfg: dict) -> pd.DataFrame:
    """Step 1: compute NPV/IRR/payback with and without frictions."""
    rate = cfg["general"]["discount_rate"]
    life = cfg["general"]["analysis_life_years"]
    fkw = base_friction_kwargs(cfg)
    rows = []

    for pk in cfg["projects"]:
        p = cfg["projects"][pk]

        # No-friction NPV (for replication against v1 claims)
        npv_clean = compute_npv(p["capex"], p["annual_benefit"], rate, life, cross_check=False)
        irr = compute_irr(p["capex"], p["annual_benefit"], life)
        pb = compute_simple_payback(p["capex"], p["annual_benefit"])

        # With-friction NPV (v2 base case)
        npv_friction = compute_npv(
            p["capex"], p["annual_benefit"], rate, life, cross_check=False, **fkw
        ) if fkw else npv_clean
        dpb = compute_discounted_payback(p["capex"], p["annual_benefit"], rate, life, **fkw)
        be = breakeven_benefit(p["capex"], rate, life)

        claimed = CLAIMED_V1.get(pk, {})
        claimed_npv = claimed.get("npv", None)
        claimed_pb = claimed.get("payback", None)
        claimed_irr = claimed.get("irr", None)

        npv_pass = abs(npv_clean - claimed_npv) < 5000 if claimed_npv else None
        pb_pass = abs(pb - claimed_pb) < 0.02 if claimed_pb else None
        irr_pass = abs(irr - claimed_irr) < 0.015 if claimed_irr else None

        rows.append({
            "project": pk,
            "npv_no_friction": npv_clean,
            "claimed_npv": claimed_npv,
            "npv_PASS": npv_pass,
            "npv_with_friction": npv_friction,
            "npv_reduction_pct": (1 - npv_friction / npv_clean) * 100 if npv_clean != 0 else 0,
            "computed_payback": pb,
            "claimed_payback": claimed_pb,
            "payback_PASS": pb_pass,
            "computed_irr": irr,
            "claimed_irr": claimed_irr,
            "irr_PASS": irr_pass,
            "discounted_payback": dpb,
            "breakeven_benefit": be,
        })

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "step1_replication.csv", index=False)
    return df


# =========================================================================
# Step 2: Adversarial Sensitivity
# =========================================================================

def step2_sensitivity(cfg: dict) -> dict[str, pd.DataFrame]:
    rate = cfg["general"]["discount_rate"]
    life = cfg["general"]["analysis_life_years"]
    projects = cfg["projects"]
    sens_cfg = cfg["sensitivity"]

    # Tornado for each project
    tornado_dfs = {}
    for pk in projects:
        p = projects[pk]
        tr = sens_cfg["tornado_ranges"]
        tdf = tornado_analysis(
            p["capex"], p["annual_benefit"], rate, life,
            {
                "savings_pct": (tr["savings_pct"][0], tr["savings_pct"][1]),
                "capex_pct": (tr["capex_pct"][0], tr["capex_pct"][1]),
                "discount_rate": (tr["discount_rate"][0], tr["discount_rate"][1]),
                "life_years": (tr["life_years"][0], tr["life_years"][1]),
            },
        )
        tornado_dfs[pk] = tdf

    all_tornado = pd.concat(
        [df.assign(project=pk) for pk, df in tornado_dfs.items()],
        ignore_index=True,
    )
    all_tornado.to_csv(OUT / "step2_tornado.csv", index=False)

    # Tiered downside scenarios
    jd = sens_cfg["joint_downside"]
    surv = survival_table(projects, {"joint_downside": jd}, rate, life)
    surv.to_csv(OUT / "step2_survival.csv", index=False)

    # Friction comparison
    fric = friction_comparison(projects, rate, life, cfg["frictions"])
    fric.to_csv(OUT / "step2_frictions.csv", index=False)

    _plot_tornado(tornado_dfs.get("central_plant", tornado_dfs[list(tornado_dfs.keys())[0]]),
                  "Central Plant", OUT / "chart_tornado_central_plant.png")
    _plot_tornado(tornado_dfs.get("lab_ventilation", tornado_dfs[list(tornado_dfs.keys())[0]]),
                  "Lab Ventilation", OUT / "chart_tornado_lab_ventilation.png")

    return {"tornado": all_tornado, "survival": surv, "frictions": fric, "tornado_dfs": tornado_dfs}


def _plot_tornado(tdf: pd.DataFrame, title: str, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    tdf_sorted = tdf.sort_values("swing")
    y_pos = range(len(tdf_sorted))
    base_npv = tdf_sorted["npv_base"].iloc[0]
    lefts = tdf_sorted["npv_low"].values - base_npv
    rights = tdf_sorted["npv_high"].values - base_npv
    ax.barh(y_pos, rights - lefts, left=lefts, height=0.5, color="#4A90D9")
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(tdf_sorted["parameter"].values)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Change in NPV ($)")
    ax.set_title(f"Tornado: {title}")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# =========================================================================
# Step 3: Monte Carlo
# =========================================================================

def step3_monte_carlo(cfg: dict) -> dict[str, Any]:
    mc_results = run_monte_carlo_all_projects(cfg)

    rows = []
    for pk, res in mc_results.items():
        row = {"project": pk}
        row.update(res["stats"])
        rows.append(row)
    stats_df = pd.DataFrame(rows)
    stats_df.to_csv(OUT / "step3_mc_stats.csv", index=False)

    corr_imp = correlation_impact(cfg)
    corr_df = pd.DataFrame(corr_imp).T
    corr_df.to_csv(OUT / "step3_correlation_impact.csv")

    proj_keys = [pk for pk in cfg["projects"]]
    fig, axes = plt.subplots(1, len(proj_keys), figsize=(4 * len(proj_keys), 6), sharey=True)
    if len(proj_keys) == 1:
        axes = [axes]
    for i, pk in enumerate(proj_keys):
        npvs = mc_results[pk]["npvs"]
        ax = axes[i]
        ax.hist(npvs / 1000, bins=50, color="#4A90D9", alpha=0.7, edgecolor="white")
        stats = mc_results[pk]["stats"]
        for pctile, label in [(stats["P10"], "P10"), (stats["P50"], "P50"), (stats["P90"], "P90")]:
            ax.axvline(pctile / 1000, color="red", linestyle="--", linewidth=1)
            ax.text(pctile / 1000, ax.get_ylim()[1] * 0.95, label, fontsize=8, color="red")
        ax.set_xlabel("NPV ($k)")
        ax.set_title(pk.replace("_", " ").title(), fontsize=9)
    axes[0].set_ylabel("Frequency")
    fig.suptitle("Monte Carlo NPV Distributions (v2)", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "chart_mc_npv_distributions.png", dpi=150)
    plt.close(fig)

    if "electrical_full" in mc_results and "electrical_energy_only" in mc_results:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.hist(mc_results["electrical_full"]["npvs"] / 1000, bins=50, alpha=0.6,
                label="Full (energy + avoided failure)", color="#4A90D9")
        ax.hist(mc_results["electrical_energy_only"]["npvs"] / 1000, bins=50, alpha=0.6,
                label="Energy only ($45k/yr)", color="#E74C3C")
        ax.axvline(0, color="black", linewidth=1)
        ax.set_xlabel("NPV ($k)")
        ax.set_ylabel("Frequency")
        ax.set_title("Electrical Monitoring: Full vs Energy-Only (v2)")
        ax.legend()
        fig.tight_layout()
        fig.savefig(OUT / "chart_electrical_comparison.png", dpi=150)
        plt.close(fig)

    return {"stats": stats_df, "mc_results": mc_results, "correlation": corr_df}


# =========================================================================
# Step 4: Project Interactions
# =========================================================================

def step4_interactions(cfg: dict) -> dict[str, pd.DataFrame]:
    subset_df = enumerate_all_subsets(cfg)
    subset_df.to_csv(OUT / "step4_subsets.csv", index=False)
    seq_df = sequencing_analysis(cfg)
    seq_df.to_csv(OUT / "step4_sequencing.csv", index=False)
    return {"subsets": subset_df, "sequencing": seq_df}


# =========================================================================
# Step 5: Optimization
# =========================================================================

def step5_optimization(cfg: dict) -> dict[str, Any]:
    sweep_df = budget_sweep(cfg)
    sweep_df.to_csv(OUT / "step5_budget_sweep.csv", index=False)
    sp_df = shadow_prices(cfg, 2_000_000)
    sp_df.to_csv(OUT / "step5_shadow_prices.csv", index=False)
    my_result = multi_year_milp(cfg)
    ef = efficient_frontier(sweep_df)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(np.array(sweep_df["budget"]) / 1e6, np.array(sweep_df["optimal_npv"]) / 1e6,
            "b-o", label="Optimal (MILP)", markersize=4)
    ax.plot(np.array(sweep_df["budget"]) / 1e6, np.array(sweep_df["heuristic_npv"]) / 1e6,
            "r--s", label="Heuristic (top-k by score)", markersize=4)
    ax.axvline(ef["flatten_budget"] / 1e6, color="green", linestyle=":",
               label=f"Frontier flattens at ${ef['flatten_budget']/1e6:.1f}M")
    ax.set_xlabel("Budget ($M)")
    ax.set_ylabel("Portfolio NPV ($M)")
    ax.set_title("Budget vs NPV: Optimal vs Heuristic (v2)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "chart_budget_frontier.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(np.array(sweep_df["budget"]) / 1e6, np.array(sweep_df["gap"]) / 1e3,
           width=0.08, color="#E74C3C")
    ax.set_xlabel("Budget ($M)")
    ax.set_ylabel("NPV Gap ($k)")
    ax.set_title("Heuristic Gap (v2)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "chart_heuristic_gap.png", dpi=150)
    plt.close(fig)

    return {"sweep": sweep_df, "shadow_prices": sp_df, "multi_year": my_result, "frontier": ef}


# =========================================================================
# Step 6: Scoring Validity
# =========================================================================

def step6_scoring(cfg: dict) -> dict[str, Any]:
    ws_result = weight_stability_analysis(cfg)
    ws_result["summary"].to_csv(OUT / "step6_weight_stability.csv", index=False)
    ws_result["rank_distribution"].to_csv(OUT / "step6_rank_distribution.csv")
    norm_df = normalization_sensitivity(cfg)
    norm_df.to_csv(OUT / "step6_normalization.csv", index=False)
    corr_result = correlation_double_counting(cfg)
    corr_result["vif_summary"].to_csv(OUT / "step6_vif.csv", index=False)
    corr_result["correlation_matrix"].to_csv(OUT / "step6_correlation_matrix.csv")
    rank_df = rank_disagreement(cfg)
    rank_df.to_csv(OUT / "step6_rank_disagreement.csv", index=False)

    rd = ws_result["rank_distribution"]
    fig, ax = plt.subplots(figsize=(8, 5))
    im = ax.imshow(rd.values, cmap="YlOrRd", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(rd.shape[1]))
    ax.set_xticklabels(rd.columns, fontsize=8)
    ax.set_yticks(range(rd.shape[0]))
    ax.set_yticklabels([n.replace("_", " ").title() for n in rd.index], fontsize=8)
    for i in range(rd.shape[0]):
        for j in range(rd.shape[1]):
            ax.text(j, i, f"{rd.values[i,j]:.2f}", ha="center", va="center", fontsize=8)
    ax.set_title("Rank Distribution Under Weight Perturbation (v2)")
    ax.set_xlabel("Rank")
    fig.colorbar(im, ax=ax, label="Probability")
    fig.tight_layout()
    fig.savefig(OUT / "chart_rank_heatmap.png", dpi=150)
    plt.close(fig)

    return {"weight_stability": ws_result, "normalization": norm_df,
            "correlation": corr_result, "rank_disagreement": rank_df}


# =========================================================================
# Step 7: Baseline Sanity Check
# =========================================================================

def step7_baseline(cfg: dict) -> pd.DataFrame:
    data = generate_synthetic_load(cfg)
    eval_df = evaluate_waste_recovery(data, cfg)
    eval_df.to_csv(OUT / "step7_SYNTHETIC_waste_recovery.csv", index=False)
    return eval_df


# =========================================================================
# Evidence Generation & Calibration
# =========================================================================

def step_evidence(cfg: dict, mc_stats: pd.DataFrame) -> dict[str, Any]:
    """Generate all evidence packages, calibrate v3 config, run risk assessment."""
    evidence = generate_all_evidence(cfg)

    evidence["utility_bills"].to_csv(OUT / "evidence_utility_bills.csv", index=False)
    evidence["bill_validation"].to_csv(OUT / "evidence_bill_validation.csv", index=False)
    evidence["mv_data"].to_csv(OUT / "evidence_mv_data.csv", index=False)
    evidence["maintenance_records"].to_csv(OUT / "evidence_maintenance_records.csv", index=False)
    evidence["interaction_engineering"].to_csv(OUT / "evidence_interaction_analysis.csv", index=False)

    submeter_summary = evidence["submetered_data"].describe()
    submeter_summary.to_csv(OUT / "evidence_submeter_summary.csv")

    risk_df = risk_tolerance_assessment(cfg, mc_stats)
    risk_df.to_csv(OUT / "evidence_risk_tolerance.csv", index=False)

    cfg_v3 = calibrate_config_from_evidence(cfg, evidence)
    comparison = evidence_comparison_table(cfg, cfg_v3, evidence)
    comparison.to_csv(OUT / "evidence_v2_v3_comparison.csv", index=False)

    decisions = generate_decision_rules(risk_df, evidence)
    decisions.to_csv(OUT / "evidence_decision_rules.csv", index=False)

    return {
        "evidence": evidence,
        "risk": risk_df,
        "cfg_v3": cfg_v3,
        "comparison": comparison,
        "decisions": decisions,
    }


# =========================================================================
# Step 8: Report
# =========================================================================

def generate_report(
    cfg: dict,
    replication: pd.DataFrame,
    sensitivity: dict,
    mc: dict,
    interactions: dict,
    optimization: dict,
    scoring: dict,
    baseline_eval: pd.DataFrame,
    evidence_result: dict[str, Any] | None = None,
) -> str:
    lines: list[str] = []
    lines.append("# CMPM Validation Harness — Report (v2: Accuracy Improvements)\n")
    lines.append("**Generated by automated adversarial testing pipeline.**\n")
    lines.append("v2 changes: frictions in base case, decomposed electrical benefit, "
                 "widened MC distributions, tiered scenarios, rebalanced scoring, "
                 "expanded interactions, improved waste detection.\n")

    # Section 1: Replication table
    lines.append("\n## 1. Replication & Friction Impact\n")
    lines.append("| Project | No-Friction NPV | With-Friction NPV | Reduction | Payback | IRR |")
    lines.append("|---------|----------------|-------------------|-----------|---------|-----|")
    for _, row in replication.iterrows():
        lines.append(
            f"| {row['project']} | {format_currency(row['npv_no_friction'])} "
            f"| {format_currency(row['npv_with_friction'])} "
            f"| {row['npv_reduction_pct']:.1f}% "
            f"| {row['computed_payback']:.2f} "
            f"| {format_pct(row['computed_irr'])} |"
        )

    # Section 2: Findings ranked by severity
    lines.append("\n## 2. Findings Ranked by Severity\n")
    findings = []

    # Tiered scenario results
    surv = sensitivity["survival"]
    for scenario_name in surv["scenario"].unique():
        if scenario_name == "base":
            continue
        dead = surv[(surv["scenario"] == scenario_name) & (surv["npv"] < 0)]
        alive = surv[(surv["scenario"] == scenario_name) & (surv["npv"] > 0)]
        if len(dead) > 0:
            dead_list = ", ".join(dead["project"].tolist())
            severity = "CRITICAL" if "severe" in scenario_name else "HIGH" if "moderate" in scenario_name else "MEDIUM"
            prio = 1 if severity == "CRITICAL" else 2 if severity == "HIGH" else 3
            findings.append((prio, severity, f"[{scenario_name}] Projects with NPV < 0: {dead_list}"))
        if len(alive) > 0:
            alive_list = ", ".join(alive["project"].tolist())
            findings.append((4, "INFO", f"[{scenario_name}] Survivors: {alive_list}"))

    # Friction impact
    fkw = base_friction_kwargs(cfg)
    if fkw:
        worst_reduction = replication["npv_reduction_pct"].max()
        findings.append((2, "HIGH", f"Base-case frictions (decay {fkw.get('savings_decay_rate',0):.0%}, "
                         f"O&M {fkw.get('om_cost_annual_pct',0):.1%}, escalation {fkw.get('escalation_rate',0):.0%}) "
                         f"reduce NPVs by up to {worst_reduction:.1f}%."))

    # Electrical project
    mc_stats = mc["stats"]
    if "electrical_energy_only" in mc_stats["project"].values:
        ee_row = mc_stats[mc_stats["project"] == "electrical_energy_only"].iloc[0]
        findings.append((1, "CRITICAL",
                         f"Electrical monitoring energy-only: P(NPV>0) = {ee_row['P_NPV_positive']:.1%}. "
                         f"v2 decomposed benefit ($92.5k = $45k energy + $32.5k maintenance + $15k avoided-failure)."))

    # Interaction overstatement
    subset_df = interactions["subsets"]
    full_portfolio = subset_df[subset_df["size"] == subset_df["size"].max()].iloc[0]
    if full_portfolio["overstatement"] > 50_000:
        findings.append((2, "HIGH",
                         f"Full portfolio naive NPV overstates by {format_currency(full_portfolio['overstatement'])} "
                         f"({full_portfolio['overstatement_pct']:.1f}%) due to interactions."))

    # Score vs MILP disagreement
    rank_df = scoring["rank_disagreement"]
    tau_score_pi = rank_df.attrs.get("tau_score_vs_pi", 0)
    findings.append((2 if abs(tau_score_pi) < 0.5 else 3, "HIGH" if abs(tau_score_pi) < 0.5 else "MEDIUM",
                     f"Score vs profitability index: Kendall tau = {tau_score_pi:.2f} "
                     f"(v2 rebalanced weights)."))

    # Heuristic gap
    sweep = optimization["sweep"]
    max_gap = sweep["gap"].max()
    if max_gap > 50_000:
        findings.append((2, "HIGH",
                         f"Max NPV left on table by heuristic: {format_currency(max_gap)}."))

    # Weight stability
    ws = scoring["weight_stability"]
    low_p_top2 = ws["summary"][ws["summary"]["P_top2"] < 0.5]
    if len(low_p_top2) > 0:
        unstable = ", ".join(low_p_top2["project"].tolist())
        findings.append((3, "MEDIUM", f"Unstable top-2 ranking under weight perturbation: {unstable}"))

    # Correlation double-counting
    vif_df = scoring["correlation"]["vif_summary"]
    high_vif = vif_df[vif_df["VIF"] > 1.5]
    if len(high_vif) > 0:
        inflated = ", ".join(f"{r['criterion']} (VIF={r['VIF']:.2f})" for _, r in high_vif.iterrows())
        findings.append((3, "MEDIUM", f"Weight double-counting: {inflated}"))

    # Baseline waste recovery
    cp_row = baseline_eval[baseline_eval["model"] == "change_point_regression"].iloc[0]
    gb_row = baseline_eval[baseline_eval["model"] == "gradient_boosting"].iloc[0]
    detect_status = "both detect" if (cp_row["detects_waste"] and gb_row["detects_waste"]) else \
                    "CP detects, GB misses" if cp_row["detects_waste"] else \
                    "GB detects, CP misses" if gb_row["detects_waste"] else "both miss"
    findings.append((3 if "detect" in detect_status else 2, "MEDIUM" if "detect" in detect_status else "HIGH",
                     f"Waste detection (v2: shoulder feature + lower noise): "
                     f"CP estimated {cp_row['estimated_waste_pct']:.1%}, "
                     f"GB estimated {gb_row['estimated_waste_pct']:.1%}. "
                     f"True = {cp_row['true_waste_pct']:.1%}. Status: {detect_status}."))

    findings.sort(key=lambda x: x[0])
    for _, severity, desc in findings:
        lines.append(f"- **[{severity}]** {desc}")

    # Section 3: Survival assessment (tiered)
    lines.append("\n## 3. Claims That Survive Adversarial Testing\n")
    scenario_names = [s for s in surv["scenario"].unique() if s != "base"]
    header = "| Project | " + " | ".join(scenario_names) + " | MC P(NPV>0) |"
    sep = "|---------|" + "|".join(["------" for _ in scenario_names]) + "|------|"
    lines.append(header)
    lines.append(sep)
    for pk in cfg["projects"]:
        cells = [pk]
        for sn in scenario_names:
            row_data = surv[(surv["project"] == pk) & (surv["scenario"] == sn)]
            if len(row_data) > 0:
                npv = row_data["npv"].iloc[0]
                cells.append(f"{'**FAIL**' if npv < 0 else 'PASS'} ({format_currency(npv)})")
            else:
                cells.append("N/A")
        mc_proj = mc_stats[mc_stats["project"] == pk]
        p_pos = f"{mc_proj['P_NPV_positive'].iloc[0]:.1%}" if len(mc_proj) > 0 else "N/A"
        cells.append(p_pos)
        lines.append("| " + " | ".join(cells) + " |")

    # Section 3b: Evidence Packages
    if evidence_result is not None:
        lines.append("\n## 3b. Evidence Packages (SYNTHETIC)\n")
        lines.append("All data in this section is fabricated for demonstration. "
                     "Replace with actual campus data before real decisions.\n")

        ev = evidence_result["evidence"]

        # Utility bill validation
        lines.append("### Utility Bill Cross-Check\n")
        bill_val = ev["bill_validation"]
        lines.append("| Project | Claimed Benefit | Bill-Derived | Ratio | Flag |")
        lines.append("|---------|----------------|-------------|-------|------|")
        for _, r in bill_val.iterrows():
            lines.append(f"| {r['project']} | {format_currency(r['claimed_annual_benefit'])} "
                         f"| {format_currency(r['bill_derived_savings'])} "
                         f"| {r['ratio_claimed_to_derived']:.2f} | {r['flag']} |")

        # M&V calibration
        cal = ev["calibrated_distribution"]
        lines.append(f"\n### M&V Calibration (n={cal['n_projects']} peer projects)\n")
        lines.append(f"- Actual/predicted ratio: median = {cal['mode']:.3f}, "
                     f"mean = {cal['mean']:.3f}, std = {cal['std']:.3f}")
        lines.append(f"- Calibrated MC savings triangular: "
                     f"[{cal['low']:.3f}, {cal['mode']:.3f}, {cal['high']:.3f}]")
        lines.append(f"- v2 used: {cfg['monte_carlo']['savings_triangular']}\n")

        # Maintenance evidence
        maint = ev["maintenance_analysis"]
        lines.append("### Maintenance Record Analysis (10 years)\n")
        lines.append(f"- Annual routine cost: {format_currency(maint['annual_routine_cost'])}")
        lines.append(f"- Failures: {maint['total_failures']} in {maint['years_of_data']} years "
                     f"(rate = {maint['failure_rate_per_year']:.2f}/yr)")
        lines.append(f"- Avg failure cost: {format_currency(maint['avg_failure_cost'])}")
        lines.append(f"- Evidence-based benefit: {format_currency(maint['total_evidence_based_benefit'])} "
                     f"(vs config claim: {format_currency(maint['config_claimed_nonenergy_benefit'])} non-energy)\n")

        # Submetered waste detection
        sub = ev["submeter_analysis"]
        lines.append("### Submetered Waste Detection (Gold Standard)\n")
        lines.append(f"- Simultaneous H+C hours: {sub['simultaneous_hours']} / {sub['total_hours']} "
                     f"({sub['simultaneous_pct']:.1f}%)")
        lines.append(f"- Waste energy: {format_currency(sub['wasted_energy_kwh'])} kWh "
                     f"({sub['waste_fraction']:.1%} of total)")
        lines.append(f"- No model required — direct observation from submeters")
        lines.append(f"- Comparison: whole-building model estimated "
                     f"{baseline_eval[baseline_eval['model'] == 'change_point_regression']['estimated_waste_pct'].iloc[0]:.1%} "
                     f"vs submeter measured {sub['waste_fraction']:.1%}\n")

        # Risk tolerance
        risk = evidence_result["risk"]
        lines.append("### Risk Tolerance Assessment\n")
        lines.append("| Project | ES10 | P(NPV>0) | Loss | Prob | Recommendation |")
        lines.append("|---------|------|----------|------|------|----------------|")
        for _, r in risk.iterrows():
            lines.append(f"| {r['project']} | {format_currency(r['expected_shortfall_10'])} "
                         f"| {r['P_NPV_positive']:.1%} "
                         f"| {'PASS' if r['passes_loss_test'] else 'FAIL'} "
                         f"| {'PASS' if r['passes_probability_test'] else 'FAIL'} "
                         f"| **{r['recommendation']}** |")

        # v2 vs v3 comparison
        comp = evidence_result["comparison"]
        lines.append("\n### v2 vs v3 (Evidence-Calibrated) Comparison\n")
        lines.append("| Parameter | v2 Value | v3 (Evidence) | Source |")
        lines.append("|-----------|----------|--------------|--------|")
        for _, r in comp.iterrows():
            lines.append(f"| {r['parameter']} | {r['v2_value']} | {r['v3_evidence_value']} | {r['source']} |")

        # Decision rules
        decisions = evidence_result.get("decisions")
        if decisions is not None and len(decisions) > 0:
            lines.append("\n### Decision Rules\n")
            lines.append("| Project | Decision | Conditions | Evidence Gaps | Evidence Quality |")
            lines.append("|---------|----------|-----------|---------------|-----------------|")
            for _, r in decisions.iterrows():
                lines.append(f"| {r['project']} | **{r['decision']}** "
                             f"| {r['conditions']} | {r['evidence_gaps']} "
                             f"| {r['evidence_quality']} |")

    # Section 4: Config dump
    lines.append("\n## 4. Configuration (config.yaml v2)\n")
    lines.append("```yaml")
    with open(Path(__file__).resolve().parent / "config.yaml") as f:
        lines.append(f.read())
    lines.append("```\n")

    # Section 5: Skeptical judge Q&A
    lines.append("\n## 5. What a Skeptical Judge Would Ask\n")
    rate = cfg["general"]["discount_rate"]
    life = cfg["general"]["analysis_life_years"]

    questions = [
        ("How much do frictions reduce the NPVs?",
         lambda: "; ".join(f"{r['project']}: {r['npv_reduction_pct']:.1f}% reduction"
                           for _, r in replication.iterrows()) + "."),
        ("How sensitive is the ranking to the discount rate?",
         lambda: _discount_sensitivity_answer(cfg)),
        ("What if savings are 30% lower than projected?",
         lambda: _savings_30_answer(cfg)),
        ("Are the savings estimates additive?",
         lambda: f"No. Interaction effects reduce full-portfolio NPV by "
                 f"{format_currency(full_portfolio['overstatement'])} ({full_portfolio['overstatement_pct']:.1f}%)."),
        ("What is the probability each project has positive NPV?",
         lambda: _mc_prob_answer(mc_stats)),
        ("Does the scoring system agree with economic analysis?",
         lambda: f"Kendall tau (score vs PI) = {tau_score_pi:.2f} (v2 rebalanced from 0.00)."),
        ("Can we detect the kind of waste this model targets?",
         lambda: f"v2 with shoulder feature: CP estimated {cp_row['estimated_waste_pct']:.1%}, "
                 f"GB estimated {gb_row['estimated_waste_pct']:.1%} vs true {cp_row['true_waste_pct']:.1%}."),
        ("What is the worst-case 10% NPV for each project?",
         lambda: _es_answer(mc_stats)),
    ]

    for q, a_fn in questions:
        lines.append(f"**Q: {q}**\n")
        lines.append(f"A: {a_fn()}\n")

    lines.append("\n## Charts\n")
    for png in sorted(OUT.glob("chart_*.png")):
        lines.append(f"![{png.stem}]({png.name})\n")

    report_text = "\n".join(lines)
    (OUT / "report.md").write_text(report_text)
    return report_text


def _discount_sensitivity_answer(cfg: dict) -> str:
    projects = cfg["projects"]
    life = cfg["general"]["analysis_life_years"]
    parts = []
    for pk in projects:
        p = projects[pk]
        npv_4 = compute_npv(p["capex"], p["annual_benefit"], 0.04, life, cross_check=False)
        npv_12 = compute_npv(p["capex"], p["annual_benefit"], 0.12, life, cross_check=False)
        parts.append(f"{pk}: {format_currency(npv_12)} (12%) to {format_currency(npv_4)} (4%)")
    return "; ".join(parts) + "."


def _savings_30_answer(cfg: dict) -> str:
    projects = cfg["projects"]
    rate = cfg["general"]["discount_rate"]
    life = cfg["general"]["analysis_life_years"]
    fkw = base_friction_kwargs(cfg)
    parts = []
    for pk in projects:
        p = projects[pk]
        npv = compute_npv(p["capex"], p["annual_benefit"] * 0.70, rate, life, cross_check=False, **fkw)
        parts.append(f"{pk}: {format_currency(npv)}")
    return "; ".join(parts) + "."


def _mc_prob_answer(mc_stats: pd.DataFrame) -> str:
    parts = []
    for _, row in mc_stats.iterrows():
        if not row["project"].startswith("electrical_"):
            parts.append(f"{row['project']}: P(NPV>0) = {row['P_NPV_positive']:.1%}")
        elif row["project"] in ("electrical_monitoring", "electrical_full", "electrical_energy_only"):
            parts.append(f"{row['project']}: P(NPV>0) = {row['P_NPV_positive']:.1%}")
    return "; ".join(parts) + "."


def _es_answer(mc_stats: pd.DataFrame) -> str:
    parts = []
    for _, row in mc_stats.iterrows():
        if row["project"] in CLAIMED_V1 or row["project"] == "electrical_monitoring":
            parts.append(f"{row['project']}: ES10 = {format_currency(row['expected_shortfall_10'])}")
    return "; ".join(parts) + "."


# =========================================================================
# Main
# =========================================================================

def main() -> None:
    ensure_output_dir()
    cfg = load_config()
    fkw = base_friction_kwargs(cfg)

    print("=" * 70)
    print("CMPM VALIDATION HARNESS (v2: ACCURACY IMPROVEMENTS)")
    print("=" * 70)
    if fkw:
        print(f"Base-case frictions ON: {fkw}")

    print("\n--- Step 1: Deterministic Replication ---")
    replication = step1_replication(cfg)
    print(replication[["project", "npv_no_friction", "npv_with_friction",
                       "npv_reduction_pct", "computed_irr"]].to_string(index=False))

    print("\n--- Step 2: Adversarial Sensitivity (tiered scenarios) ---")
    sensitivity = step2_sensitivity(cfg)
    surv = sensitivity["survival"]
    non_base = surv[surv["scenario"] != "base"][["project", "scenario", "npv", "sign_flip"]]
    print(non_base.to_string(index=False))

    print("\n--- Step 3: Monte Carlo ---")
    mc = step3_monte_carlo(cfg)
    print(mc["stats"][["project", "P10", "P50", "P90", "P_NPV_positive"]].to_string(index=False))

    print("\n--- Step 4: Project Interactions ---")
    interact = step4_interactions(cfg)
    top_subsets = interact["subsets"].head(5)
    print(top_subsets[["subset", "naive_npv", "adjusted_npv", "overstatement"]].to_string(index=False))

    print("\n--- Step 5: Optimization ---")
    opt = step5_optimization(cfg)
    print(f"Frontier flattens at budget = {format_currency(opt['frontier']['flatten_budget'])}")
    print("Multi-year result:", opt["multi_year"]["selected"])

    print("\n--- Step 6: Scoring Validity ---")
    scr = step6_scoring(cfg)
    rd = scr["rank_disagreement"]
    print(rd[["project", "score_rank", "pi_rank", "npv_rank"]].to_string(index=False))
    print(f"Kendall tau (score vs PI): {rd.attrs.get('tau_score_vs_pi', 'N/A'):.2f}")

    print("\n--- Step 7: Baseline Sanity Check (SYNTHETIC) ---")
    baseline_eval = step7_baseline(cfg)
    print(baseline_eval.to_string(index=False))

    print("\n--- Evidence Generation & Calibration ---")
    mc_stats = mc["stats"]
    evidence_result = step_evidence(cfg, mc_stats)
    ev = evidence_result["evidence"]
    print(f"  Utility bills: {len(ev['utility_bills'])} rows")
    print(f"  M&V peers: {len(ev['mv_data'])} projects")
    cal = ev["calibrated_distribution"]
    print(f"  Calibrated MC savings: [{cal['low']:.3f}, {cal['mode']:.3f}, {cal['high']:.3f}]")
    maint = ev["maintenance_analysis"]
    print(f"  Maintenance evidence benefit: {format_currency(maint['total_evidence_based_benefit'])}")
    sub = ev["submeter_analysis"]
    print(f"  Submeter waste: {sub['waste_fraction']:.1%} ({sub['simultaneous_hours']} hours)")
    print(f"  Risk assessment:")
    print(evidence_result["risk"][["project", "recommendation"]].to_string(index=False))
    print(f"\n  v2 vs v3 comparison:")
    print(evidence_result["comparison"].to_string(index=False))
    print(f"\n  Decision rules:")
    print(evidence_result["decisions"].to_string(index=False))

    print("\n--- Step 8: Generating Report ---")
    report = generate_report(cfg, replication, sensitivity, mc, interact, opt, scr, baseline_eval,
                             evidence_result=evidence_result)
    print(f"Report written to {OUT / 'report.md'}")

    # ---- V1 vs V2 comparison summary ----
    print("\n" + "=" * 70)
    print("V1 -> V2 COMPARISON SUMMARY")
    print("=" * 70)

    for pk in cfg["projects"]:
        row = replication[replication["project"] == pk].iloc[0]
        v1_npv = row["npv_no_friction"]
        v2_npv = row["npv_with_friction"]
        print(f"  {pk}: NPV {format_currency(v1_npv)} -> {format_currency(v2_npv)} "
              f"({row['npv_reduction_pct']:.1f}% reduction)")

    # Count scenario failures
    for scenario_name in surv["scenario"].unique():
        if scenario_name == "base":
            continue
        dead = surv[(surv["scenario"] == scenario_name) & (surv["npv"] < 0)]
        print(f"  {scenario_name}: {len(dead)} projects fail")

    mc_stats = mc["stats"]
    risky = mc_stats[mc_stats["project"].isin(cfg["projects"]) & (mc_stats["P_NPV_positive"] < 0.90)]
    print(f"  MC projects with P(NPV>0) < 90%: {len(risky)}")

    tau = rd.attrs.get("tau_score_vs_pi", 0)
    print(f"  Score vs PI Kendall tau: {tau:.2f} (v1 was 0.00)")

    for _, row in baseline_eval.iterrows():
        print(f"  {row['model']}: waste estimate = {row['estimated_waste_pct']:.1%} "
              f"(v1: {'1.1%' if 'change' in row['model'] else '0.1%'})")

    print("\n" + "=" * 70)
    print("EVIDENCE STATUS")
    print("=" * 70)
    print("1. Utility bills: SYNTHETIC — replace with actual campus utility data.")
    print("2. M&V data: SYNTHETIC — replace with real completed project outcomes.")
    print("3. Maintenance records: SYNTHETIC — replace with actual CMMS export.")
    print("4. Interaction analysis: SYNTHETIC — replace with calibrated energy model results.")
    print("5. Submetered data: SYNTHETIC — install submeters for direct waste measurement.")
    print("6. Risk tolerance thresholds: ARBITRARY — board/finance must set real thresholds.")
    print("7. Decision rules derived from evidence, but thresholds need institutional calibration.")


if __name__ == "__main__":
    main()
