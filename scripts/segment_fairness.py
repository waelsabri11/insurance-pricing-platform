"""Proxy check: premium dispersion and actual-vs-expected by segment on the held-out test set.

Reads the dbt mart (marts.fct_policies) and data/processed/policy_predictions.parquet written
by `make train`; writes docs/results/segment_fairness.json and segment_fairness.png.

This is not a fairness audit: freMTPL2 has no gender, nationality or other protected
attribute, so the segments are legitimate rating factors (driver age band, Area, Region)
that could act as proxies. The check shows whether premiums and loss ratios differ
systematically across them.

A/E = actual losses / predicted pure premium (exposure-weighted). Two actuals are reported:
full incurred, and claims capped at the training 99.5th percentile times the large-loss load
(the same convention as the dbt loss-ratio mart), which is far less noisy.
"""

import json
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "results"
SEED, N_BOOT = 42, 300
MODELS = ("glm", "gbm")
SEGMENTS = {"driver_age_band": "driver_age_band", "area": "area_code", "region": "region_name"}
MIN_EXPOSURE = 500.0  # policy-years; smaller segments are listed but flagged


def wquantile(x: np.ndarray, w: np.ndarray, q: float) -> float:
    order = np.argsort(x)
    cum = np.cumsum(w[order]) / w.sum()
    return float(x[order][np.searchsorted(cum, q)])


def lo_ci(row: dict, m: str) -> float:
    return row[m]["ae_capped_loaded_ci95"][0]


def hi_ci(row: dict, m: str) -> float:
    return row[m]["ae_capped_loaded_ci95"][1]


def main() -> None:
    con = duckdb.connect(str(ROOT / "data" / "warehouse.duckdb"), read_only=True)
    pol = con.sql("select policy_id, driver_age_band, area_code, region_name, incurred_amount "
                  "from marts.fct_policies").df()
    con.close()
    pred = pd.read_parquet(ROOT / "data" / "processed" / "policy_predictions.parquet")
    te = pred[pred.split == "test"].merge(pol, on="policy_id", how="left")
    assert te.driver_age_band.notna().all() and len(te) > 0
    w = te["exposure"].to_numpy()
    rng = np.random.default_rng(SEED)

    report = {"test_policies": int(len(te)), "test_exposure_years": round(float(w.sum()), 1),
              "min_exposure_for_reliable_segment": MIN_EXPOSURE, "n_boot": N_BOOT, "premium_unit":
              "pure premium per exposure-year (EUR), no expenses or loading",
              "portfolio": {}, "segments": {}}

    # ---- Dispersion of individual premiums
    for m in MODELS:
        p = te[f"pp_{m}"].to_numpy()
        mean = float((p * w).sum() / w.sum())
        sd = float(np.sqrt((w * (p - mean) ** 2).sum() / w.sum()))
        q = {k: wquantile(p, w, v) for k, v in (("p05", .05), ("p25", .25), ("p50", .5), ("p75", .75),
                                                  ("p95", .95))}
        report["portfolio"][m] = {"mean": mean, "cv": sd / mean, **q, "p95_over_p05": q["p95"] / q["p05"],
                                  "min": float(p.min()), "max": float(p.max())}

    # ---- By segment
    actual = {"full": te["incurred_amount"].to_numpy(), "capped_loaded": te["incurred_capped_loaded"].to_numpy()}
    n = len(te)
    boot_idx = [rng.integers(0, n, n) for _ in range(N_BOOT)]
    for name, col in SEGMENTS.items():
        codes, labels = pd.factorize(te[col], sort=True)
        k = len(labels)
        rows = []
        pol_n = np.bincount(codes, minlength=k)
        expo = np.bincount(codes, weights=w, minlength=k)
        prem = {m: np.bincount(codes, weights=te[f"premium_{m}"].to_numpy(), minlength=k) for m in MODELS}
        act = {a: np.bincount(codes, weights=v, minlength=k) for a, v in actual.items()}
        # bootstrap of A/E on capped_loaded
        boots = {m: np.empty((N_BOOT, k)) for m in MODELS}
        for b, idx in enumerate(boot_idx):
            c = codes[idx]
            a_b = np.bincount(c, weights=actual["capped_loaded"][idx], minlength=k)
            for m in MODELS:
                boots[m][b] = a_b / np.bincount(c, weights=te[f"premium_{m}"].to_numpy()[idx], minlength=k)
        for i, lab in enumerate(labels):
            row = {"segment": str(lab), "policies": int(pol_n[i]), "exposure_years": round(float(expo[i]), 1),
                   "reliable": bool(expo[i] >= MIN_EXPOSURE), "claims_actual_full_eur_per_year":
                   float(act["full"][i] / expo[i])}
            for m in MODELS:
                mean_prem = prem[m][i] / expo[i]
                row[m] = {"mean_premium": float(mean_prem),
                          "premium_index_vs_portfolio": float(mean_prem / report["portfolio"][m]["mean"]),
                          "ae_full": float(act["full"][i] / prem[m][i]),
                          "ae_capped_loaded": float(act["capped_loaded"][i] / prem[m][i]),
                          "ae_capped_loaded_ci95": [float(np.percentile(boots[m][:, i], 2.5)),
                                                    float(np.percentile(boots[m][:, i], 97.5))]}
            rows.append(row)
        rel = [r for r in rows if r["reliable"]]
        summ = {}
        for m in MODELS:
            idxs = np.array([r[m]["premium_index_vs_portfolio"] for r in rel])
            ex = np.array([r["exposure_years"] for r in rel])
            ae = np.array([r[m]["ae_capped_loaded"] for r in rel])
            mu = (ex * idxs).sum() / ex.sum()
            summ[m] = {"premium_index_min": float(idxs.min()), "premium_index_max": float(idxs.max()),
                       "premium_index_exposure_weighted_sd": float(np.sqrt((ex * (idxs - mu) ** 2).sum() / ex.sum())),
                       "ae_capped_min": float(ae.min()), "ae_capped_max": float(ae.max()),
                       "mean_abs_ae_minus_1_exposure_weighted": float((ex * np.abs(ae - 1)).sum() / ex.sum()),
                       "segments_with_ci_excluding_1": [r["segment"] for r in rel if not
                                                        lo_ci(r, m) <= 1 <= hi_ci(r, m)]}
        report["segments"][name] = {"column": col, "n_segments": k, "n_reliable": len(rel),
                                    "summary_reliable_segments": summ, "rows": rows}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "segment_fairness.json").write_text(json.dumps(report, indent=2))

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2), gridspec_kw={"width_ratios": [7, 6, 22]})
    for ax, (name, seg) in zip(axes, report["segments"].items(), strict=True):
        rows = [r for r in seg["rows"] if r["reliable"]]
        x = np.arange(len(rows))
        for m, color, off in (("glm", "#2b6cb0", -.15), ("gbm", "#c05621", .15)):
            y = np.array([r[m]["ae_capped_loaded"] for r in rows])
            lo = y - np.array([r[m]["ae_capped_loaded_ci95"][0] for r in rows])
            hi = np.array([r[m]["ae_capped_loaded_ci95"][1] for r in rows]) - y
            ax.errorbar(x + off, y, yerr=[lo, hi], fmt="o", ms=3, lw=1, color=color, label=m.upper())
        ax.axhline(1, color="grey", ls="--", lw=1)
        ax.set_xticks(x, [r["segment"] for r in rows], rotation=90 if name == "region" else 0, fontsize=7)
        ax.set_title(f"A/E by {name}", fontsize=10)
    axes[0].set_ylabel("actual / predicted (capped claims + large-loss load)")
    axes[0].legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "segment_fairness.png", dpi=130)
    print(json.dumps({k: v for k, v in report.items() if k != "segments"}, indent=1))
    for name, seg in report["segments"].items():
        print(name, seg["n_segments"], seg["n_reliable"], json.dumps(seg["summary_reliable_segments"], indent=1))


if __name__ == "__main__":
    main()
