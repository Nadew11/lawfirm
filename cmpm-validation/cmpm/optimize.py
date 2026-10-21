"""MILP portfolio optimization, budget sweep, multi-year extension."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pulp

from cmpm.economics import compute_npv
from cmpm.interactions import (
    adjusted_portfolio_npv,
    interaction_matrix_from_config,
    naive_portfolio_npv,
)


def _solver() -> pulp.LpSolver:
    """Return a quiet MILP solver (HiGHS preferred, fallback to default)."""
    available = pulp.listSolvers(onlyAvailable=True)
    if "HiGHS" in available:
        return pulp.HiGHS(msg=0)
    if "HiGHS_CMD" in available:
        return pulp.HiGHS_CMD(msg=0)
    if "COIN_CMD" in available:
        return pulp.COIN_CMD(msg=0)
    raise RuntimeError(f"No MILP solver found. Available: {available}")


def milp_optimize(
    cfg: dict[str, Any],
    budget: float,
    *,
    use_interactions: bool = True,
    apply_dependency: bool = False,
    apply_exclusion: bool = False,
) -> dict[str, Any]:
    """Solve single-period portfolio selection via MILP.

    Since n=5 is tiny, we also enumerate all 2^5 subsets as ground truth.
    The MILP uses pairwise linearisation variables for interaction terms.
    """
    projects = cfg["projects"]
    rate = cfg["general"]["discount_rate"]
    life = cfg["general"]["analysis_life_years"]
    interaction_mat = interaction_matrix_from_config(cfg) if use_interactions else {}
    keys = list(projects.keys())
    n = len(keys)

    # --- Brute-force enumeration (ground truth) ---
    best_enum_npv = -np.inf
    best_enum_set: list[str] = []
    for mask in range(1 << n):
        selected = [keys[i] for i in range(n) if mask & (1 << i)]
        total_capex = sum(projects[k]["capex"] for k in selected)
        if total_capex > budget:
            continue

        if apply_dependency:
            dep = cfg["optimization"].get("dependency", {})
            feasible = True
            for proj, req in dep.items():
                if proj in selected and req not in selected:
                    feasible = False
                    break
            if not feasible:
                continue

        if apply_exclusion:
            excl_groups = cfg["optimization"].get("mutual_exclusion", [])
            feasible = True
            for group in excl_groups:
                count = sum(1 for p in group if p in selected)
                if count > 1:
                    feasible = False
                    break
            if not feasible:
                continue

        if use_interactions:
            npv = adjusted_portfolio_npv(selected, projects, interaction_mat, rate, life)
        else:
            npv = naive_portfolio_npv(selected, projects, rate, life)

        if npv > best_enum_npv:
            best_enum_npv = npv
            best_enum_set = selected

    # --- MILP formulation ---
    prob = pulp.LpProblem("CMPM_Portfolio", pulp.LpMaximize)
    x = {k: prob.add_variable(f"x_{k}", cat="Binary") for k in keys}

    indiv_npv = {}
    for k in keys:
        indiv_npv[k] = compute_npv(
            projects[k]["capex"], projects[k]["annual_benefit"],
            rate, life, cross_check=False,
        )

    # Pairwise interaction terms y[i,j] for linearisation
    y = {}
    interaction_npv_delta = {}
    for (src, tgt), frac in interaction_mat.items():
        if src in keys and tgt in keys:
            y_var = prob.add_variable(f"y_{src}_{tgt}", cat="Binary")
            y[(src, tgt)] = y_var
            prob += y_var <= x[src]
            prob += y_var <= x[tgt]
            prob += y_var >= x[src] + x[tgt] - 1
            reduced_benefit = projects[tgt]["annual_benefit"] * frac
            if rate > 0:
                annuity = (1 - (1 + rate) ** (-life)) / rate
            else:
                annuity = float(life)
            interaction_npv_delta[(src, tgt)] = reduced_benefit * annuity

    prob += (
        pulp.lpSum(indiv_npv[k] * x[k] for k in keys)
        - pulp.lpSum(interaction_npv_delta[pair] * y[pair] for pair in y)
    )

    prob += pulp.lpSum(projects[k]["capex"] * x[k] for k in keys) <= budget

    if apply_dependency:
        dep = cfg["optimization"].get("dependency", {})
        for proj, req in dep.items():
            if proj in keys and req in keys:
                prob += x[proj] <= x[req]

    if apply_exclusion:
        excl_groups = cfg["optimization"].get("mutual_exclusion", [])
        for group in excl_groups:
            valid = [p for p in group if p in keys]
            if len(valid) > 1:
                prob += pulp.lpSum(x[p] for p in valid) <= 1

    prob.solve(_solver())

    milp_selected = [k for k in keys if pulp.value(x[k]) > 0.5]
    milp_npv = pulp.value(prob.objective)

    return {
        "milp_selected": sorted(milp_selected),
        "milp_npv": milp_npv,
        "enum_selected": sorted(best_enum_set),
        "enum_npv": best_enum_npv if best_enum_npv > -np.inf else 0.0,
        "budget": budget,
    }


def heuristic_greedy_by_score(
    cfg: dict[str, Any],
    budget: float,
    *,
    use_interactions: bool = True,
) -> dict[str, Any]:
    """Greedy heuristic: add projects in descending strategic_score order until budget is exhausted."""
    projects = cfg["projects"]
    rate = cfg["general"]["discount_rate"]
    life = cfg["general"]["analysis_life_years"]
    interaction_mat = interaction_matrix_from_config(cfg) if use_interactions else {}

    sorted_keys = sorted(projects.keys(), key=lambda k: projects[k]["strategic_score"], reverse=True)
    selected: list[str] = []
    total_capex = 0.0
    for k in sorted_keys:
        if total_capex + projects[k]["capex"] <= budget:
            selected.append(k)
            total_capex += projects[k]["capex"]

    if use_interactions:
        npv = adjusted_portfolio_npv(selected, projects, interaction_mat, rate, life)
    else:
        npv = naive_portfolio_npv(selected, projects, rate, life)

    return {"selected": sorted(selected), "npv": npv, "capex": total_capex}


def budget_sweep(cfg: dict[str, Any]) -> pd.DataFrame:
    """Sweep budget range and compare optimal vs heuristic selection."""
    sweep = cfg["optimization"]["budget_sweep"]
    budgets = np.arange(sweep["min"], sweep["max"] + sweep["step"], sweep["step"])
    rows = []
    for b in budgets:
        b = float(b)
        opt = milp_optimize(cfg, b)
        heur = heuristic_greedy_by_score(cfg, b)
        gap = opt["milp_npv"] - heur["npv"]
        gap_pct = (gap / opt["milp_npv"] * 100) if opt["milp_npv"] > 0 else 0.0
        rows.append({
            "budget": b,
            "optimal_npv": opt["milp_npv"],
            "optimal_set": ", ".join(opt["milp_selected"]),
            "heuristic_npv": heur["npv"],
            "heuristic_set": ", ".join(heur["selected"]),
            "gap": gap,
            "gap_pct": gap_pct,
        })
    return pd.DataFrame(rows)


def shadow_prices(cfg: dict[str, Any], budget: float) -> pd.DataFrame:
    """Compute shadow prices: NPV cost of each constraint."""
    base = milp_optimize(cfg, budget, apply_dependency=False, apply_exclusion=False)
    dep_only = milp_optimize(cfg, budget, apply_dependency=True, apply_exclusion=False)
    excl_only = milp_optimize(cfg, budget, apply_dependency=False, apply_exclusion=True)
    both = milp_optimize(cfg, budget, apply_dependency=True, apply_exclusion=True)

    rows = [
        {"constraint": "none", "npv": base["milp_npv"], "cost": 0.0,
         "selected": ", ".join(base["milp_selected"])},
        {"constraint": "dependency_only", "npv": dep_only["milp_npv"],
         "cost": base["milp_npv"] - dep_only["milp_npv"],
         "selected": ", ".join(dep_only["milp_selected"])},
        {"constraint": "exclusion_only", "npv": excl_only["milp_npv"],
         "cost": base["milp_npv"] - excl_only["milp_npv"],
         "selected": ", ".join(excl_only["milp_selected"])},
        {"constraint": "both", "npv": both["milp_npv"],
         "cost": base["milp_npv"] - both["milp_npv"],
         "selected": ", ".join(both["milp_selected"])},
    ]
    return pd.DataFrame(rows)


def multi_year_milp(cfg: dict[str, Any]) -> dict[str, Any]:
    """Multi-year extension: x[i,t] for t in 1..T with per-year budget.

    Benefits for project i start the year after install.
    NPV accounts for delayed benefit start.
    """
    projects = cfg["projects"]
    rate = cfg["general"]["discount_rate"]
    life = cfg["general"]["analysis_life_years"]
    keys = list(projects.keys())
    my_cfg = cfg["optimization"]["multi_year"]
    T = my_cfg["num_periods"]
    budgets_per_year = my_cfg["budgets"]

    prob = pulp.LpProblem("CMPM_MultiYear", pulp.LpMaximize)

    x = {}
    for k in keys:
        for t in range(T):
            x[(k, t)] = prob.add_variable(f"x_{k}_{t}", cat="Binary")

    for k in keys:
        prob += pulp.lpSum(x[(k, t)] for t in range(T)) <= 1

    for t in range(T):
        prob += pulp.lpSum(projects[k]["capex"] * x[(k, t)] for k in keys) <= budgets_per_year[t]

    obj_terms = []
    for k in keys:
        for t in range(T):
            npv_t = compute_npv(
                projects[k]["capex"], projects[k]["annual_benefit"],
                rate, life, cross_check=False, delay_years=t,
            )
            obj_terms.append(npv_t * x[(k, t)])

    prob += pulp.lpSum(obj_terms)
    prob.solve(_solver())

    result_selected = {}
    for k in keys:
        for t in range(T):
            if pulp.value(x[(k, t)]) is not None and pulp.value(x[(k, t)]) > 0.5:
                result_selected[k] = t

    total_npv = pulp.value(prob.objective)

    return {
        "selected": result_selected,
        "total_npv": total_npv,
        "budgets": budgets_per_year,
    }


def efficient_frontier(sweep_df: pd.DataFrame) -> dict[str, Any]:
    """Extract Pareto-optimal points and find where frontier flattens."""
    budgets = sweep_df["budget"].values
    npvs = sweep_df["optimal_npv"].values

    frontier_mask = np.ones(len(budgets), dtype=bool)
    max_npv_so_far = -np.inf
    for i in range(len(budgets)):
        if npvs[i] > max_npv_so_far:
            max_npv_so_far = npvs[i]
        else:
            frontier_mask[i] = False

    frontier_budgets = budgets[frontier_mask]
    frontier_npvs = npvs[frontier_mask]

    if len(frontier_budgets) > 1:
        marginals = np.diff(frontier_npvs) / np.diff(frontier_budgets)
        max_marginal = np.max(marginals) if len(marginals) > 0 else 1.0
        flatten_idx = np.argmax(marginals < 0.1 * max_marginal)
        flatten_budget = frontier_budgets[flatten_idx + 1] if flatten_idx > 0 else frontier_budgets[-1]
    else:
        flatten_budget = frontier_budgets[0] if len(frontier_budgets) > 0 else 0

    return {
        "frontier_budgets": frontier_budgets.tolist(),
        "frontier_npvs": frontier_npvs.tolist(),
        "flatten_budget": float(flatten_budget),
    }
