#!/usr/bin/env python3
"""CMPM Validation Harness — Run All Steps and generate report.

Runs Steps 1-7 in sequence, writes CSV tables and PNG charts to outputs/,
then generates outputs/report.md.
"""
from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cmpm.config_loader import load_config, get_project_list
from cmpm.economics import (
    breakeven_benefit,
    compute_discounted_payback,
    compute_irr,
    compute_npv,
    compute_simple_payback,
    friction_comparison,
    joint_downside_npv,
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
    milp_optimize,
    multi_year_milp,
    shadow_prices,
)
from cmpm.scoring import (
    correlation_double_counting,
    normalization_sensitivity,
    rank_disagreement,
    reverse_engineer_subscores,
    weight_stability_analysis,
    weighted_score,
)
from cmpm.baseline import (
    evaluate_waste_recovery,
    generate_synthetic_load,
)
from cmpm.utils import format_currency, format_pct


OUT = Path(__file__).resolve().parent / "outputs"


def ensure_output_dir() -> None:
    OUT.mkdir(exist_ok=True)


# =========================================================================
# Step 1: Deterministic Replication
# =========================================================================
CLAIMED = {
    "lab_ventilation":       {"npv": 633_000, "payback": 2.15, "irr": 0.45},
    "central_plant":         {"npv": 1_118_000, "payback": 3.64, "irr": 0.24},
    "classroom_bas":         {"npv": 241_000, "payback": 3.00, "irr": 0.31},
    "electrical_monitoring": {"npv": 809_000, "payback": 2.12, "irr": 0.46},
    "dorm_occupancy":        {"npv": 166_000, "payback": 4.00, "irr": 0.21},
}


def step1_replication(cfg: dict) -> pd.DataFrame:
    """Step 1: compute NPV/IRR/payback and compare to claimed values."""
    rate = cfg["general"]["discount_rate"]
    life = cfg["general"]["analysis_life_years"]
    rows = []
    for pk, claimed in CLAIMED.items():
        p = cfg["projects"][pk]
        npv = compute_npv(p["capex"], p["annual_benefit"], rate, life)
        irr = compute_irr(p["capex"], p["annual_benefit"], life)
        pb = compute_simple_payback(p["capex"], p["annual_benefit"])
        dpb = compute_discounted_payback(p["capex"], p["annual_benefit"], rate, life)
        be = breakeven_benefit(p["capex"], rate, life)

        npv_pass = abs(npv - claimed["npv"]) < 5000
        pb_pass = abs(pb - claimed["payback"]) < 0.02
        irr_pass = abs(irr - claimed["irr"]) < 0.015

        rows.append({
            "project": pk,
            "computed_npv": npv,
            "claimed_npv": claimed["npv"],
            "npv_delta": npv - claimed["npv"],
            "npv_PASS": npv_pass,
            "computed_payback": pb,
            "claimed_payback": claimed["payback"],
            "payback_PASS": pb_pass,
            "computed_irr": irr,
            "claimed_irr": claimed["irr"],
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
    """Step 2: tornado, joint downside, survival table, frictions."""
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

    # Joint downside
    jd = sens_cfg["joint_downside"]
    scenarios = {"joint_downside": jd}
    surv = survival_table(projects, scenarios, rate, life)
    surv.to_csv(OUT / "step2_survival.csv", index=False)

    # Friction comparison
    fric = friction_comparison(projects, rate, life, cfg["frictions"])
    fric.to_csv(OUT / "step2_frictions.csv", index=False)

    # Tornado chart for the largest-capex project (central plant)
    _plot_tornado(tornado_dfs["central_plant"], "Central Plant", OUT / "chart_tornado_central_plant.png")
    _plot_tornado(tornado_dfs["lab_ventilation"], "Lab Ventilation", OUT / "chart_tornado_lab_ventilation.png")

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
    """Step 3: run MC, produce stats and charts."""
    mc_results = run_monte_carlo_all_projects(cfg)

    rows = []
    for pk, res in mc_results.items():
        row = {"project": pk}
        row.update(res["stats"])
        rows.append(row)
    stats_df = pd.DataFrame(rows)
    stats_df.to_csv(OUT / "step3_mc_stats.csv", index=False)

    # Correlation impact
    corr_imp = correlation_impact(cfg)
    corr_df = pd.DataFrame(corr_imp).T
    corr_df.to_csv(OUT / "step3_correlation_impact.csv")

    # NPV distribution chart (violin-style histograms)
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
    fig.suptitle("Monte Carlo NPV Distributions", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "chart_mc_npv_distributions.png", dpi=150)
    plt.close(fig)

    # Electrical version comparison
    if "electrical_full" in mc_results and "electrical_energy_only" in mc_results:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.hist(mc_results["electrical_full"]["npvs"] / 1000, bins=50, alpha=0.6,
                label="Full (energy + avoided failure)", color="#4A90D9")
        ax.hist(mc_results["electrical_energy_only"]["npvs"] / 1000, bins=50, alpha=0.6,
                label="Energy only ($45k/yr)", color="#E74C3C")
        ax.axvline(0, color="black", linewidth=1)
        ax.set_xlabel("NPV ($k)")
        ax.set_ylabel("Frequency")
        ax.set_title("Electrical Monitoring: Full vs Energy-Only")
        ax.legend()
        fig.tight_layout()
        fig.savefig(OUT / "chart_electrical_comparison.png", dpi=150)
        plt.close(fig)

    return {"stats": stats_df, "mc_results": mc_results, "correlation": corr_df}


# =========================================================================
# Step 4: Project Interactions
# =========================================================================

def step4_interactions(cfg: dict) -> dict[str, pd.DataFrame]:
    """Step 4: subset enumeration, sequencing analysis."""
    subset_df = enumerate_all_subsets(cfg)
    subset_df.to_csv(OUT / "step4_subsets.csv", index=False)

    seq_df = sequencing_analysis(cfg)
    seq_df.to_csv(OUT / "step4_sequencing.csv", index=False)

    return {"subsets": subset_df, "sequencing": seq_df}


# =========================================================================
# Step 5: Optimization
# =========================================================================

def step5_optimization(cfg: dict) -> dict[str, Any]:
    """Step 5: budget sweep, shadow prices, multi-year, frontier."""
    sweep_df = budget_sweep(cfg)
    sweep_df.to_csv(OUT / "step5_budget_sweep.csv", index=False)

    sp_df = shadow_prices(cfg, 2_000_000)
    sp_df.to_csv(OUT / "step5_shadow_prices.csv", index=False)

    my_result = multi_year_milp(cfg)

    ef = efficient_frontier(sweep_df)

    # Budget-vs-NPV frontier chart
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(np.array(sweep_df["budget"]) / 1e6, np.array(sweep_df["optimal_npv"]) / 1e6,
            "b-o", label="Optimal (MILP)", markersize=4)
    ax.plot(np.array(sweep_df["budget"]) / 1e6, np.array(sweep_df["heuristic_npv"]) / 1e6,
            "r--s", label="Heuristic (top-k by score)", markersize=4)
    ax.axvline(ef["flatten_budget"] / 1e6, color="green", linestyle=":", label=f"Frontier flattens at ${ef['flatten_budget']/1e6:.1f}M")
    ax.set_xlabel("Budget ($M)")
    ax.set_ylabel("Portfolio NPV ($M)")
    ax.set_title("Budget vs NPV: Optimal vs Heuristic")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "chart_budget_frontier.png", dpi=150)
    plt.close(fig)

    # Gap chart
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(np.array(sweep_df["budget"]) / 1e6, np.array(sweep_df["gap"]) / 1e3, width=0.08, color="#E74C3C")
    ax.set_xlabel("Budget ($M)")
    ax.set_ylabel("NPV Gap ($k)")
    ax.set_title("Heuristic Gap: NPV Left on Table by Score-Based Selection")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "chart_heuristic_gap.png", dpi=150)
    plt.close(fig)

    return {
        "sweep": sweep_df, "shadow_prices": sp_df,
        "multi_year": my_result, "frontier": ef,
    }


# =========================================================================
# Step 6: Scoring Validity
# =========================================================================

def step6_scoring(cfg: dict) -> dict[str, Any]:
    """Step 6: weight stability, normalization, correlation, rank disagreement."""
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

    # Rank distribution heatmap
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
    ax.set_title("Rank Distribution Under Weight Perturbation")
    ax.set_xlabel("Rank")
    fig.colorbar(im, ax=ax, label="Probability")
    fig.tight_layout()
    fig.savefig(OUT / "chart_rank_heatmap.png", dpi=150)
    plt.close(fig)

    return {
        "weight_stability": ws_result, "normalization": norm_df,
        "correlation": corr_result, "rank_disagreement": rank_df,
    }


# =========================================================================
# Step 7: Baseline Sanity Check
# =========================================================================

def step7_baseline(cfg: dict) -> pd.DataFrame:
    """Step 7: synthetic load, waste recovery evaluation."""
    data = generate_synthetic_load(cfg)
    eval_df = evaluate_waste_recovery(data, cfg)
    eval_df.to_csv(OUT / "step7_SYNTHETIC_waste_recovery.csv", index=False)
    return eval_df


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
) -> str:
    """Generate outputs/report.md."""
    lines: list[str] = []
    lines.append("# CMPM Validation Harness — Report\n")
    lines.append("**Generated by automated adversarial testing pipeline.**\n")
    lines.append("All synthetic data is labeled. All assumptions from config.yaml.\n")

    # Section 1: Replication table
    lines.append("\n## 1. Replication Table (Claimed vs Computed)\n")
    lines.append("| Project | Claimed NPV | Computed NPV | Delta | PASS | Claimed Payback | Computed Payback | PASS | Claimed IRR | Computed IRR | PASS |")
    lines.append("|---------|------------|-------------|-------|------|----------------|-----------------|------|------------|-------------|------|")
    for _, row in replication.iterrows():
        lines.append(
            f"| {row['project']} | {format_currency(row['claimed_npv'])} | {format_currency(row['computed_npv'])} "
            f"| {format_currency(row['npv_delta'])} | {'PASS' if row['npv_PASS'] else '**FAIL**'} "
            f"| {row['claimed_payback']:.2f} | {row['computed_payback']:.2f} "
            f"| {'PASS' if row['payback_PASS'] else '**FAIL**'} "
            f"| {format_pct(row['claimed_irr'])} | {format_pct(row['computed_irr'])} "
            f"| {'PASS' if row['irr_PASS'] else '**FAIL**'} |"
        )

    # Section 2: Findings ranked by severity
    lines.append("\n## 2. Findings Ranked by Severity\n")

    findings = []

    # Joint downside survivors
    surv = sensitivity["survival"]
    jd_rows = surv[surv["scenario"] == "joint_downside"]
    dead_projects = jd_rows[jd_rows["npv"] < 0]["project"].tolist()
    if dead_projects:
        findings.append((1, "CRITICAL", f"Projects with NPV < 0 under joint downside ({', '.join(dead_projects)}). These do not survive adversarial testing."))
    surviving = jd_rows[jd_rows["npv"] > 0]["project"].tolist()
    if surviving:
        findings.append((3, "INFO", f"Projects surviving joint downside: {', '.join(surviving)}"))

    # Electrical project fragility
    mc_stats = mc["stats"]
    if "electrical_energy_only" in mc_stats["project"].values:
        ee_row = mc_stats[mc_stats["project"] == "electrical_energy_only"].iloc[0]
        if ee_row["P_NPV_positive"] < 0.5:
            findings.append((1, "CRITICAL", f"Electrical monitoring without avoided-failure term: P(NPV>0) = {ee_row['P_NPV_positive']:.1%}. The entire case rests on speculative failure avoidance."))

    # Interaction overstatement
    subset_df = interactions["subsets"]
    full_portfolio = subset_df[subset_df["size"] == subset_df["size"].max()].iloc[0]
    if full_portfolio["overstatement"] > 100_000:
        findings.append((2, "HIGH", f"Full portfolio naive NPV overstates by {format_currency(full_portfolio['overstatement'])} ({full_portfolio['overstatement_pct']:.1f}%) due to savings interactions."))

    # Score vs MILP disagreement
    rank_df = scoring["rank_disagreement"]
    tau_score_pi = rank_df.attrs.get("tau_score_vs_pi", 0)
    if abs(tau_score_pi) < 0.5:
        findings.append((2, "HIGH", f"Score ranking vs profitability index: Kendall tau = {tau_score_pi:.2f}. The scoring system and economic optimization disagree substantially."))

    # Heuristic gap
    sweep = optimization["sweep"]
    max_gap = sweep["gap"].max()
    if max_gap > 50_000:
        findings.append((2, "HIGH", f"Maximum NPV left on table by score-based heuristic: {format_currency(max_gap)}. MILP optimization outperforms naive score-based selection."))

    # Weight stability
    ws = scoring["weight_stability"]
    low_p_top2 = ws["summary"][ws["summary"]["P_top2"] < 0.5]
    if len(low_p_top2) > 0:
        unstable = ", ".join(low_p_top2["project"].tolist())
        findings.append((3, "MEDIUM", f"Projects with unstable top-2 ranking under weight perturbation: {unstable}"))

    # Correlation double-counting
    vif_df = scoring["correlation"]["vif_summary"]
    high_vif = vif_df[vif_df["VIF"] > 1.5]
    if len(high_vif) > 0:
        inflated = ", ".join(f"{r['criterion']} (VIF={r['VIF']:.2f})" for _, r in high_vif.iterrows())
        findings.append((3, "MEDIUM", f"Weight double-counting via correlation: {inflated}"))

    # Baseline waste recovery
    cp_row = baseline_eval[baseline_eval["model"] == "change_point_regression"].iloc[0]
    gb_row = baseline_eval[baseline_eval["model"] == "gradient_boosting"].iloc[0]
    findings.append((4, "INFO", f"Waste detection: change-point bias = {cp_row['bias']:.3f}, GB bias = {gb_row['bias']:.3f}. Both {'detect' if cp_row['detects_waste'] and gb_row['detects_waste'] else 'struggle to detect'} the 12% injected waste."))

    findings.sort(key=lambda x: x[0])
    for _, severity, desc in findings:
        lines.append(f"- **[{severity}]** {desc}")

    # Section 3: Survival assessment
    lines.append("\n## 3. Claims That Survive Adversarial Testing\n")
    lines.append("| Claim | Survives? | Evidence |")
    lines.append("|-------|----------|---------|")

    for pk in CLAIMED:
        p = cfg["projects"][pk]
        jd_npv = jd_rows[jd_rows["project"] == pk]["npv"].iloc[0] if pk in jd_rows["project"].values else None
        mc_proj = mc_stats[mc_stats["project"] == pk].iloc[0] if pk in mc_stats["project"].values else None

        survives = "Yes" if (jd_npv is not None and jd_npv > 0) else "**No**"
        p_pos = f"{mc_proj['P_NPV_positive']:.1%}" if mc_proj is not None else "N/A"
        evidence = f"Joint downside NPV = {format_currency(jd_npv) if jd_npv is not None else 'N/A'}, MC P(NPV>0) = {p_pos}"
        lines.append(f"| {pk} is NPV-positive | {survives} | {evidence} |")

    # Section 4: Config dump
    lines.append("\n## 4. Configuration (config.yaml)\n")
    lines.append("```yaml")
    with open(Path(__file__).resolve().parent / "config.yaml") as f:
        lines.append(f.read())
    lines.append("```\n")

    # Section 5: Skeptical judge Q&A
    lines.append("\n## 5. What a Skeptical Judge Would Ask\n")
    rate = cfg["general"]["discount_rate"]
    life = cfg["general"]["analysis_life_years"]

    questions = [
        ("How sensitive is the ranking to the discount rate?",
         lambda: _discount_sensitivity_answer(cfg)),
        ("What if savings are 30% lower than projected?",
         lambda: _savings_30_answer(cfg)),
        ("Are the savings estimates additive?",
         lambda: f"No. With all projects selected, interaction effects reduce portfolio NPV by {format_currency(full_portfolio['overstatement'])} ({full_portfolio['overstatement_pct']:.1f}%)."),
        ("What is the probability each project has positive NPV?",
         lambda: _mc_prob_answer(mc_stats)),
        ("Does the scoring system agree with economic analysis?",
         lambda: f"Weakly. Kendall tau between composite score and profitability index = {tau_score_pi:.2f}."),
        ("Can we detect the kind of waste this model targets?",
         lambda: f"The synthetic test injected 12% waste. Change-point model estimated {cp_row['estimated_waste_pct']:.1%}, gradient boosting estimated {gb_row['estimated_waste_pct']:.1%}."),
        ("What is the worst-case 10% NPV for each project?",
         lambda: _es_answer(mc_stats)),
    ]

    for q, a_fn in questions:
        lines.append(f"**Q: {q}**\n")
        lines.append(f"A: {a_fn()}\n")

    # Charts listing
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
        parts.append(f"{pk}: NPV ranges from {format_currency(npv_12)} (12%) to {format_currency(npv_4)} (4%)")
    return "; ".join(parts) + "."


def _savings_30_answer(cfg: dict) -> str:
    projects = cfg["projects"]
    rate = cfg["general"]["discount_rate"]
    life = cfg["general"]["analysis_life_years"]
    parts = []
    for pk in projects:
        p = projects[pk]
        npv = compute_npv(p["capex"], p["annual_benefit"] * 0.70, rate, life, cross_check=False)
        parts.append(f"{pk}: NPV = {format_currency(npv)}")
    return "; ".join(parts) + "."


def _mc_prob_answer(mc_stats: pd.DataFrame) -> str:
    parts = []
    for _, row in mc_stats.iterrows():
        if row["project"] in CLAIMED:
            parts.append(f"{row['project']}: P(NPV>0) = {row['P_NPV_positive']:.1%}")
    return "; ".join(parts) + "."


def _es_answer(mc_stats: pd.DataFrame) -> str:
    parts = []
    for _, row in mc_stats.iterrows():
        if row["project"] in CLAIMED:
            parts.append(f"{row['project']}: ES10 = {format_currency(row['expected_shortfall_10'])}")
    return "; ".join(parts) + "."


# =========================================================================
# Main
# =========================================================================

def main() -> None:
    ensure_output_dir()
    cfg = load_config()

    print("=" * 70)
    print("CMPM VALIDATION HARNESS")
    print("=" * 70)

    print("\n--- Step 1: Deterministic Replication ---")
    replication = step1_replication(cfg)
    print(replication[["project", "computed_npv", "claimed_npv", "npv_PASS",
                       "computed_irr", "claimed_irr", "irr_PASS"]].to_string(index=False))

    print("\n--- Step 2: Adversarial Sensitivity ---")
    sensitivity = step2_sensitivity(cfg)
    surv = sensitivity["survival"]
    jd = surv[surv["scenario"] == "joint_downside"][["project", "npv", "sign_flip"]]
    print("Joint downside results:")
    print(jd.to_string(index=False))

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
    print("Rank disagreement (score vs PI vs NPV):")
    rd = scr["rank_disagreement"]
    print(rd[["project", "score_rank", "pi_rank", "npv_rank"]].to_string(index=False))
    print(f"Kendall tau (score vs PI): {rd.attrs.get('tau_score_vs_pi', 'N/A'):.2f}")

    print("\n--- Step 7: Baseline Sanity Check (SYNTHETIC) ---")
    baseline_eval = step7_baseline(cfg)
    print(baseline_eval.to_string(index=False))

    print("\n--- Step 8: Generating Report ---")
    report = generate_report(cfg, replication, sensitivity, mc, interact, opt, scr, baseline_eval)
    print(f"Report written to {OUT / 'report.md'}")

    # Final summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    all_pass = replication["npv_PASS"].all() and replication["payback_PASS"].all() and replication["irr_PASS"].all()
    print(f"Step 1 replication: {'ALL PASS' if all_pass else 'FAILURES DETECTED'}")

    jd_dead = surv[(surv["scenario"] == "joint_downside") & (surv["npv"] < 0)]
    print(f"Step 2 joint downside: {len(jd_dead)} projects fail (NPV < 0)")

    mc_stats = mc["stats"]
    risky = mc_stats[mc_stats["project"].isin(CLAIMED) & (mc_stats["P_NPV_positive"] < 0.90)]
    print(f"Step 3 Monte Carlo: {len(risky)} projects with P(NPV>0) < 90%")

    full_portfolio = interact["subsets"][interact["subsets"]["size"] == interact["subsets"]["size"].max()].iloc[0]
    print(f"Step 4 interaction overstatement (full portfolio): {format_currency(full_portfolio['overstatement'])}")

    max_gap = opt["sweep"]["gap"].max()
    print(f"Step 5 max heuristic gap: {format_currency(max_gap)}")

    tau = rd.attrs.get("tau_score_vs_pi", 0)
    print(f"Step 6 score-vs-PI Kendall tau: {tau:.2f}")

    for _, row in baseline_eval.iterrows():
        print(f"Step 7 {row['model']}: waste estimate = {row['estimated_waste_pct']:.1%}, bias = {row['bias']:.3f}")

    print("\n" + "=" * 70)
    print("UNVERIFIABLE ITEMS")
    print("=" * 70)
    print("1. Sub-scores were reverse-engineered (underdetermined system) — they are SYNTHETIC.")
    print("2. Electrical avoided-failure parameters (p_fail, consequence) are ARBITRARY.")
    print("3. Interaction magnitudes (15%, 5%) are ARBITRARY — real values need field measurement.")
    print("4. Monte Carlo distribution shapes are assumed — real data would improve calibration.")
    print("5. Baseline waste model uses synthetic load — real building data needed for production use.")


if __name__ == "__main__":
    main()
