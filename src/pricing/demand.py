"""SIMULATED demand layer and segment definitions (pure Python, usable by the API image).

freMTPL2 contains no quotes, conversions or renewals, so nothing here is estimated from data.
Conversion is a logistic function of the price relative to a market-price proxy, with
parameters that are explicit assumptions (see ASSUMPTIONS). Every conversion, volume and
profit figure derived from it is a simulation, never an observation.
"""

import math
from dataclasses import asdict, dataclass

# Business assumptions (not estimated from data).
ASSUMPTIONS = {
    "expense_ratio": 0.25,  # variable expenses + commission, share of the gross price
    "fixed_cost_eur": 20.0,  # acquisition/admin cost per policy-year
    "flat_loading": 0.10,  # baseline: technical premium x (1 + flat_loading)
    "multiplier_min": 0.80,
    "multiplier_max": 1.30,
    "senior_multiplier_max": 1.10,  # guard: cap for drivers aged 71+ (assumed vulnerable-customer rule)
    "min_volume_vs_baseline": 0.90,  # expected conversions >= 90% of the flat-loading baseline
    "max_loss_ratio": 0.70,  # expected claims / premium of converted policies
    "market_offset": 0.05,  # market price = 5% above its own break-even
    "market_blend_flat": 0.5,  # market prices less finely than us: 50% flat rate, 50% GLM
}


@dataclass(frozen=True)
class DemandParams:
    """conversion = sigmoid(logit(base_conversion) - price_sensitivity * ln(price / market_price))

    base_conversion: conversion probability when our price equals the market proxy.
    price_sensitivity: logit slope per unit of ln-price. Price elasticity of conversion is
    -price_sensitivity * (1 - conversion), e.g. 4 at 15% conversion gives about -3.4.
    """

    base_conversion: float = 0.15
    price_sensitivity: float = 4.0

    def as_dict(self) -> dict:
        return asdict(self)


def conversion(price_ratio: float, p: DemandParams) -> float:
    """Simulated conversion probability at price / market_price = price_ratio."""
    base = math.log(p.base_conversion / (1 - p.base_conversion))
    z = base - p.price_sensitivity * math.log(price_ratio)
    return 1 / (1 + math.exp(-z))


def technical_premium(pure_premium: float, a: dict = ASSUMPTIONS) -> float:
    """Break-even gross price: covers expected claims, fixed cost and proportional expenses."""
    return (pure_premium + a["fixed_cost_eur"]) / (1 - a["expense_ratio"])


def market_price(pure_premium: float, flat_pure_premium: float, a: dict = ASSUMPTIONS) -> float:
    """Market-price proxy: a less segmented tariff (blend of flat rate and GLM) plus an offset."""
    w = a["market_blend_flat"]
    blend = w * flat_pure_premium + (1 - w) * pure_premium
    return technical_premium(blend, a) * (1 + a["market_offset"])


def expected_profit(price: float, pure_premium: float, conv: float, a: dict = ASSUMPTIONS) -> float:
    """Expected profit per quote = conversion x (price net of expenses - expected claims)."""
    return conv * (price * (1 - a["expense_ratio"]) - a["fixed_cost_eur"] - pure_premium)


# Segments: only legitimate rating factors from the tariff (no gender; nothing protected).
AGE_BANDS = ["18-20", "21-25", "26-30", "31-40", "41-50", "51-70", "71+"]
BM_BANDS = ["50", "51-75", "76-100", "101+"]
DENSITY_BANDS = ["<200", "200-2000", ">2000"]


def bm_band(bonus_malus: float) -> str:
    return "50" if bonus_malus <= 50 else "51-75" if bonus_malus <= 75 else "76-100" if bonus_malus <= 100 else "101+"


def density_band(density: float) -> str:
    return "<200" if density < 200 else "200-2000" if density <= 2000 else ">2000"


def segment_key(age_band: str, bm: str, dens: str) -> str:
    return f"{age_band}|{bm}|{dens}"


def all_segments() -> list[str]:
    return [segment_key(a, b, d) for a in AGE_BANDS for b in BM_BANDS for d in DENSITY_BANDS]
