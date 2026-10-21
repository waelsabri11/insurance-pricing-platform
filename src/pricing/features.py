"""Rating-factor definitions shared by model training and the quote API.

The GLM uses the classic freMTPL2 case-study preparation (Noll, Salzmann & Wuthrich, 2018):
banded driver and vehicle age, vehicle power capped at 9, bonus-malus capped at 150 and
log population density. The Area code is left out of the models: it is a banding of the
same density, and using both makes the two coefficients unstable. Keeping these rules in one
module means the API prices a quote with exactly the transformations the model was fitted on.
"""

import math

import numpy as np
import pandas as pd

DRIVER_AGE_BANDS = [(18, 20, "18-20"), (21, 25, "21-25"), (26, 30, "26-30"), (31, 40, "31-40"),
                    (41, 50, "41-50"), (51, 70, "51-70"), (71, 200, "71+")]
FUEL_TYPES = ["Diesel", "Regular"]
BONUS_MALUS_CAP = 150
VEHICLE_POWER_CAP = 9


def driver_age_band(age: int) -> str:
    for low, high, label in DRIVER_AGE_BANDS:
        if low <= age <= high:
            return label
    raise ValueError(f"driver age {age} out of range")


def vehicle_age_band(age: int) -> str:
    return "0" if age < 1 else ("1-10" if age <= 10 else "11+")


def glm_factors(df: pd.DataFrame) -> pd.DataFrame:
    """Raw policy columns (dbt fct_policies names) -> GLM rating factors."""
    return pd.DataFrame({
        "driver_age_band": df["driver_age"].map(driver_age_band),
        "vehicle_age_band": df["vehicle_age"].map(vehicle_age_band),
        "vehicle_power": df["vehicle_power"].clip(upper=VEHICLE_POWER_CAP).astype(int).astype(str),
        "bonus_malus": df["bonus_malus"].clip(upper=BONUS_MALUS_CAP).astype(float),
        "log_density": np.log(df["population_density"].astype(float)),
        "fuel_type": df["fuel_type"].astype(str),
        "vehicle_brand": df["vehicle_brand"].astype(str),
        "region_name": df["region_name"].astype(str),
    }, index=df.index)


def glm_factors_one(profile: dict) -> dict:
    """Same transformation for a single quote (no pandas needed in the API)."""
    return {
        "driver_age_band": driver_age_band(profile["driver_age"]),
        "vehicle_age_band": vehicle_age_band(profile["vehicle_age"]),
        "vehicle_power": str(min(profile["vehicle_power"], VEHICLE_POWER_CAP)),
        "bonus_malus": float(min(profile["bonus_malus"], BONUS_MALUS_CAP)),
        "log_density": math.log(profile["population_density"]),
        "fuel_type": profile["fuel_type"],
        "vehicle_brand": profile["vehicle_brand"],
        "region_name": profile["region_name"],
    }


# GBM: raw numeric features (trees find their own cut points) + one-hot categoricals.
# Native categorical splits were tried first, but SHAP's TreeExplainer does not reproduce
# sklearn's categorical bitset splits (SHAP sums were off by up to 2 on the log scale), so
# the model gets numeric input only and SHAP values are summed back per rating factor.
GBM_NUMERIC = ["driver_age", "vehicle_age", "vehicle_power", "bonus_malus", "log_density", "diesel"]
GBM_CATEGORICAL = ["vehicle_brand", "region_name"]
# Monotone constraints only where the direction is part of the tariff's logic: a higher
# bonus-malus coefficient (worse claims history) must never lower the premium.
GBM_MONOTONIC = {"bonus_malus": 1}


def gbm_features(df: pd.DataFrame, levels: dict[str, list[str]]) -> pd.DataFrame:
    out = pd.DataFrame({
        "driver_age": df["driver_age"].astype(float),
        "vehicle_age": df["vehicle_age"].astype(float),
        "vehicle_power": df["vehicle_power"].astype(float),
        "bonus_malus": df["bonus_malus"].astype(float),
        "log_density": np.log(df["population_density"].astype(float)),
        "diesel": (df["fuel_type"] == "Diesel").astype(float),
    }, index=df.index)
    for col in GBM_CATEGORICAL:
        for level in levels[col]:
            out[f"{col}={level}"] = (df[col] == level).astype(float)
    return out


def gbm_factor_of(column: str) -> str:
    """Map a GBM input column back to its rating factor (for SHAP aggregation)."""
    return {"diesel": "fuel_type"}.get(column, column.split("=")[0])
