"""Deterministic project economics: NPV, IRR, payback, sensitivity."""
from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import numpy_financial as npf
import pandas as pd
from scipy.optimize import brentq

from cmpm.utils import build_cashflows


def base_friction_kwargs(cfg: dict[str, Any]) -> dict[str, float]:
    """Extract base-case friction kwargs from config.

    Returns empty dict if apply_frictions_in_base is false/missing,
    otherwise returns the friction kwargs for build_cashflows.
    """
    if not cfg.get("apply_frictions_in_base", False):
        return {}
    f = cfg.get("frictions", {})
    return {
        "escalation_rate": f.get("energy_escalation_rate", 0.0),
        "savings_decay_rate": f.get("savings_decay_rate", 0.0),
        "residual_value_pct": f.get("residual_value_pct", 0.0),
        "om_cost_annual_pct": f.get("om_cost_annual_pct", 0.0),
    }


# ---------------------------------------------------------------------------
# Core economic functions
# ---------------------------------------------------------------------------

def compute_npv(
    capex: float,
    annual_benefit: float,
    rate: float,
    life: int,
    *,
    cross_check: bool = True,
    **friction_kwargs: Any,
) -> float:
    """Compute NPV via three independent methods and cross-check.

    Methods:
      1. Explicit discounted cash-flow sum
      2. numpy_financial.npv
      3. Annuity formula (only when no frictions active)

    Returns the explicit-sum result.
    """
    cf = build_cashflows(capex, annual_benefit, life, **friction_kwargs)
    has_frictions = any(v != 0 for v in friction_kwargs.values() if isinstance(v, (int, float)))

    # Method 1: explicit sum
    npv_explicit = sum(cf[t] / (1 + rate) ** t for t in range(len(cf)))

    # Method 2: numpy_financial (expects rate, then cash flows starting at t=0)
    npv_npf = npf.npv(rate, cf)

    if cross_check and abs(npv_explicit - npv_npf) > 0.01:
        raise ValueError(
            f"NPV cross-check failed: explicit={npv_explicit:.2f}, "
            f"npf={npv_npf:.2f}"
        )

    # Method 3: annuity formula (only valid for constant-benefit, no-friction case)
    if not has_frictions and cross_check:
        if rate > 0:
            annuity_factor = (1 - (1 + rate) ** (-life)) / rate
        else:
            annuity_factor = float(life)
        npv_annuity = -capex + annual_benefit * annuity_factor
        if abs(npv_explicit - npv_annuity) > 0.01:
            raise ValueError(
                f"NPV annuity cross-check failed: explicit={npv_explicit:.2f}, "
                f"annuity={npv_annuity:.2f}"
            )

    return float(npv_explicit)


def compute_npv_from_cashflows(cf: np.ndarray, rate: float) -> float:
    """Compute NPV directly from a pre-built cash-flow array."""
    return float(sum(cf[t] / (1 + rate) ** t for t in range(len(cf))))


def compute_irr(capex: float, annual_benefit: float, life: int) -> float:
    """Compute IRR via two methods: npf.irr and scipy.optimize.brentq.

    Returns NaN if the cash-flow stream has no sign change.
    """
    cf = np.array([-capex] + [annual_benefit] * life, dtype=float)

    if capex <= 0 or annual_benefit <= 0:
        return np.nan
    if np.all(cf >= 0) or np.all(cf <= 0):
        return np.nan

    # Method 1: numpy_financial
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        irr_npf = npf.irr(cf)

    # Method 2: brentq root-finding on NPV(r) = 0
    def npv_at_rate(r: float) -> float:
        return sum(cf[t] / (1 + r) ** t for t in range(len(cf)))

    try:
        irr_brentq = brentq(npv_at_rate, -0.5, 10.0, xtol=1e-10)
    except ValueError:
        irr_brentq = np.nan

    if not np.isnan(irr_npf) and not np.isnan(irr_brentq):
        if abs(irr_npf - irr_brentq) > 0.001:
            raise ValueError(
                f"IRR cross-check failed: npf={irr_npf:.6f}, brentq={irr_brentq:.6f}"
            )

    return float(irr_brentq if not np.isnan(irr_brentq) else irr_npf)


def compute_irr_from_cashflows(cf: np.ndarray) -> float:
    """Compute IRR from a pre-built cash-flow array."""
    if np.all(cf >= 0) or np.all(cf <= 0):
        return np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = npf.irr(cf)
    return float(result) if result is not None else np.nan


def compute_simple_payback(capex: float, annual_benefit: float) -> float:
    """Simple payback = capex / annual_benefit.

    Returns inf if annual_benefit <= 0.
    """
    if annual_benefit <= 0:
        return float("inf")
    return capex / annual_benefit


def compute_discounted_payback(
    capex: float,
    annual_benefit: float,
    rate: float,
    life: int,
    **friction_kwargs: Any,
) -> float:
    """Discounted payback: first year where cumulative discounted CF >= 0.

    Returns inf if payback never achieved within the analysis period.
    Uses fractional interpolation in the payback year.
    """
    cf = build_cashflows(capex, annual_benefit, life, **friction_kwargs)
    cumulative = 0.0
    for t in range(len(cf)):
        prev = cumulative
        cumulative += cf[t] / (1 + rate) ** t
        if cumulative >= 0 and t > 0:
            fraction = -prev / (cumulative - prev) if (cumulative - prev) != 0 else 0
            return (t - 1) + fraction
    return float("inf")


def breakeven_benefit(capex: float, rate: float, life: int) -> float:
    """Annual benefit at which NPV = 0 (break-even).

    For constant annual benefit: benefit = capex / annuity_factor.
    """
    if rate > 0:
        annuity_factor = (1 - (1 + rate) ** (-life)) / rate
    else:
        annuity_factor = float(life)
    return capex / annuity_factor


# ---------------------------------------------------------------------------
# Sensitivity analysis (Step 2)
# ---------------------------------------------------------------------------

def tornado_analysis(
    capex: float,
    annual_benefit: float,
    rate: float,
    life: int,
    param_ranges: dict[str, tuple[float, float]],
) -> pd.DataFrame:
    """One-way tornado: vary each parameter independently, return NPV swing.

    param_ranges keys: 'savings_pct', 'capex_pct', 'discount_rate', 'life_years'.
    Values are (low, high) absolute or percentage-change tuples depending on key.
    """
    base_npv = compute_npv(capex, annual_benefit, rate, life, cross_check=False)
    rows = []

    for param, (lo, hi) in param_ranges.items():
        if param == "savings_pct":
            npv_lo = compute_npv(capex, annual_benefit * (1 + lo), rate, life, cross_check=False)
            npv_hi = compute_npv(capex, annual_benefit * (1 + hi), rate, life, cross_check=False)
        elif param == "capex_pct":
            npv_lo = compute_npv(capex * (1 + lo), annual_benefit, rate, life, cross_check=False)
            npv_hi = compute_npv(capex * (1 + hi), annual_benefit, rate, life, cross_check=False)
        elif param == "discount_rate":
            npv_lo = compute_npv(capex, annual_benefit, lo, life, cross_check=False)
            npv_hi = compute_npv(capex, annual_benefit, hi, life, cross_check=False)
        elif param == "life_years":
            npv_lo = compute_npv(capex, annual_benefit, rate, int(lo), cross_check=False)
            npv_hi = compute_npv(capex, annual_benefit, rate, int(hi), cross_check=False)
        else:
            continue

        swing = abs(npv_hi - npv_lo)
        rows.append({
            "parameter": param,
            "low_value": lo,
            "high_value": hi,
            "npv_low": npv_lo,
            "npv_high": npv_hi,
            "npv_base": base_npv,
            "swing": swing,
        })

    df = pd.DataFrame(rows).sort_values("swing", ascending=False).reset_index(drop=True)
    return df


def joint_downside_npv(
    capex: float,
    annual_benefit: float,
    rate: float,
    life: int,
    scenario: dict[str, Any],
) -> float:
    """Compute NPV under a joint-adverse scenario.

    scenario keys: savings_multiplier, capex_multiplier, delay_years,
                   savings_decay_rate, life_years.
    """
    adj_capex = capex * scenario.get("capex_multiplier", 1.0)
    adj_benefit = annual_benefit * scenario.get("savings_multiplier", 1.0)
    adj_life = scenario.get("life_years", life)
    delay = scenario.get("delay_years", 0)
    decay = scenario.get("savings_decay_rate", 0.0)

    return compute_npv(
        adj_capex, adj_benefit, rate, adj_life,
        cross_check=False,
        delay_years=delay,
        savings_decay_rate=decay,
    )


def survival_table(
    projects: dict[str, dict],
    scenarios: dict[str, dict],
    rate: float,
    life: int,
) -> pd.DataFrame:
    """Build project x scenario NPV matrix with sign-flip flags.

    Supports flat scenarios {name: {params}} and tiered scenarios
    {tier_name: {sub_name: {params}}} (e.g. joint_downside.mild/moderate/severe).
    Returns DataFrame with columns: project, scenario, npv, sign_flip.
    """
    # Flatten nested scenarios
    flat_scenarios: dict[str, dict] = {}
    for sname, sdata in scenarios.items():
        if _is_scenario(sdata):
            flat_scenarios[sname] = sdata
        else:
            for sub_name, sub_data in sdata.items():
                if isinstance(sub_data, dict) and _is_scenario(sub_data):
                    flat_scenarios[f"{sname}_{sub_name}"] = sub_data

    rows = []
    for pkey, pdata in projects.items():
        base_npv = compute_npv(
            pdata["capex"], pdata["annual_benefit"], rate, life, cross_check=False
        )
        rows.append({
            "project": pkey,
            "scenario": "base",
            "npv": base_npv,
            "sign_flip": False,
        })
        for sname, scenario in flat_scenarios.items():
            npv = joint_downside_npv(
                pdata["capex"], pdata["annual_benefit"], rate, life, scenario
            )
            rows.append({
                "project": pkey,
                "scenario": sname,
                "npv": npv,
                "sign_flip": (npv < 0) != (base_npv < 0),
            })
    return pd.DataFrame(rows)


def _is_scenario(d: dict) -> bool:
    """Check if a dict looks like a scenario (has scenario keys, not nested dicts)."""
    scenario_keys = {"savings_multiplier", "capex_multiplier", "delay_years",
                     "savings_decay_rate", "life_years"}
    return bool(scenario_keys & set(d.keys()))


def friction_comparison(
    projects: dict[str, dict],
    rate: float,
    life: int,
    frictions: dict[str, float],
) -> pd.DataFrame:
    """Rank projects with each friction toggled on individually vs baseline.

    Returns DataFrame showing how rankings change.
    """
    friction_map = {
        "escalation": {"escalation_rate": frictions.get("energy_escalation_rate", 0.02)},
        "decay": {"savings_decay_rate": frictions.get("savings_decay_rate", 0.03)},
        "residual": {"residual_value_pct": frictions.get("residual_value_pct", 0.10)},
        "om_cost": {"om_cost_annual_pct": frictions.get("om_cost_annual_pct", 0.02)},
    }

    rows = []
    for pkey, pdata in projects.items():
        base_npv = compute_npv(
            pdata["capex"], pdata["annual_benefit"], rate, life, cross_check=False
        )
        row: dict[str, Any] = {"project": pkey, "npv_base": base_npv}
        for fname, fkwargs in friction_map.items():
            npv_f = compute_npv(
                pdata["capex"], pdata["annual_benefit"], rate, life,
                cross_check=False, **fkwargs,
            )
            row[f"npv_{fname}"] = npv_f
        rows.append(row)

    df = pd.DataFrame(rows)
    df["rank_base"] = df["npv_base"].rank(ascending=False).astype(int)
    for fname in friction_map:
        df[f"rank_{fname}"] = df[f"npv_{fname}"].rank(ascending=False).astype(int)
    return df
