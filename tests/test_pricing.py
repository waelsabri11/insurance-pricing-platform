import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from pricing import features, glm, metrics, rating


def test_gini_perfect_and_flat():
    rng = np.random.default_rng(0)
    n = 20_000
    exposure = np.ones(n)
    losses = rng.gamma(1.0, 100, n)
    # a flat prediction leaves policies in random order: Gini is ~0 up to sampling noise
    assert metrics.gini(losses, np.ones(n), exposure) == pytest.approx(0.0, abs=0.03)
    assert metrics.gini(losses, losses, exposure) > 0.4
    assert metrics.gini(losses, -losses, exposure) < -0.4


def test_exposure_bins_hold_equal_exposure():
    rng = np.random.default_rng(1)
    exposure = rng.uniform(0.1, 1.0, 10_000)
    bins = metrics.exposure_quantile_bins(rng.random(10_000), exposure, 10)
    shares = pd.Series(exposure).groupby(bins).sum() / exposure.sum()
    assert np.allclose(shares, 0.1, atol=0.002)


def test_bands_match_dbt_definitions():
    assert [rating.driver_age_band(a) for a in (18, 20, 21, 25, 26, 40, 41, 50, 51, 70, 71, 100)] == [
        "18-20", "18-20", "21-25", "21-25", "26-30", "31-40", "41-50", "41-50", "51-70", "51-70", "71+", "71+"]
    assert [rating.vehicle_age_band(a) for a in (0, 1, 10, 11)] == ["0", "1-10", "1-10", "11+"]


def test_glm_recovers_known_poisson_relativities():
    rng = np.random.default_rng(42)
    n = 60_000
    fac = pd.DataFrame({"colour": rng.choice(["red", "blue"], n, p=[0.3, 0.7]), "x": rng.normal(0, 1, n)})
    exposure = rng.uniform(0.2, 1.0, n)
    mu = exposure * 0.1 * np.where(fac.colour == "red", 1.5, 1.0) * np.exp(0.2 * fac.x)
    y = rng.poisson(mu)
    spec = glm.make_spec(fac, pd.Series(exposure), ["colour"], {"x": 0.0})
    res, _ = glm.fit(fac, y, sm.families.Poisson(), spec, offset=np.log(exposure))
    tariff = glm.to_tariff(res, spec)
    assert spec["colour"]["reference"] == "blue"  # most exposure
    assert np.exp(tariff["factors"]["colour"]["levels"]["red"]["coef"]) == pytest.approx(1.5, rel=0.05)
    assert tariff["factors"]["x"]["coef"] == pytest.approx(0.2, abs=0.02)
    # JSON tariff pricing (batch and single quote) agrees with statsmodels
    sm_pred = res.predict(glm.design_matrix(fac, spec))
    assert np.allclose(glm.predict(tariff, fac), sm_pred)
    base, rel = rating.relativities(tariff, {"colour": "red", "x": 1.0})
    assert base * rel["colour"] * rel["x"] == pytest.approx(glm.predict(tariff, fac.iloc[[0]].assign(
        colour="red", x=1.0))[0])


def test_gbm_feature_columns_map_back_to_factors():
    df = pd.DataFrame({"driver_age": [30], "vehicle_age": [2], "vehicle_power": [6], "bonus_malus": [50],
                       "population_density": [100], "fuel_type": ["Diesel"], "vehicle_brand": ["B1"],
                       "region_name": ["Centre"]})
    X = features.gbm_features(df, {"vehicle_brand": ["B1", "B2"], "region_name": ["Centre"]})
    assert X.loc[0, "diesel"] == 1.0 and X.loc[0, "vehicle_brand=B1"] == 1.0
    assert {features.gbm_factor_of(c) for c in X.columns} == {
        "driver_age", "vehicle_age", "vehicle_power", "bonus_malus", "log_density", "fuel_type",
        "vehicle_brand", "region_name"}
