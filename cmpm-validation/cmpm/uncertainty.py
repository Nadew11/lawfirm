"""Monte Carlo uncertainty analysis with Gaussian copula correlation."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm, triang, beta as beta_dist

from cmpm.economics import compute_npv, compute_simple_payback
from cmpm.utils import build_cashflows


def _triangular_ppf(u: np.ndarray, low: float, mode: float, high: float) -> np.ndarray:
    """Inverse CDF of triangular distribution for uniform inputs in [0,1]."""
    c = (mode - low) / (high - low)
    return triang.ppf(u, c, loc=low, scale=high - low)


def _lognormal_ppf(u: np.ndarray, mean: float, sigma: float) -> np.ndarray:
    """Inverse CDF of lognormal parameterised by desired mean and sigma of the log."""
    mu_log = np.log(mean) - 0.5 * sigma ** 2
    return np.exp(norm.ppf(u) * sigma + mu_log)


def generate_correlated_draws(
    n: int,
    rho: float,
    seed: int,
    mc_cfg: dict[str, Any],
) -> dict[str, np.ndarray]:
    """Generate correlated Monte Carlo draws via Gaussian copula.

    Returns dict with keys: savings_mult, capex_mult, delay_years,
    discount_rate, savings_decay.
    """
    rng = np.random.default_rng(seed)

    # Cholesky decomposition for savings-capex correlation
    corr = np.array([[1.0, rho], [rho, 1.0]])
    L = np.linalg.cholesky(corr)
    z = rng.standard_normal((n, 2))
    z_corr = z @ L.T
    u = norm.cdf(z_corr)  # uniform marginals

    # Savings multiplier: triangular
    tri_params = mc_cfg["savings_triangular"]
    savings_mult = _triangular_ppf(u[:, 0], tri_params[0], tri_params[1], tri_params[2])

    # Capex multiplier: lognormal (right-skewed overruns)
    capex_mult = _lognormal_ppf(u[:, 1], 1.0, mc_cfg["capex_lognormal_sigma"])

    # Delay: independent discrete draw
    delay_dist = mc_cfg["delay_distribution"]
    delay_vals = np.array(list(delay_dist.keys()), dtype=int)
    delay_probs = np.array(list(delay_dist.values()), dtype=float)
    delay_years = rng.choice(delay_vals, size=n, p=delay_probs)

    # Discount rate: independent triangular
    disc_params = mc_cfg["discount_triangular"]
    u_disc = rng.uniform(0, 1, n)
    discount_rate = _triangular_ppf(u_disc, disc_params[0], disc_params[1], disc_params[2])

    # Savings decay: independent uniform
    decay_params = mc_cfg["decay_uniform"]
    savings_decay = rng.uniform(decay_params[0], decay_params[1], n)

    return {
        "savings_mult": savings_mult,
        "capex_mult": capex_mult,
        "delay_years": delay_years,
        "discount_rate": discount_rate,
        "savings_decay": savings_decay,
    }


def monte_carlo_npv(
    capex: float,
    annual_benefit: float,
    life: int,
    draws: dict[str, np.ndarray],
) -> np.ndarray:
    """Compute NPV for each Monte Carlo draw.

    Returns array of length n.
    """
    n = len(draws["savings_mult"])
    npvs = np.empty(n)
    for i in range(n):
        adj_capex = capex * draws["capex_mult"][i]
        adj_benefit = annual_benefit * draws["savings_mult"][i]
        rate = draws["discount_rate"][i]
        delay = int(draws["delay_years"][i])
        decay = draws["savings_decay"][i]

        cf = build_cashflows(
            adj_capex, adj_benefit, life,
            delay_years=delay,
            savings_decay_rate=decay,
        )
        npvs[i] = sum(cf[t] / (1 + rate) ** t for t in range(len(cf)))
    return npvs


def monte_carlo_payback(
    capex: float,
    annual_benefit: float,
    draws: dict[str, np.ndarray],
) -> np.ndarray:
    """Simple payback for each draw."""
    n = len(draws["savings_mult"])
    paybacks = np.empty(n)
    for i in range(n):
        adj_capex = capex * draws["capex_mult"][i]
        adj_benefit = annual_benefit * draws["savings_mult"][i]
        if adj_benefit <= 0:
            paybacks[i] = np.inf
        else:
            paybacks[i] = adj_capex / adj_benefit
    return paybacks


def electrical_avoided_failure_mc(
    elec_cfg: dict[str, Any],
    mc_cfg: dict[str, Any],
    n: int,
    seed: int,
) -> dict[str, np.ndarray]:
    """Model avoided-failure benefit with distributional uncertainty.

    Returns dict with keys:
        'benefit_full' — energy + avoided_failure (version a)
        'benefit_energy_only' — energy only (version b)
        'avoided_failure_per_year' — just the avoided-failure component
    """
    rng = np.random.default_rng(seed + 1000)

    alpha = elec_cfg["failure_probability_beta_alpha"]
    beta_param = elec_cfg["failure_probability_beta_beta"]
    p_fail = beta_dist.rvs(alpha, beta_param, size=n, random_state=rng)

    consequence_mean = elec_cfg["failure_consequence"]
    consequence_sigma = elec_cfg["failure_consequence_log_sigma"]
    mu_log = np.log(consequence_mean) - 0.5 * consequence_sigma ** 2
    consequence = rng.lognormal(mu_log, consequence_sigma, n)

    avoided_failure = p_fail * consequence
    energy_only = elec_cfg["energy_only_benefit"]

    return {
        "benefit_full": energy_only + avoided_failure,
        "benefit_energy_only": np.full(n, energy_only, dtype=float),
        "avoided_failure_per_year": avoided_failure,
    }


def compute_mc_stats(npv_array: np.ndarray, payback_array: np.ndarray | None = None) -> dict[str, float]:
    """Compute summary statistics for a Monte Carlo NPV distribution.

    Returns: P10, P50, P90, P(NPV>0), P(payback<4), expected_shortfall_10.
    """
    p10, p50, p90 = np.percentile(npv_array, [10, 50, 90])
    prob_positive = float(np.mean(npv_array > 0))

    prob_payback_lt4 = float("nan")
    if payback_array is not None:
        prob_payback_lt4 = float(np.mean(payback_array < 4.0))

    worst_10_pct = npv_array[npv_array <= np.percentile(npv_array, 10)]
    expected_shortfall = float(np.mean(worst_10_pct)) if len(worst_10_pct) > 0 else float("nan")

    return {
        "P10": float(p10),
        "P50": float(p50),
        "P90": float(p90),
        "P_NPV_positive": prob_positive,
        "P_payback_lt4": prob_payback_lt4,
        "expected_shortfall_10": expected_shortfall,
    }


def run_monte_carlo_all_projects(
    cfg: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Run full Monte Carlo for all projects.  Returns per-project stats + NPV arrays."""
    seed = cfg["general"]["random_seed"]
    n = cfg["general"]["monte_carlo_draws"]
    life = cfg["general"]["analysis_life_years"]
    mc_cfg = cfg["monte_carlo"]
    rho = mc_cfg["correlation_rho"]

    draws = generate_correlated_draws(n, rho, seed, mc_cfg)
    results: dict[str, dict[str, Any]] = {}

    for pkey, pdata in cfg["projects"].items():
        npvs = monte_carlo_npv(pdata["capex"], pdata["annual_benefit"], life, draws)
        paybacks = monte_carlo_payback(pdata["capex"], pdata["annual_benefit"], draws)
        stats = compute_mc_stats(npvs, paybacks)
        results[pkey] = {"npvs": npvs, "paybacks": paybacks, "stats": stats}

    # Electrical project: two versions
    elec_cfg = cfg["electrical_project"]
    elec_draws = electrical_avoided_failure_mc(elec_cfg, mc_cfg, n, seed)

    for version, benefit_key in [("full", "benefit_full"), ("energy_only", "benefit_energy_only")]:
        benefits = elec_draws[benefit_key]
        npvs = np.empty(n)
        paybacks = np.empty(n)
        capex = cfg["projects"]["electrical_monitoring"]["capex"]
        for i in range(n):
            adj_capex = capex * draws["capex_mult"][i]
            rate = draws["discount_rate"][i]
            delay = int(draws["delay_years"][i])
            decay = draws["savings_decay"][i]
            cf = build_cashflows(adj_capex, benefits[i], life, delay_years=delay, savings_decay_rate=decay)
            npvs[i] = sum(cf[t] / (1 + rate) ** t for t in range(len(cf)))
            paybacks[i] = adj_capex / benefits[i] if benefits[i] > 0 else np.inf
        stats = compute_mc_stats(npvs, paybacks)
        results[f"electrical_{version}"] = {"npvs": npvs, "paybacks": paybacks, "stats": stats}

    return results


def correlation_impact(
    cfg: dict[str, Any],
    project_key: str = "lab_ventilation",
) -> dict[str, dict[str, float]]:
    """Compare MC stats with correlation (rho from config) vs independence (rho=0)."""
    seed = cfg["general"]["random_seed"]
    n = cfg["general"]["monte_carlo_draws"]
    life = cfg["general"]["analysis_life_years"]
    mc_cfg = cfg["monte_carlo"]
    pdata = cfg["projects"][project_key]

    out = {}
    for label, rho in [("correlated", mc_cfg["correlation_rho"]), ("independent", 0.0)]:
        draws = generate_correlated_draws(n, rho, seed, mc_cfg)
        npvs = monte_carlo_npv(pdata["capex"], pdata["annual_benefit"], life, draws)
        paybacks = monte_carlo_payback(pdata["capex"], pdata["annual_benefit"], draws)
        out[label] = compute_mc_stats(npvs, paybacks)
    return out
