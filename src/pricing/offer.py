"""Offer price for one quote from the optimized segment multipliers (pure Python, no numpy).

Everything about conversion and expected profit here is SIMULATED (see pricing.demand).
"""

from pricing.demand import (
    DemandParams,
    bm_band,
    conversion,
    density_band,
    expected_profit,
    market_price,
    segment_key,
    technical_premium,
)
from pricing.rating import driver_age_band

CURVE_STEP = 0.05


def offer(optimization: dict, profile: dict, annual_pure_premium: float, exposure: float = 1.0) -> dict:
    a = optimization["assumptions"]
    demand = DemandParams(**optimization["demand_params"])
    segment = segment_key(driver_age_band(profile["driver_age"]), bm_band(profile["bonus_malus"]),
                          density_band(profile["population_density"]))
    seg = optimization["segments"][segment]
    tech = technical_premium(annual_pure_premium, a)
    market = market_price(annual_pure_premium, optimization["flat_pure_premium"], a)
    multiplier = seg["multiplier"]
    price = tech * multiplier
    conv = conversion(price / market, demand)

    lo, hi = a["multiplier_min"], a["multiplier_max"]
    n_steps = round((hi - lo) / CURVE_STEP)
    multipliers = [round(lo + i * CURVE_STEP, 4) for i in range(n_steps + 1)]
    curves = []
    others = [s for s in optimization["sensitivity_scenarios"] if s["price_sensitivity"] != demand.price_sensitivity]
    for sc in [{"label": "base assumption", **demand.as_dict()}, *others]:
        d = DemandParams(sc["base_conversion"], sc["price_sensitivity"])
        points = []
        for m in multipliers:
            c = conversion(tech * m / market, d)
            points.append({"multiplier": m, "price": tech * m, "conversion": c,
                           "expected_profit": expected_profit(tech * m, annual_pure_premium, c, a)})
        curves.append({"label": sc["label"], "price_sensitivity": sc["price_sensitivity"],
                       "base_conversion": sc["base_conversion"], "points": points})
    return {
        "simulated": True,
        "disclaimer": "Conversion and profit come from an assumed demand model, not from observed quotes.",
        "segment": segment,
        "technical_premium": tech * exposure,
        "annual_technical_premium": tech,
        "multiplier": multiplier,
        "price": price * exposure,
        "annual_price": price,
        "market_price_proxy": market * exposure,
        "expected_conversion": conv,
        "expected_profit_per_quote": expected_profit(price, annual_pure_premium, conv, a) * exposure,
        "baseline_flat_loading_price": tech * (1 + a["flat_loading"]) * exposure,
        "sensitivity": curves,
    }
