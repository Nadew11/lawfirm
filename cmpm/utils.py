"""Shared helpers: cash-flow construction and formatting utilities."""
from __future__ import annotations

import numpy as np


def build_cashflows(
    capex: float,
    annual_benefit: float,
    life: int,
    *,
    delay_years: int = 0,
    escalation_rate: float = 0.0,
    savings_decay_rate: float = 0.0,
    residual_value_pct: float = 0.0,
    om_cost_annual_pct: float = 0.0,
) -> np.ndarray:
    """Build year-by-year cash-flow array.

    Year 0 is always -capex.  Benefits start at year (1 + delay_years).
    Returns an array of length 1 + life + delay_years.

    Parameters
    ----------
    capex : float
        Up-front capital cost (positive number).
    annual_benefit : float
        Year-1 savings / benefit.
    life : int
        Analysis period in years (from start of benefits, not from year 0).
    delay_years : int
        Implementation delay — years before benefits begin.
    escalation_rate : float
        Annual energy-price escalation applied to benefits.
    savings_decay_rate : float
        Annual savings degradation (persistence loss).
    residual_value_pct : float
        Fraction of capex recovered at end of life.
    om_cost_annual_pct : float
        Annual O&M cost as fraction of capex.
    """
    total_years = life + delay_years
    cf = np.zeros(total_years + 1)
    cf[0] = -capex

    om_annual = om_cost_annual_pct * capex

    for t in range(1, total_years + 1):
        if t <= delay_years:
            cf[t] = -om_annual if om_annual > 0 else 0.0
            continue
        benefit_year = t - delay_years
        benefit_t = annual_benefit * (1 + escalation_rate) ** (benefit_year - 1)
        benefit_t *= (1 - savings_decay_rate) ** (benefit_year - 1)
        cf[t] = benefit_t - om_annual

    if residual_value_pct > 0:
        cf[-1] += residual_value_pct * capex

    return cf


def format_currency(value: float) -> str:
    """Format a number as $X,XXX."""
    if np.isnan(value):
        return "NaN"
    return f"${value:,.0f}"


def format_pct(value: float) -> str:
    """Format a fraction as XX.X%."""
    if np.isnan(value):
        return "NaN"
    return f"{value * 100:.1f}%"
