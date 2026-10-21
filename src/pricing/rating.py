"""Pure-Python rating of a single quote from the GLM tariff JSON.

No numpy/pandas/statsmodels here, so the quote API image only needs FastAPI. Batch feature
preparation for training lives in pricing.features and reuses the band rules below.
"""

import math

DRIVER_AGE_BANDS = [(18, 20, "18-20"), (21, 25, "21-25"), (26, 30, "26-30"), (31, 40, "31-40"),
                    (41, 50, "41-50"), (51, 70, "51-70"), (71, 200, "71+")]
BONUS_MALUS_CAP = 150
VEHICLE_POWER_CAP = 9


def driver_age_band(age: int) -> str:
    for low, high, label in DRIVER_AGE_BANDS:
        if low <= age <= high:
            return label
    raise ValueError(f"driver age {age} out of range")


def vehicle_age_band(age: int) -> str:
    return "0" if age < 1 else ("1-10" if age <= 10 else "11+")


def rating_factors(profile: dict) -> dict:
    """Driver/vehicle profile -> GLM rating factors (same rules as training)."""
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


def relativities(model: dict, factors: dict) -> tuple[float, dict[str, float]]:
    """Base value exp(intercept) and the multiplicative relativity of each tariff factor."""
    rel = {}
    for name, f in model["factors"].items():
        x = factors[name]
        if f["type"] == "continuous":
            rel[name] = math.exp(f["coef"] * (x - f["center"]))
        else:
            if x not in f["levels"]:
                raise KeyError(f"unknown level {x!r} for {name}")
            rel[name] = math.exp(f["levels"][x]["coef"])
    return math.exp(model["intercept"]), rel


def quote(tariff: dict, profile: dict, exposure: float = 1.0) -> dict:
    """Pure premium = frequency x severity x large-loss load, with a per-factor breakdown."""
    factors = rating_factors(profile)
    base_f, rel_f = relativities(tariff["frequency"], factors)
    base_s, rel_s = relativities(tariff["severity"], factors)
    frequency = base_f * math.prod(rel_f.values())
    severity = base_s * math.prod(rel_s.values())
    load = tariff["large_loss_load"]
    breakdown = [
        {"factor": name, "rated_value": factors[name],
         "frequency_relativity": rel_f.get(name, 1.0), "severity_relativity": rel_s.get(name, 1.0),
         "combined_relativity": rel_f.get(name, 1.0) * rel_s.get(name, 1.0)}
        for name in factors
    ]
    return {
        "pure_premium": frequency * severity * load * exposure,
        "annual_pure_premium": frequency * severity * load,
        "expected_claim_frequency": frequency,
        "expected_claim_severity": severity,
        "base_premium": base_f * base_s * load,
        "large_loss_load": load,
        "breakdown": breakdown,
    }
