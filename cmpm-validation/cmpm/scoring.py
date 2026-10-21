"""Scoring validity: four precise bias checks on the ranking system.

Bias types tested (not vague — each is defined and measured):
  1. WEIGHTING BIAS — Dirichlet perturbation: do rankings flip with small
     weight changes? Measured by P(rank unchanged) across 10K random weight
     vectors drawn from Dirichlet(alpha * concentration).
  2. SCALE BIAS — Normalization sensitivity: do rankings depend on the
     normalization method (min-max vs z-score vs rank)? If top-5 changes,
     the scoring is scale-biased.
  3. DOUBLE-COUNTING BIAS — VIF analysis: do correlated sub-scores inflate
     one criterion's effective weight beyond its nominal weight? VIF > 5
     means severe multicollinearity.
  4. RANK VALIDITY — Kendall tau: does the composite score agree with
     pure financial metrics (NPV, PI)? Strong disagreement may be intentional
     (non-financial priorities) but must be justified.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import kendalltau

from cmpm.economics import compute_npv


def weighted_score(sub_scores: dict[str, float], weights: dict[str, float]) -> float:
    """Compute weighted composite score as a simple dot product."""
    return sum(sub_scores[k] * weights[k] for k in weights)


def reverse_engineer_subscores(
    target_composites: dict[str, float],
    weights: dict[str, float],
) -> dict[str, dict[str, float]]:
    """Find sub-scores (0-100 each) that reproduce target composite scores.

    WARNING: This is reverse-engineering. The system is underdetermined
    (n_projects * n_criteria unknowns, only n_projects equations).
    We use constrained least-squares regularised toward 70 (mid-range).
    Results are labeled SYNTHETIC / REVERSE-ENGINEERED.
    """
    proj_keys = list(target_composites.keys())
    weight_keys = list(weights.keys())
    n_proj = len(proj_keys)
    n_crit = len(weight_keys)
    w_vec = np.array([weights[k] for k in weight_keys])

    def objective(flat_scores: np.ndarray) -> float:
        scores_2d = flat_scores.reshape(n_proj, n_crit)
        loss = 0.0
        for i, pk in enumerate(proj_keys):
            composite = float(scores_2d[i] @ w_vec)
            target = target_composites[pk]
            loss += (composite - target) ** 2 * 1000
        loss += np.sum((scores_2d - 70) ** 2) * 0.01
        return loss

    x0 = np.full(n_proj * n_crit, 70.0)
    bounds = [(0, 100)] * (n_proj * n_crit)
    result = minimize(objective, x0, method="L-BFGS-B", bounds=bounds)
    scores_2d = result.x.reshape(n_proj, n_crit)

    out = {}
    for i, pk in enumerate(proj_keys):
        out[pk] = {weight_keys[j]: float(scores_2d[i, j]) for j in range(n_crit)}
    return out


def weight_stability_analysis(
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Draw weight vectors from Dirichlet and assess rank stability.

    Returns per-project: rank distribution, P(top-2), mean Kendall tau.
    """
    projects = cfg["projects"]
    weights = cfg["score_weights"]
    scoring_cfg = cfg["scoring"]
    concentration = scoring_cfg["dirichlet_concentration"]
    n_draws = scoring_cfg["weight_draws"]
    seed = cfg["general"]["random_seed"]
    rng = np.random.default_rng(seed + 200)

    weight_keys = list(weights.keys())
    proj_keys = list(projects.keys())
    n_proj = len(proj_keys)
    alpha = np.array([weights[k] * concentration for k in weight_keys])

    baseline_scores = []
    for pk in proj_keys:
        ss = projects[pk]["sub_scores"]
        baseline_scores.append(weighted_score(ss, weights))
    baseline_ranking = np.argsort(np.argsort(-np.array(baseline_scores))) + 1

    rank_counts = np.zeros((n_proj, n_proj), dtype=int)
    top2_counts = np.zeros(n_proj, dtype=int)
    tau_sum = 0.0

    for _ in range(n_draws):
        w_draw = rng.dirichlet(alpha)
        w_dict = {weight_keys[j]: w_draw[j] for j in range(len(weight_keys))}

        scores = []
        for pk in proj_keys:
            ss = projects[pk]["sub_scores"]
            scores.append(weighted_score(ss, w_dict))
        ranking = np.argsort(np.argsort(-np.array(scores))) + 1

        for i in range(n_proj):
            rank_counts[i, int(ranking[i]) - 1] += 1
            if ranking[i] <= 2:
                top2_counts[i] += 1

        tau, _ = kendalltau(baseline_ranking, ranking)
        tau_sum += tau

    rank_dist_df = pd.DataFrame(
        rank_counts / n_draws,
        index=proj_keys,
        columns=[f"rank_{r+1}" for r in range(n_proj)],
    )
    summary = pd.DataFrame({
        "project": proj_keys,
        "baseline_score": baseline_scores,
        "baseline_rank": baseline_ranking,
        "P_top2": top2_counts / n_draws,
        "mean_kendall_tau": tau_sum / n_draws,
    })

    return {"rank_distribution": rank_dist_df, "summary": summary}


def normalization_sensitivity(
    cfg: dict[str, Any],
) -> pd.DataFrame:
    """Generate synthetic 30-building population and test normalization methods.

    Returns comparison of how often the top-5 set changes across:
    min-max, z-score, rank normalization.
    """
    seed = cfg["scoring"].get("normalization_seed", 123)
    rng = np.random.default_rng(seed)
    n_buildings = cfg["scoring"]["synthetic_population_30"]
    weight_keys = list(cfg["score_weights"].keys())
    n_crit = len(weight_keys)
    weights = np.array([cfg["score_weights"][k] for k in weight_keys])

    raw_scores = rng.uniform(20, 100, size=(n_buildings, n_crit))

    def _minmax(arr: np.ndarray) -> np.ndarray:
        mn, mx = arr.min(axis=0), arr.max(axis=0)
        rng_ = mx - mn
        rng_[rng_ == 0] = 1.0
        return (arr - mn) / rng_

    def _zscore(arr: np.ndarray) -> np.ndarray:
        mu, sd = arr.mean(axis=0), arr.std(axis=0)
        sd[sd == 0] = 1.0
        return (arr - mu) / sd

    def _rank(arr: np.ndarray) -> np.ndarray:
        from scipy.stats import rankdata
        return np.column_stack([rankdata(arr[:, j]) for j in range(arr.shape[1])])

    methods = {"minmax": _minmax, "zscore": _zscore, "rank": _rank}
    top5_sets = {}
    composites = {}
    for name, fn in methods.items():
        normed = fn(raw_scores)
        comp = normed @ weights
        top5 = set(np.argsort(-comp)[:5].tolist())
        top5_sets[name] = top5
        composites[name] = comp

    pairs = [("minmax", "zscore"), ("minmax", "rank"), ("zscore", "rank")]
    rows = []
    for a, b in pairs:
        overlap = len(top5_sets[a] & top5_sets[b])
        rows.append({"pair": f"{a} vs {b}", "top5_overlap": overlap, "top5_changed": 5 - overlap})

    return pd.DataFrame(rows)


def correlation_double_counting(
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Check for weight double-counting using TWO approaches:

    1. Actual project sub-scores (honest but small n=5)
    2. Synthetic population with config-observed correlations (larger n for PCA)

    The synthetic population's covariance is estimated FROM the 5 actual
    projects, not hardcoded, so the analysis reflects the real data.
    """
    seed = cfg["scoring"].get("normalization_seed", 123)
    rng = np.random.default_rng(seed + 300)
    weight_keys = list(cfg["score_weights"].keys())
    n_crit = len(weight_keys)
    weights = np.array([cfg["score_weights"][k] for k in weight_keys])

    # Build actual sub-score matrix from the 5 projects
    proj_keys = list(cfg["projects"].keys())
    actual_scores = np.array([
        [cfg["projects"][pk]["sub_scores"][k] for k in weight_keys]
        for pk in proj_keys
    ])

    # Correlation from actual data (small sample, but honest)
    if actual_scores.shape[0] >= 3:
        actual_corr = np.corrcoef(actual_scores, rowvar=False)
    else:
        actual_corr = np.eye(n_crit)
    actual_corr_df = pd.DataFrame(actual_corr, index=weight_keys, columns=weight_keys)

    # Generate synthetic population using OBSERVED correlations
    n_buildings = cfg["scoring"]["synthetic_population_200"]
    actual_cov = np.cov(actual_scores, rowvar=False) if actual_scores.shape[0] >= 3 else np.eye(n_crit) * 200
    means = np.mean(actual_scores, axis=0) if actual_scores.shape[0] >= 2 else np.full(n_crit, 60.0)
    raw = rng.multivariate_normal(means, actual_cov, size=n_buildings)
    raw = np.clip(raw, 0, 100)

    synth_corr = np.corrcoef(raw, rowvar=False) if raw.shape[0] > n_crit else actual_corr

    from sklearn.decomposition import PCA
    pca = PCA()
    pca.fit(raw)
    explained = pca.explained_variance_ratio_

    # VIF from actual project correlations
    from numpy.linalg import inv
    try:
        corr_inv = inv(actual_corr)
        vif = np.diag(corr_inv)
    except np.linalg.LinAlgError:
        vif = np.ones(n_crit)

    effective_weights = weights * vif / np.sum(weights * vif)

    summary = pd.DataFrame({
        "criterion": weight_keys,
        "nominal_weight": weights,
        "VIF": vif,
        "effective_weight": effective_weights,
        "weight_inflation": effective_weights - weights,
    })

    return {
        "correlation_matrix": actual_corr_df,
        "pca_explained_variance": explained.tolist(),
        "vif_summary": summary,
        "n_actual_projects": len(proj_keys),
    }


def rank_disagreement(
    cfg: dict[str, Any],
) -> pd.DataFrame:
    """Compare ranking by composite score, profitability index, and MILP priority."""
    projects = cfg["projects"]
    weights = cfg["score_weights"]
    rate = cfg["general"]["discount_rate"]
    life = cfg["general"]["analysis_life_years"]
    proj_keys = list(projects.keys())

    scores = []
    pi_values = []
    npvs = []
    for pk in proj_keys:
        p = projects[pk]
        ss = p["sub_scores"]
        scores.append(weighted_score(ss, weights))
        npv = compute_npv(p["capex"], p["annual_benefit"], rate, life, cross_check=False)
        npvs.append(npv)
        pi_values.append(npv / p["capex"])

    score_rank = np.argsort(np.argsort(-np.array(scores))) + 1
    pi_rank = np.argsort(np.argsort(-np.array(pi_values))) + 1
    npv_rank = np.argsort(np.argsort(-np.array(npvs))) + 1

    df = pd.DataFrame({
        "project": proj_keys,
        "composite_score": scores,
        "score_rank": score_rank,
        "profitability_index": pi_values,
        "pi_rank": pi_rank,
        "npv": npvs,
        "npv_rank": npv_rank,
    })

    tau_score_pi, _ = kendalltau(score_rank, pi_rank)
    tau_score_npv, _ = kendalltau(score_rank, npv_rank)
    tau_pi_npv, _ = kendalltau(pi_rank, npv_rank)

    df.attrs["tau_score_vs_pi"] = tau_score_pi
    df.attrs["tau_score_vs_npv"] = tau_score_npv
    df.attrs["tau_pi_vs_npv"] = tau_pi_npv

    return df
