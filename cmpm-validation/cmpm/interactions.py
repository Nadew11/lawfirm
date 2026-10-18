"""Project interaction adjustments: savings non-additivity and sequencing."""
from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd

from cmpm.economics import compute_npv


def interaction_matrix_from_config(
    cfg: dict[str, Any],
) -> dict[tuple[str, str], float]:
    """Parse config interactions section into {(source, target): fraction} dict."""
    matrix: dict[tuple[str, str], float] = {}
    for key, value in cfg["interactions"].items():
        parts = key.split("__")
        if len(parts) == 2:
            matrix[(parts[0], parts[1])] = float(value)
    return matrix


def adjusted_benefit(
    project_key: str,
    selected_keys: list[str],
    projects: dict[str, dict],
    interaction_mat: dict[tuple[str, str], float],
) -> float:
    """Compute adjusted annual benefit for a project given the selected portfolio.

    Reductions are additive: if lab_vent reduces plant by 15% and classroom
    reduces plant by 5%, and both are selected, plant loses 20%.
    """
    base = projects[project_key]["annual_benefit"]
    total_reduction = 0.0
    for other in selected_keys:
        if other == project_key:
            continue
        reduction = interaction_mat.get((other, project_key), 0.0)
        total_reduction += reduction
    return base * max(1.0 - total_reduction, 0.0)


def adjusted_portfolio_npv(
    selected_keys: list[str],
    projects: dict[str, dict],
    interaction_mat: dict[tuple[str, str], float],
    rate: float,
    life: int,
) -> float:
    """Compute portfolio NPV with interaction adjustments."""
    total = 0.0
    for key in selected_keys:
        adj_ben = adjusted_benefit(key, selected_keys, projects, interaction_mat)
        npv = compute_npv(projects[key]["capex"], adj_ben, rate, life, cross_check=False)
        total += npv
    return total


def naive_portfolio_npv(
    selected_keys: list[str],
    projects: dict[str, dict],
    rate: float,
    life: int,
) -> float:
    """Compute portfolio NPV without interactions (naive sum)."""
    total = 0.0
    for key in selected_keys:
        npv = compute_npv(
            projects[key]["capex"], projects[key]["annual_benefit"],
            rate, life, cross_check=False,
        )
        total += npv
    return total


def enumerate_all_subsets(
    cfg: dict[str, Any],
) -> pd.DataFrame:
    """Enumerate all 2^n subsets and compare naive vs interaction-adjusted NPV.

    Returns DataFrame with columns: subset, size, naive_npv, adjusted_npv,
    overstatement, overstatement_pct.
    """
    projects = cfg["projects"]
    rate = cfg["general"]["discount_rate"]
    life = cfg["general"]["analysis_life_years"]
    interaction_mat = interaction_matrix_from_config(cfg)
    all_keys = list(projects.keys())
    n = len(all_keys)

    rows = []
    for mask in range(1 << n):
        selected = [all_keys[i] for i in range(n) if mask & (1 << i)]
        if not selected:
            continue
        naive = naive_portfolio_npv(selected, projects, rate, life)
        adjusted = adjusted_portfolio_npv(selected, projects, interaction_mat, rate, life)
        overstatement = naive - adjusted
        overstatement_pct = (overstatement / abs(naive) * 100) if naive != 0 else 0.0
        rows.append({
            "subset": "+".join(sorted(selected)),
            "size": len(selected),
            "naive_npv": naive,
            "adjusted_npv": adjusted,
            "overstatement": overstatement,
            "overstatement_pct": overstatement_pct,
        })

    df = pd.DataFrame(rows).sort_values("adjusted_npv", ascending=False).reset_index(drop=True)
    return df


def sequencing_analysis(
    cfg: dict[str, Any],
) -> pd.DataFrame:
    """Show how order of implementation affects realized NPV.

    Compares 'plant-first' vs 'plant-last' sequencing for the subset
    that includes lab_ventilation, classroom_bas, and central_plant.
    """
    projects = cfg["projects"]
    rate = cfg["general"]["discount_rate"]
    life = cfg["general"]["analysis_life_years"]
    interaction_mat = interaction_matrix_from_config(cfg)

    subset = ["lab_ventilation", "classroom_bas", "central_plant"]
    available = [k for k in subset if k in projects]
    if len(available) < 2:
        return pd.DataFrame()

    rows = []

    # Plant-first: plant at full benefit, later projects see plant as existing
    plant_first_order = ["central_plant", "lab_ventilation", "classroom_bas"]
    plant_first_order = [k for k in plant_first_order if k in available]
    running: list[str] = []
    total_npv = 0.0
    for key in plant_first_order:
        running.append(key)
        adj_ben = adjusted_benefit(key, running, projects, interaction_mat)
        npv = compute_npv(projects[key]["capex"], adj_ben, rate, life, cross_check=False)
        total_npv += npv
    rows.append({"sequence": "plant_first", "order": " -> ".join(plant_first_order), "npv": total_npv})

    # Plant-last: lab and classroom implemented first, plant sees reduced baseline
    plant_last_order = ["lab_ventilation", "classroom_bas", "central_plant"]
    plant_last_order = [k for k in plant_last_order if k in available]
    running = []
    total_npv = 0.0
    for key in plant_last_order:
        running.append(key)
        adj_ben = adjusted_benefit(key, running, projects, interaction_mat)
        npv = compute_npv(projects[key]["capex"], adj_ben, rate, life, cross_check=False)
        total_npv += npv
    rows.append({"sequence": "plant_last", "order": " -> ".join(plant_last_order), "npv": total_npv})

    # Simultaneous (all at once — the standard interaction calculation)
    sim_npv = adjusted_portfolio_npv(available, projects, interaction_mat, rate, life)
    rows.append({"sequence": "simultaneous", "order": "all at once", "npv": sim_npv})

    return pd.DataFrame(rows)
