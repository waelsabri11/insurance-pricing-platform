"""Pricing-model metrics: deviances, ordered-Lorenz Gini, lift and double lift."""

import numpy as np
import pandas as pd
from sklearn.metrics import mean_gamma_deviance, mean_poisson_deviance


def poisson_deviance(claims: np.ndarray, exposure: np.ndarray, pred_freq: np.ndarray) -> float:
    """Exposure-weighted mean Poisson deviance on claim frequency."""
    return mean_poisson_deviance(claims / exposure, pred_freq, sample_weight=exposure)


def gamma_deviance(avg_sev: np.ndarray, n_claims: np.ndarray, pred_sev: np.ndarray) -> float:
    return mean_gamma_deviance(avg_sev, pred_sev, sample_weight=n_claims)


def lorenz_curve(y_true: np.ndarray, y_pred: np.ndarray, exposure: np.ndarray):
    """Ordered Lorenz curve: policies sorted by predicted risk (ascending); x = cumulative
    share of exposure, y = cumulative share of observed losses."""
    order = np.argsort(y_pred, kind="stable")
    cum_exp = np.concatenate([[0], np.cumsum(exposure[order])])
    cum_loss = np.concatenate([[0], np.cumsum(y_true[order])])
    return cum_exp / cum_exp[-1], cum_loss / cum_loss[-1]


def gini(y_true: np.ndarray, y_pred: np.ndarray, exposure: np.ndarray) -> float:
    """Gini = 1 - 2 * area under the ordered Lorenz curve (0 = no segmentation)."""
    x, y = lorenz_curve(y_true, y_pred, exposure)
    return 1.0 - 2.0 * np.trapezoid(y, x)


def bootstrap_gini(y_true, preds: dict[str, np.ndarray], exposure, n_boot=200, seed=0):
    """Bootstrap the Gini of each model and of each model minus the GLM."""
    rng = np.random.default_rng(seed)
    n = len(y_true)
    out = {k: [] for k in preds}
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        for k, p in preds.items():
            out[k].append(gini(y_true[idx], p[idx], exposure[idx]))
    return {k: np.array(v) for k, v in out.items()}


def exposure_quantile_bins(score: np.ndarray, exposure: np.ndarray, n_bins=10) -> np.ndarray:
    """Bin index (0..n_bins-1) such that each bin holds ~equal exposure."""
    order = np.argsort(score, kind="stable")
    cum = np.cumsum(exposure[order]) / exposure.sum()
    bins = np.empty(len(score), dtype=int)
    bins[order] = np.minimum((cum * n_bins).astype(int), n_bins - 1)
    return bins


def lift_table(losses, exposure, pred_pp, n_bins=10) -> pd.DataFrame:
    """Actual vs predicted pure premium by decile of predicted pure premium."""
    bins = exposure_quantile_bins(pred_pp, exposure, n_bins)
    df = pd.DataFrame({"bin": bins + 1, "exposure": exposure, "losses": losses, "pred": pred_pp * exposure})
    g = df.groupby("bin").sum()
    return pd.DataFrame({"exposure": g["exposure"], "actual_pp": g["losses"] / g["exposure"],
                         "predicted_pp": g["pred"] / g["exposure"]})


def double_lift_table(losses, exposure, pp_a, pp_b, n_bins=10) -> pd.DataFrame:
    """Sort by pp_b / pp_a; per decile, loss ratio of actual losses to each model's premium.
    The model whose loss ratios stay flatter around 1 is the better one where they disagree."""
    bins = exposure_quantile_bins(pp_b / pp_a, exposure, n_bins)
    df = pd.DataFrame({"bin": bins + 1, "exposure": exposure, "losses": losses,
                       "prem_a": pp_a * exposure, "prem_b": pp_b * exposure})
    g = df.groupby("bin").sum()
    return pd.DataFrame({"exposure": g["exposure"], "ratio_b_over_a": g["prem_b"] / g["prem_a"],
                         "loss_ratio_a": g["losses"] / g["prem_a"], "loss_ratio_b": g["losses"] / g["prem_b"]})
