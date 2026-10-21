"""Fit frequency/severity GLMs and GBMs on the dbt marts, evaluate on a held-out split.

Outputs
  models/tariff.json                    GLM tariff used by the quote API (committed, a few KB)
  models/gbm_*.joblib                   fitted GBMs (git-ignored)
  data/processed/policy_predictions.parquet   per-policy premiums, read back by dbt
  results/                              metrics, relativities, lift tables, figures

Environment: DUCKDB_PATH (default data/warehouse.duckdb), PRICING_SAMPLE_FRAC (default 1.0;
CI uses a sample to stay fast).
"""

import json
import os
import time
from pathlib import Path

import duckdb
import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.api as sm  # noqa: E402
from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: E402

from pricing import features, glm, metrics  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SEED = 42
TEST_SHARE = 0.2
CLAIM_COUNT_CAP = 4          # a handful of policies report 5-16 claims; standard freMTPL2 cleaning
LARGE_LOSS_QUANTILE = 0.995  # individual claims above this are capped for severity modelling

CATEGORICAL = ["driver_age_band", "vehicle_age_band", "vehicle_power", "fuel_type", "vehicle_brand", "region_name"]
CONTINUOUS = ["bonus_malus", "log_density"]


def load(db_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    con = duckdb.connect(str(db_path), read_only=True)
    policies = con.sql("select * from marts.fct_policies order by policy_id").df()
    claims = con.sql("select policy_id, claim_amount from marts.fct_claims").df()
    con.close()
    return policies, claims


def gbm(loss: str, min_samples_leaf: int, monotonic: dict) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss=loss, learning_rate=0.05, max_iter=2000, max_leaf_nodes=31,
        min_samples_leaf=min_samples_leaf, l2_regularization=1.0, early_stopping=True,
        validation_fraction=0.1, n_iter_no_change=50,
        monotonic_cst=monotonic, random_state=SEED)


def main() -> None:
    t0 = time.time()
    db_path = Path(os.environ.get("DUCKDB_PATH", ROOT / "data" / "warehouse.duckdb"))
    sample_frac = float(os.environ.get("PRICING_SAMPLE_FRAC", "1.0"))
    results, models_dir = ROOT / "results", ROOT / "models"
    (results / "figures").mkdir(parents=True, exist_ok=True)

    df, claims = load(db_path)
    if sample_frac < 1.0:
        df = df.sample(frac=sample_frac, random_state=SEED).sort_values("policy_id").reset_index(drop=True)
        claims = claims[claims.policy_id.isin(df.policy_id)]

    rng = np.random.default_rng(SEED)
    df["split"] = np.where(rng.random(len(df)) < TEST_SHARE, "test", "train")
    df["exposure"] = df["exposure_years"].clip(upper=1.0)
    df["n_claims"] = df["claim_count"].clip(upper=CLAIM_COUNT_CAP)
    train = df["split"] == "train"

    # Large losses: cap individual claims at the train-set quantile, model the capped severity,
    # and spread the excess back over everyone as a flat loading so the tariff stays balanced.
    claims = claims.merge(df[["policy_id", "split"]], on="policy_id")
    cap = float(claims.loc[claims.split == "train", "claim_amount"].quantile(LARGE_LOSS_QUANTILE))
    claims["capped"] = claims["claim_amount"].clip(upper=cap)
    capped = claims.groupby("policy_id")["capped"].sum()
    df["incurred_capped"] = df["policy_id"].map(capped).fillna(0.0)
    large_loss_load = df.loc[train, "incurred_amount"].sum() / df.loc[train, "incurred_capped"].sum()

    fac = features.glm_factors(df)[CATEGORICAL + CONTINUOUS]
    centers = {"bonus_malus": 50.0, "log_density": round(float(np.log(df["population_density"].median())), 2)}

    # ---- Frequency GLM: Poisson, log link, offset log(exposure)
    spec_f = glm.make_spec(fac[train], df.loc[train, "exposure"], CATEGORICAL, centers)
    res_f, _ = glm.fit(fac[train], df.loc[train, "n_claims"].to_numpy(), sm.families.Poisson(), spec_f,
                       offset=np.log(df.loc[train, "exposure"].to_numpy()))
    tariff_f = glm.to_tariff(res_f, spec_f)

    # ---- Severity GLM: Gamma, log link, on average capped claim per policy weighted by claim count
    has_claim = df["claim_count"] > 0
    sev_train = train & has_claim
    avg_sev = df["incurred_capped"] / df["claim_count"].where(has_claim)
    # Only ~21k claims carry the severity signal, so factors are selected by backward
    # elimination on training-set BIC (the test set is never used for selection).
    full_spec_s = glm.make_spec(fac[sev_train], df.loc[sev_train, "claim_count"], CATEGORICAL, centers)

    def fit_sev(spec):
        return glm.fit(fac[sev_train], avg_sev[sev_train].to_numpy(), sm.families.Gamma(sm.families.links.Log()),
                       spec, weights=df.loc[sev_train, "claim_count"].to_numpy(float))[0]

    spec_s, res_s = dict(full_spec_s), fit_sev(full_spec_s)
    while spec_s:
        trials = {f: fit_sev({k: v for k, v in spec_s.items() if k != f}) for f in spec_s}
        drop, best = min(trials.items(), key=lambda kv: kv[1].bic_llf)
        if best.bic_llf >= res_s.bic_llf:
            break
        spec_s, res_s = {k: v for k, v in spec_s.items() if k != drop}, best
    tariff_s = glm.to_tariff(res_s, spec_s)

    df["freq_glm"] = glm.predict(tariff_f, fac)
    df["sev_glm"] = glm.predict(tariff_s, fac)

    # ---- GBMs: same targets, raw features, monotone in bonus-malus
    gbm_levels = {c: sorted(df[c].astype(str).unique().tolist()) for c in features.GBM_CATEGORICAL}
    X = features.gbm_features(df, gbm_levels)
    mono = [features.GBM_MONOTONIC.get(c, 0) for c in X.columns]
    gbm_f = gbm("poisson", 500, mono).fit(
        X[train], (df.loc[train, "n_claims"] / df.loc[train, "exposure"]).to_numpy(),
        sample_weight=df.loc[train, "exposure"].to_numpy())
    gbm_s = gbm("gamma", 200, mono).fit(
        X[sev_train], avg_sev[sev_train].to_numpy(), sample_weight=df.loc[sev_train, "claim_count"].to_numpy())
    df["freq_gbm"] = gbm_f.predict(X)
    df["sev_gbm"] = gbm_s.predict(X)

    # Balance property: rescale each component so its training-set total matches observed
    # (Poisson GLM with intercept already satisfies it; the Gamma log-link GLM and the
    # early-stopped GBMs do not). For the GLM the factor is folded into the intercept.
    balance = {}
    for m in ("glm", "gbm"):
        balance[f"freq_{m}"] = df.loc[train, "n_claims"].sum() / (
            df.loc[train, f"freq_{m}"] * df.loc[train, "exposure"]).sum()
        balance[f"sev_{m}"] = df.loc[sev_train, "incurred_capped"].sum() / (
            df.loc[sev_train, f"sev_{m}"] * df.loc[sev_train, "claim_count"]).sum()
        df[f"freq_{m}"] *= balance[f"freq_{m}"]
        df[f"sev_{m}"] *= balance[f"sev_{m}"]
    tariff_f["intercept"] += float(np.log(balance["freq_glm"]))
    tariff_s["intercept"] += float(np.log(balance["sev_glm"]))

    for m in ("glm", "gbm"):
        df[f"pp_{m}"] = df[f"freq_{m}"] * df[f"sev_{m}"] * large_loss_load
    flat_pp = df.loc[train, "incurred_amount"].sum() / df.loc[train, "exposure"].sum()
    df["pp_flat"] = flat_pp

    # ---- Evaluation on the test split
    te = df[df["split"] == "test"]
    sev_te = te[te["claim_count"] > 0]
    exp_te, loss_te = te["exposure"].to_numpy(), te["incurred_amount"].to_numpy()
    flat_freq = df.loc[train, "n_claims"].sum() / df.loc[train, "exposure"].sum()
    flat_sev = df.loc[sev_train, "incurred_capped"].sum() / df.loc[sev_train, "claim_count"].sum()
    sev_y = (sev_te["incurred_capped"] / sev_te["claim_count"]).to_numpy()

    preds_pp = {"glm": te["pp_glm"].to_numpy(), "gbm": te["pp_gbm"].to_numpy()}
    boot = metrics.bootstrap_gini(loss_te, preds_pp, exp_te, n_boot=200, seed=SEED)
    diff = boot["gbm"] - boot["glm"]
    boot_c = metrics.bootstrap_gini(te["incurred_capped"].to_numpy(), preds_pp, exp_te, n_boot=200, seed=SEED)

    def ci(a):
        return [round(float(np.percentile(a, 2.5)), 4), round(float(np.percentile(a, 97.5)), 4)]

    report = {
        "data": {"policies": int(len(df)), "train_policies": int(train.sum()), "test_policies": int(len(te)),
                 "claims": int(df["claim_count"].sum()), "exposure_years": round(float(df["exposure"].sum()), 1),
                 "sample_frac": sample_frac},
        "large_loss": {"cap_eur": round(cap, 2), "quantile": LARGE_LOSS_QUANTILE,
                       "load_factor": round(large_loss_load, 4)},
        "frequency_poisson_deviance": {
            "null": metrics.poisson_deviance(te["n_claims"].to_numpy(), exp_te, np.full(len(te), flat_freq)),
            "glm": metrics.poisson_deviance(te["n_claims"].to_numpy(), exp_te, te["freq_glm"].to_numpy()),
            "gbm": metrics.poisson_deviance(te["n_claims"].to_numpy(), exp_te, te["freq_gbm"].to_numpy())},
        "severity_gamma_deviance": {
            "null": metrics.gamma_deviance(sev_y, sev_te["claim_count"].to_numpy(), np.full(len(sev_te), flat_sev)),
            "glm": metrics.gamma_deviance(sev_y, sev_te["claim_count"].to_numpy(), sev_te["sev_glm"].to_numpy()),
            "gbm": metrics.gamma_deviance(sev_y, sev_te["claim_count"].to_numpy(), sev_te["sev_gbm"].to_numpy())},
        "frequency_gini": {m: metrics.gini(te["n_claims"].to_numpy(), te[f"freq_{m}"].to_numpy(), exp_te)
                           for m in ("glm", "gbm")},
        "pure_premium_gini": {m: metrics.gini(loss_te, te[f"pp_{m}"].to_numpy(), exp_te) for m in ("glm", "gbm")},
        "pure_premium_gini_ci95": {"glm": ci(boot["glm"]), "gbm": ci(boot["gbm"]), "gbm_minus_glm": ci(diff)},
        "capped_pure_premium_gini": {m: metrics.gini(te["incurred_capped"].to_numpy(), te[f"pp_{m}"].to_numpy(), exp_te)
                                     for m in ("glm", "gbm")},
        "capped_pure_premium_gini_ci95": {"glm": ci(boot_c["glm"]), "gbm": ci(boot_c["gbm"]),
                                          "gbm_minus_glm": ci(boot_c["gbm"] - boot_c["glm"])},
        "test_predicted_over_actual": {m: float((te[f"pp_{m}"] * te["exposure"]).sum() / loss_te.sum())
                                       for m in ("flat", "glm", "gbm")},
        "balance_factors": {k: round(float(v), 4) for k, v in balance.items()},
        "gbm_iterations": {"frequency": int(gbm_f.n_iter_), "severity": int(gbm_s.n_iter_)},
        "glm_parameters": {"frequency": int(len(res_f.params)), "severity": int(len(res_s.params))},
        "severity_glm_factors": list(spec_s),
    }
    dev = report["frequency_poisson_deviance"]
    report["frequency_deviance_explained"] = {m: 1 - dev[m] / dev["null"] for m in ("glm", "gbm")}

    # ---- Tables
    rel = pd.concat([glm.relativity_table(tariff_f, "frequency"), glm.relativity_table(tariff_s, "severity")])
    rel.round(4).to_csv(results / "glm_relativities.csv", index=False)
    # Lift tables on full incurred and on capped losses x large-loss load (same total in
    # expectation, far less noise from the handful of claims above the cap).
    loss_capped_te = te["incurred_capped"].to_numpy() * large_loss_load
    for suffix, losses in (("", loss_te), ("_capped", loss_capped_te)):
        lifts = {m: metrics.lift_table(losses, exp_te, te[f"pp_{m}"].to_numpy()) for m in ("glm", "gbm")}
        pd.concat(lifts, names=["model"]).round(4).to_csv(results / f"lift_by_decile{suffix}.csv")
        dl = metrics.double_lift_table(losses, exp_te, te["pp_glm"].to_numpy(), te["pp_gbm"].to_numpy())
        dl.round(4).to_csv(results / f"double_lift_gbm_vs_glm{suffix}.csv")

    # ---- Figures
    fig, ax = plt.subplots(figsize=(5.5, 5))
    for m, color in (("glm", "#2b6cb0"), ("gbm", "#c05621")):
        x, y = metrics.lorenz_curve(loss_te, te[f"pp_{m}"].to_numpy(), exp_te)
        ax.plot(x, y, color=color, label=f"{m.upper()}  Gini {report['pure_premium_gini'][m]:.3f}")
    ax.plot([0, 1], [0, 1], color="grey", ls="--", lw=1, label="flat rate")
    ax.set(xlabel="cumulative share of exposure (lowest predicted risk first)",
           ylabel="cumulative share of incurred losses", title="Ordered Lorenz curve, test set")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(results / "figures" / "lorenz_curve.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.plot(dl.index, dl["loss_ratio_a"], "o-", color="#2b6cb0", label="GLM")
    ax.plot(dl.index, dl["loss_ratio_b"], "o-", color="#c05621", label="GBM")
    ax.axhline(1, color="grey", lw=1, ls="--")
    ax.set(xlabel="decile of GBM / GLM premium ratio", ylabel="actual / predicted losses",
           title="Double lift, test set (claims capped, excess loaded)")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(results / "figures" / "double_lift.png", dpi=130)
    plt.close(fig)

    shap_summary = explain_gbm(gbm_f, X[df["split"] == "test"], results)
    report["gbm_frequency_mean_abs_shap"] = shap_summary

    # ---- Artifacts
    tariff = {"frequency": tariff_f, "severity": tariff_s, "large_loss_load": large_loss_load,
              "large_loss_cap_eur": cap, "trained_on_policies": int(train.sum()), "seed": SEED}
    glm.save(tariff, models_dir / "tariff.json")
    joblib.dump({"frequency": gbm_f, "severity": gbm_s, "levels": gbm_levels, "large_loss_load": large_loss_load,
                 "balance": {"frequency": balance["freq_gbm"], "severity": balance["sev_gbm"]}},
                models_dir / "gbm.joblib")
    processed = ROOT / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    out = df[["policy_id", "split", "exposure", "pp_flat", "pp_glm", "pp_gbm"]].copy()
    out["incurred_capped_loaded"] = df["incurred_capped"] * large_loss_load
    for m in ("flat", "glm", "gbm"):
        out[f"premium_{m}"] = out[f"pp_{m}"] * out["exposure"]
    out.to_parquet(processed / "policy_predictions.parquet", index=False)

    (results / "metrics.json").write_text(json.dumps(report, indent=2, default=float))
    print(json.dumps(report, indent=2, default=float))
    print(f"done in {time.time() - t0:.1f}s")


def explain_gbm(model, X_test: pd.DataFrame, results: Path) -> dict:
    """TreeSHAP on a fixed sample of test policies (log-frequency scale), aggregated per factor."""
    import shap

    sample = X_test.sample(n=min(5000, len(X_test)), random_state=SEED)
    explainer = shap.TreeExplainer(model)
    values = explainer.shap_values(sample)
    # Exactness check against sklearn's own predictions (log link), not shap's tree copy
    gap = np.abs(values.sum(axis=1) + explainer.expected_value - np.log(model.predict(sample))).max()
    if gap > 1e-4:
        raise RuntimeError(f"SHAP values do not reproduce model predictions (max gap {gap:.3g})")

    per_factor = pd.DataFrame(values, columns=sample.columns).T.groupby(features.gbm_factor_of).sum().T
    mean_abs = per_factor.abs().mean().sort_values(ascending=False)

    numeric = [c for c in features.GBM_NUMERIC if c != "diesel"]
    idx = [sample.columns.get_loc(c) for c in numeric]
    plt.figure()
    shap.summary_plot(values[:, idx], sample[numeric], show=False)
    plt.title("GBM frequency: SHAP of numeric factors (log scale)")
    plt.tight_layout()
    plt.savefig(results / "figures" / "shap_frequency.png", dpi=130)
    plt.close("all")
    mean_abs.round(4).to_csv(results / "gbm_frequency_shap_importance.csv", header=["mean_abs_shap"])
    return {"max_additivity_gap": float(gap), **{k: round(float(v), 4) for k, v in mean_abs.items()}}


if __name__ == "__main__":
    main()
