"""Multiplicative GLM tariff: fit with statsmodels, export as plain JSON, price from JSON.

A fitted model is stored as a *tariff*: an intercept plus, per rating factor, either one
coefficient per categorical level (reference level = 0) or a slope for a continuous factor.
The quote API only needs this JSON, so it does not depend on statsmodels at runtime.
"""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm


def reference_levels(factors: pd.DataFrame, weights: pd.Series, categorical: list[str]) -> dict[str, str]:
    """Base level = the level with the most exposure (actuarial convention)."""
    return {c: weights.groupby(factors[c]).sum().idxmax() for c in categorical}


def design_matrix(factors: pd.DataFrame, spec: dict) -> pd.DataFrame:
    cols = {"intercept": np.ones(len(factors))}
    for name, f in spec.items():
        if f["type"] == "continuous":
            cols[name] = factors[name].to_numpy(float) - f["center"]
        else:
            for level in f["levels"]:
                if level != f["reference"]:
                    cols[f"{name}[{level}]"] = (factors[name] == level).to_numpy(float)
    return pd.DataFrame(cols, index=factors.index)


def fit(factors: pd.DataFrame, y: np.ndarray, family: sm.families.Family, spec: dict,
        offset: np.ndarray | None = None, weights: np.ndarray | None = None):
    X = design_matrix(factors, spec)
    model = sm.GLM(y, X, family=family, offset=offset, var_weights=weights)
    return model.fit(), X.columns


def make_spec(factors: pd.DataFrame, weights: pd.Series, categorical: list[str],
              continuous: dict[str, float]) -> dict:
    """continuous maps factor -> centring value (the base profile's value)."""
    refs = reference_levels(factors, weights, categorical)
    spec = {}
    for c in factors.columns:
        if c in continuous:
            spec[c] = {"type": "continuous", "center": continuous[c]}
        elif c in categorical:
            spec[c] = {"type": "categorical", "reference": str(refs[c]),
                       "levels": sorted(factors[c].unique().tolist())}
    return spec


def to_tariff(result, spec: dict) -> dict:
    params, se = result.params, result.bse
    tariff = {"intercept": float(params["intercept"]), "factors": {}}
    for name, f in spec.items():
        if f["type"] == "continuous":
            tariff["factors"][name] = {"type": "continuous", "center": f["center"],
                                       "coef": float(params[name]), "se": float(se[name])}
        else:
            levels = {}
            for level in f["levels"]:
                key = f"{name}[{level}]"
                levels[level] = {"coef": float(params.get(key, 0.0)), "se": float(se.get(key, 0.0))}
            tariff["factors"][name] = {"type": "categorical", "reference": f["reference"], "levels": levels}
    return tariff


def predict(tariff: dict, factors: pd.DataFrame) -> np.ndarray:
    """Predicted mean (per unit exposure) for a frame of rating factors."""
    eta = np.full(len(factors), tariff["intercept"])
    for name, f in tariff["factors"].items():
        if f["type"] == "continuous":
            eta += f["coef"] * (factors[name].to_numpy(float) - f["center"])
        else:
            coefs = {k: v["coef"] for k, v in f["levels"].items()}
            eta += factors[name].map(coefs).fillna(0.0).to_numpy(float)
    return np.exp(eta)


def relativity_table(tariff: dict, model: str) -> pd.DataFrame:
    rows = []
    for name, f in tariff["factors"].items():
        if f["type"] == "continuous":
            rows.append({"model": model, "factor": name, "level": f"per unit (base {f['center']:g})",
                         "relativity": math.exp(f["coef"]),
                         "ci_low": math.exp(f["coef"] - 1.96 * f["se"]),
                         "ci_high": math.exp(f["coef"] + 1.96 * f["se"])})
        else:
            for level, v in f["levels"].items():
                rows.append({"model": model, "factor": name,
                             "level": level + (" (base)" if level == f["reference"] else ""),
                             "relativity": math.exp(v["coef"]),
                             "ci_low": math.exp(v["coef"] - 1.96 * v["se"]),
                             "ci_high": math.exp(v["coef"] + 1.96 * v["se"])})
    return pd.DataFrame(rows)


def save(obj: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2))
