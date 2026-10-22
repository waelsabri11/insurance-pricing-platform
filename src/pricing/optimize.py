"""Segment-level price optimization on SIMULATED demand.

Maximises expected profit = conversion(p) x (p x (1 - expense ratio) - fixed cost - expected claims)
over one price multiplier per segment (age band x bonus-malus band x density band), applied to the
break-even technical premium, under bounds, a volume floor, a loss-ratio ceiling and a guard for
drivers aged 71+. The demand model is an assumption (pricing.demand), so every conversion, volume
and profit number produced here is simulated.

Run: uv run python -m pricing.optimize    (needs data/processed/policy_predictions.parquet and the warehouse)
"""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.optimize import minimize

from pricing.demand import (
    ASSUMPTIONS,
    DemandParams,
    all_segments,
    bm_band,
    density_band,
    segment_key,
)

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_SEGMENT_FACTORS = ["driver_age_band", "bonus_malus_band", "density_band"]
FORBIDDEN_FACTORS = ["gender", "sex", "nationality", "ethnicity", "religion", "disability"]


@dataclass
class Book:
    """Policy-level arrays (annual figures, weighted by exposure)."""

    w: np.ndarray
    pure: np.ndarray  # GLM expected claims per policy-year (what the optimizer believes)
    pure_gbm: np.ndarray  # GBM expected claims, used only as a cost-robustness check
    tech: np.ndarray  # break-even gross technical premium
    market: np.ndarray  # market-price proxy
    seg: np.ndarray  # segment index per policy
    segments: list[str]
    flat_pure: float = 0.0  # flat-rate pure premium (market-proxy input)


def load_book(a: dict = ASSUMPTIONS) -> Book:
    db = Path(os.environ.get("DUCKDB_PATH", ROOT / "data" / "warehouse.duckdb"))
    con = duckdb.connect(str(db), read_only=True)
    pol = con.sql("select policy_id, driver_age, bonus_malus, population_density from marts.fct_policies").df()
    con.close()
    pred = pd.read_parquet(ROOT / "data" / "processed" / "policy_predictions.parquet")
    df = pol.merge(pred, on="policy_id", validate="1:1")
    from pricing.rating import driver_age_band

    keys = [
        segment_key(driver_age_band(int(x)), bm_band(b), density_band(d))
        for x, b, d in zip(df["driver_age"], df["bonus_malus"], df["population_density"], strict=True)
    ]
    segments = all_segments()
    idx = {s: i for i, s in enumerate(segments)}
    tech = (df["pp_glm"].to_numpy() + a["fixed_cost_eur"]) / (1 - a["expense_ratio"])
    blend = a["market_blend_flat"] * df["pp_flat"].to_numpy() + (1 - a["market_blend_flat"]) * df["pp_glm"].to_numpy()
    market = (blend + a["fixed_cost_eur"]) / (1 - a["expense_ratio"]) * (1 + a["market_offset"])
    return Book(
        df["exposure"].to_numpy(),
        df["pp_glm"].to_numpy(),
        df["pp_gbm"].to_numpy(),
        tech,
        market,
        np.array([idx[k] for k in keys]),
        segments,
        float(df["pp_flat"].iloc[0]),
    )


def _conv(book: Book, price: np.ndarray, d: DemandParams) -> np.ndarray:
    z0 = np.log(d.base_conversion / (1 - d.base_conversion))
    return 1 / (1 + np.exp(-(z0 - d.price_sensitivity * np.log(price / book.market))))


def evaluate(
    book: Book, price: np.ndarray, d: DemandParams, a: dict = ASSUMPTIONS, cost: np.ndarray | None = None
) -> dict:
    """Portfolio totals (per year, exposure-weighted) for given per-policy prices."""
    cost = book.pure if cost is None else cost
    c = _conv(book, price, d)
    wc = book.w * c
    profit = float((wc * (price * (1 - a["expense_ratio"]) - a["fixed_cost_eur"] - cost)).sum())
    premium = float((wc * price).sum())
    return {
        "volume": float(wc.sum()),
        "premium": premium,
        "expected_claims": float((wc * cost).sum()),
        "profit": profit,
        "loss_ratio": float((wc * cost).sum() / premium),
        "mean_conversion": float(wc.sum() / book.w.sum()),
    }


def _multiplier_vector(book: Book, m_seg: np.ndarray) -> np.ndarray:
    return book.tech * m_seg[book.seg]


def optimize_segments(
    book: Book,
    d: DemandParams,
    a: dict = ASSUMPTIONS,
    min_volume_ratio: float | None = None,
    baseline: dict | None = None,
) -> np.ndarray:
    """SLSQP over one multiplier per segment; returns the multiplier vector."""
    n = len(book.segments)
    base = baseline or evaluate(book, book.tech * (1 + a["flat_loading"]), d, a)
    vol_floor = (a["min_volume_vs_baseline"] if min_volume_ratio is None else min_volume_ratio) * base["volume"]
    e, fixed = a["expense_ratio"], a["fixed_cost_eur"]
    z0 = np.log(d.base_conversion / (1 - d.base_conversion))
    scale = abs(base["profit"])

    def parts(m):
        p = book.tech * m[book.seg]
        c = 1 / (1 + np.exp(-(z0 - d.price_sensitivity * np.log(p / book.market))))
        dc = -d.price_sensitivity * c * (1 - c) / m[book.seg]  # d conv / d m
        return p, c, dc

    def agg(x):
        return np.bincount(book.seg, weights=x, minlength=n)

    def neg_profit(m):
        p, c, _ = parts(m)
        return -float((book.w * c * (p * (1 - e) - fixed - book.pure)).sum()) / scale

    def neg_profit_jac(m):
        p, c, dc = parts(m)
        g = book.w * (dc * (p * (1 - e) - fixed - book.pure) + c * book.tech * (1 - e))
        return -agg(g) / scale

    def vol_con(m):
        return float((book.w * parts(m)[1]).sum()) / base["volume"] - vol_floor / base["volume"]

    def vol_jac(m):
        return agg(book.w * parts(m)[2]) / base["volume"]

    def lr_con(m):  # max_loss_ratio * premium - claims >= 0
        p, c, _ = parts(m)
        return float((book.w * c * (a["max_loss_ratio"] * p - book.pure)).sum()) / base["premium"]

    def lr_jac(m):
        p, c, dc = parts(m)
        return (
            agg(book.w * (dc * (a["max_loss_ratio"] * p - book.pure) + c * a["max_loss_ratio"] * book.tech))
            / base["premium"]
        )

    has_policies = np.bincount(book.seg, minlength=n) > 0
    senior = np.array([s.startswith("71+") for s in book.segments])
    ub = np.where(senior, a["senior_multiplier_max"], a["multiplier_max"])
    lb = np.full(n, a["multiplier_min"])
    ub = np.where(has_policies, ub, 1.0)
    lb = np.where(has_policies, lb, 1.0)
    res = minimize(
        neg_profit,
        np.clip(np.full(n, 1 + a["flat_loading"]), lb, ub),
        jac=neg_profit_jac,
        method="SLSQP",
        bounds=list(zip(lb, ub, strict=True)),
        constraints=[{"type": "ineq", "fun": vol_con, "jac": vol_jac}, {"type": "ineq", "fun": lr_con, "jac": lr_jac}],
        options={"maxiter": 300, "ftol": 1e-10},
    )
    if not res.success:
        raise RuntimeError(f"optimizer failed: {res.message}")
    return res.x


def best_flat_multiplier(book: Book, d: DemandParams, a: dict, baseline: dict) -> float:
    """Best single multiplier for the whole book under the same volume and loss-ratio constraints."""
    best, best_profit = None, -np.inf
    for m in np.linspace(a["multiplier_min"], a["multiplier_max"], 101):
        r = evaluate(book, book.tech * m, d, a)
        if (
            r["volume"] >= a["min_volume_vs_baseline"] * baseline["volume"]
            and r["loss_ratio"] <= a["max_loss_ratio"]
            and r["profit"] > best_profit
        ):
            best, best_profit = m, r["profit"]
    if best is None:
        raise RuntimeError("no feasible flat multiplier")
    return float(best)


def compare(book: Book, d: DemandParams, a: dict, m_seg: np.ndarray, m_flat: float) -> dict:
    base_price = book.tech * (1 + a["flat_loading"])
    opt_price = _multiplier_vector(book, m_seg)
    out = {}
    for name, price in [
        ("flat_loading", base_price),
        ("best_flat_multiplier", book.tech * m_flat),
        ("optimized_segments", opt_price),
    ]:
        out[name] = evaluate(book, price, d, a)
        out[name]["profit_if_gbm_costs"] = evaluate(book, price, d, a, cost=book.pure_gbm)["profit"]
    return out


def price_change_distribution(book: Book, a: dict, m_seg: np.ndarray) -> dict:
    change = _multiplier_vector(book, m_seg) / (book.tech * (1 + a["flat_loading"])) - 1
    order = np.argsort(change)
    cw = np.cumsum(book.w[order]) / book.w.sum()
    q = {
        f"p{int(p * 100)}": float(change[order][np.searchsorted(cw, p)])
        for p in (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)
    }
    return {
        "vs": "flat_loading price",
        "exposure_weighted_quantiles": q,
        "share_of_exposure_cheaper": float(book.w[change < -0.005].sum() / book.w.sum()),
        "share_of_exposure_dearer": float(book.w[change > 0.005].sum() / book.w.sum()),
    }


def fairness_report(book: Book, df_seg: pd.DataFrame) -> dict:
    """Exposure-weighted mean multiplier per allowed dimension, and the largest gap between levels."""
    out = {
        "segment_factors_used": ALLOWED_SEGMENT_FACTORS,
        "forbidden_factors_present": [],
        "max_multiplier": float(df_seg["multiplier"].max()),
        "min_multiplier": float(df_seg["multiplier"].min()),
    }
    for dim in ("age_band", "bonus_malus_band", "density_band"):
        g = (
            df_seg[df_seg.exposure > 0]
            .groupby(dim)
            .apply(lambda x: np.average(x["multiplier"], weights=x["exposure"]), include_groups=False)
        )
        out[f"mean_multiplier_by_{dim}"] = {k: float(v) for k, v in g.items()}
        out[f"max_gap_{dim}"] = float(g.max() - g.min())
    return out


def run() -> dict:
    t0 = time.time()
    a = ASSUMPTIONS
    book = load_book(a)
    base_d = DemandParams()
    baseline = evaluate(book, book.tech * (1 + a["flat_loading"]), base_d, a)
    m_seg = optimize_segments(book, base_d, a, baseline=baseline)
    m_flat = best_flat_multiplier(book, base_d, a, baseline)
    comparison = compare(book, base_d, a, m_seg, m_flat)
    opt_price = _multiplier_vector(book, m_seg)
    conv_p = _conv(book, opt_price, base_d)

    seg_df = pd.DataFrame({"segment": book.segments, "multiplier": m_seg})
    parts = seg_df["segment"].str.split("|", expand=True)
    seg_df["age_band"], seg_df["bonus_malus_band"], seg_df["density_band"] = parts[0], parts[1], parts[2]
    seg_df["exposure"] = np.bincount(book.seg, weights=book.w, minlength=len(book.segments))
    seg_df["n_policies"] = np.bincount(book.seg, minlength=len(book.segments))
    seg_df["mean_technical_premium"] = np.bincount(
        book.seg, weights=book.w * book.tech, minlength=len(book.segments)
    ) / seg_df["exposure"].replace(0, np.nan)
    seg_df["mean_conversion_at_optimum"] = np.bincount(
        book.seg, weights=book.w * conv_p, minlength=len(book.segments)
    ) / seg_df["exposure"].replace(0, np.nan)
    seg_df["mean_conversion_flat_loading"] = np.bincount(
        book.seg,
        weights=book.w * _conv(book, book.tech * (1 + a["flat_loading"]), base_d),
        minlength=len(book.segments),
    ) / seg_df["exposure"].replace(0, np.nan)

    # Sensitivity: re-optimise under each demand scenario, and test the base-case multipliers against it.
    rows = []
    scenarios = [(b, c0, a["market_offset"]) for b in (2.0, 3.0, 4.0, 6.0, 8.0) for c0 in (0.10, 0.15, 0.25)]
    scenarios += [(4.0, 0.15, off) for off in (0.0, 0.10)]
    for b, c0, off in scenarios:
        a_s = {**a, "market_offset": off}
        book_s = load_market(book, a_s)
        d = DemandParams(c0, b)
        base_s = evaluate(book_s, book_s.tech * (1 + a["flat_loading"]), d, a_s)
        m_s = optimize_segments(book_s, d, a_s, baseline=base_s)
        flat_s = best_flat_multiplier(book_s, d, a_s, base_s)
        re = evaluate(book_s, _multiplier_vector(book_s, m_s), d, a_s)
        stale = evaluate(book_s, _multiplier_vector(book_s, m_seg), d, a_s)
        fl = evaluate(book_s, book_s.tech * flat_s, d, a_s)
        rows.append(
            {
                "price_sensitivity": b,
                "base_conversion": c0,
                "market_offset": off,
                "elasticity_at_market_price": -b * (1 - c0),
                "baseline_profit": base_s["profit"],
                "baseline_volume": base_s["volume"],
                "best_flat_profit": fl["profit"],
                "best_flat_multiplier": flat_s,
                "reoptimized_profit": re["profit"],
                "reoptimized_volume": re["volume"],
                "reoptimized_loss_ratio": re["loss_ratio"],
                "reoptimized_uplift_vs_baseline": re["profit"] / base_s["profit"] - 1,
                "base_multipliers_profit": stale["profit"],
                "base_multipliers_volume_vs_baseline": stale["volume"] / base_s["volume"],
                "base_multipliers_loss_ratio": stale["loss_ratio"],
                "base_multipliers_uplift_vs_baseline": stale["profit"] / base_s["profit"] - 1,
            }
        )
        print(f"scenario b={b} c0={c0} off={off}: uplift {rows[-1]['reoptimized_uplift_vs_baseline']:+.1%}", flush=True)
    sens = pd.DataFrame(rows)

    # Volume-floor frontier at base demand.
    frontier = []
    for floor in (0.80, 0.85, 0.90, 0.95, 1.00):
        m_f = optimize_segments(book, base_d, a, min_volume_ratio=floor, baseline=baseline)
        r = evaluate(book, _multiplier_vector(book, m_f), base_d, a)
        frontier.append(
            {
                "min_volume_vs_baseline": floor,
                "profit": r["profit"],
                "volume": r["volume"],
                "loss_ratio": r["loss_ratio"],
                "profit_uplift_vs_baseline": r["profit"] / baseline["profit"] - 1,
            }
        )
    frontier_df = pd.DataFrame(frontier)

    summary = {
        "SIMULATED": "Demand is an assumption, not estimated from freMTPL2 (no quotes or conversions in the data). "
        "Conversion, volume and profit below are simulated.",
        "assumptions": a,
        "demand_params": base_d.as_dict(),
        "book": {
            "policies": int(len(book.w)),
            "policy_years": float(book.w.sum()),
            "segments": len(book.segments),
            "non_empty_segments": int((seg_df.n_policies > 0).sum()),
        },
        "comparison_annual_totals": comparison,
        "uplift_vs_flat_loading": {
            k: comparison[k]["profit"] / comparison["flat_loading"]["profit"] - 1
            for k in ("best_flat_multiplier", "optimized_segments")
        },
        "best_flat_multiplier": m_flat,
        "price_change_vs_flat_loading": price_change_distribution(book, a, m_seg),
        "fairness": fairness_report(book, seg_df),
        "sensitivity_uplift_range": {
            "reoptimized": [
                float(sens.reoptimized_uplift_vs_baseline.min()),
                float(sens.reoptimized_uplift_vs_baseline.max()),
            ],
            "base_multipliers_under_wrong_demand": [
                float(sens.base_multipliers_uplift_vs_baseline.min()),
                float(sens.base_multipliers_uplift_vs_baseline.max()),
            ],
        },
        "runtime_note": "all numbers generated by `python -m pricing.optimize`",
    }
    res = ROOT / "results"
    (res / "figures").mkdir(exist_ok=True)
    (res / "price_optimization.json").write_text(json.dumps(summary, indent=2, default=float))
    seg_df.round(6).to_csv(res / "price_optimization_segments.csv", index=False)
    sens.round(6).to_csv(res / "price_optimization_sensitivity.csv", index=False)
    frontier_df.round(6).to_csv(res / "price_optimization_volume_frontier.csv", index=False)
    plot(book, a, m_seg, sens, res / "figures" / "price_optimization.png")

    artifact = {
        "SIMULATED": summary["SIMULATED"],
        "assumptions": a,
        "demand_params": base_d.as_dict(),
        "flat_pure_premium": book.flat_pure,
        "sensitivity_scenarios": [
            {"label": f"sensitivity {b:g}", "base_conversion": 0.15, "price_sensitivity": b} for b in (2.0, 4.0, 6.0)
        ],
        "segment_factors": ALLOWED_SEGMENT_FACTORS,
        "segments": {
            r.segment: {"multiplier": round(float(r.multiplier), 4), "n_policies": int(r.n_policies)}
            for r in seg_df.itertuples()
        },
    }
    (ROOT / "models" / "price_optimization.json").write_text(json.dumps(artifact, indent=1))
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "comparison_annual_totals",
                    "uplift_vs_flat_loading",
                    "best_flat_multiplier",
                    "sensitivity_uplift_range",
                )
            },
            indent=2,
        )
    )
    print(f"done in {time.time() - t0:.1f}s")
    return summary


def load_market(book: Book, a_s: dict) -> Book:
    """Same book with the market proxy recomputed for another market offset (market = tech(blend) x (1+offset))."""
    old = ASSUMPTIONS["market_offset"]
    return Book(
        book.w,
        book.pure,
        book.pure_gbm,
        book.tech,
        book.market / (1 + old) * (1 + a_s["market_offset"]),
        book.seg,
        book.segments,
        book.flat_pure,
    )


def plot(book: Book, a: dict, m_seg: np.ndarray, sens: pd.DataFrame, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    change = _multiplier_vector(book, m_seg) / (book.tech * (1 + a["flat_loading"])) - 1
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ax[0].hist(change * 100, bins=60, weights=book.w, color="#4C78A8")
    ax[0].set(
        xlabel="optimized price vs flat-loading price (%)",
        ylabel="policy-years",
        title="Price change distribution (simulated demand)",
    )
    piv = (
        sens[(sens.market_offset == a["market_offset"])].pivot(
            index="price_sensitivity", columns="base_conversion", values="reoptimized_uplift_vs_baseline"
        )
        * 100
    )
    for c in piv.columns:
        ax[1].plot(piv.index, piv[c], marker="o", label=f"base conversion {c:.0%}")
    ax[1].set(
        xlabel="price sensitivity b (assumed)",
        ylabel="profit uplift vs flat loading (%)",
        title="Sensitivity to demand assumptions (simulated)",
    )
    ax[1].legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    run()
