import math

import numpy as np
import pytest

from pricing.demand import ASSUMPTIONS, DemandParams, all_segments, conversion, market_price, technical_premium
from pricing.optimize import Book, best_flat_multiplier, evaluate, optimize_segments


def test_conversion_at_market_price_is_base_and_decreasing():
    d = DemandParams(0.2, 4.0)
    assert conversion(1.0, d) == pytest.approx(0.2)
    assert conversion(1.1, d) < conversion(1.0, d) < conversion(0.9, d)


def test_elasticity_matches_definition():
    d = DemandParams(0.15, 4.0)
    h = 1e-6
    numeric = (math.log(conversion(1 + h, d)) - math.log(conversion(1, d))) / math.log(1 + h)
    assert numeric == pytest.approx(-4.0 * (1 - 0.15), rel=1e-4)


def test_technical_premium_breaks_even():
    pure = 150.0
    tp = technical_premium(pure)
    assert tp * (1 - ASSUMPTIONS["expense_ratio"]) - ASSUMPTIONS["fixed_cost_eur"] == pytest.approx(pure)
    assert market_price(pure, pure) == pytest.approx(tp * (1 + ASSUMPTIONS["market_offset"]))


def toy_book(n=4000, seed=0):
    rng = np.random.default_rng(seed)
    segments = all_segments()
    pure = rng.gamma(4, 40, n)
    flat = pure.mean()
    tech = (pure + ASSUMPTIONS["fixed_cost_eur"]) / (1 - ASSUMPTIONS["expense_ratio"])
    blend = 0.5 * flat + 0.5 * pure
    market = (blend + ASSUMPTIONS["fixed_cost_eur"]) / (1 - ASSUMPTIONS["expense_ratio"]) * 1.05
    # first segments of the list get all the policies; others stay empty
    return Book(rng.uniform(0.3, 1, n), pure, pure * 1.05, tech, market, rng.integers(0, 12, n), segments, flat)


def test_optimizer_respects_constraints_and_beats_baseline():
    book, d, a = toy_book(), DemandParams(), ASSUMPTIONS
    base = evaluate(book, book.tech * (1 + a["flat_loading"]), d, a)
    m = optimize_segments(book, d, a, baseline=base)
    assert m.min() >= a["multiplier_min"] - 1e-9 and m.max() <= a["multiplier_max"] + 1e-9
    res = evaluate(book, book.tech * m[book.seg], d, a)
    assert res["volume"] >= a["min_volume_vs_baseline"] * base["volume"] - 1e-6 * base["volume"]
    assert res["loss_ratio"] <= a["max_loss_ratio"] + 1e-6
    assert res["profit"] >= base["profit"]
    # seniors (71+) are capped; empty segments stay at 1
    for s, mult in zip(book.segments, m, strict=True):
        if s.startswith("71+"):
            assert mult <= a["senior_multiplier_max"] + 1e-9
    assert np.allclose(m[np.bincount(book.seg, minlength=len(m)) == 0], 1.0)


def test_segment_optimum_at_least_best_flat():
    book, d, a = toy_book(), DemandParams(), ASSUMPTIONS
    base = evaluate(book, book.tech * (1 + a["flat_loading"]), d, a)
    m = optimize_segments(book, d, a, baseline=base)
    flat = best_flat_multiplier(book, d, a, base)
    seg_profit = evaluate(book, book.tech * m[book.seg], d, a)["profit"]
    assert seg_profit >= evaluate(book, book.tech * flat, d, a)["profit"] - 1
