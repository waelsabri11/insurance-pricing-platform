import math

import pytest
from fastapi.testclient import TestClient

from pricing.api import app, load_tariff

client = TestClient(app)

PROFILE = {
    "driver_age": 35, "vehicle_age": 4, "vehicle_power": 6, "bonus_malus": 50, "population_density": 600,
    "fuel_type": "Regular", "vehicle_brand": "B12", "region_name": "Centre",
}


def post(**overrides):
    return client.post("/quote", json={**PROFILE, **overrides})


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_quote_is_product_of_base_and_relativities():
    body = post().json()
    combined = math.prod(line["combined_relativity"] for line in body["breakdown"])
    assert body["annual_pure_premium"] == pytest.approx(body["base_premium"] * combined, rel=1e-9)
    assert body["annual_pure_premium"] == pytest.approx(
        body["expected_claim_frequency"] * body["expected_claim_severity"] * body["large_loss_load"], rel=1e-9)
    assert 10 < body["annual_pure_premium"] < 2000


def test_exposure_scales_premium():
    full, half = post().json(), post(exposure=0.5).json()
    assert half["pure_premium"] == pytest.approx(full["pure_premium"] / 2)


def test_malus_costs_more_than_bonus():
    assert post(bonus_malus=120).json()["pure_premium"] > post(bonus_malus=50).json()["pure_premium"]


def test_bonus_malus_capped_like_training():
    assert post(bonus_malus=200).json()["pure_premium"] == pytest.approx(post(bonus_malus=150).json()["pure_premium"])


def test_breakdown_covers_every_tariff_factor():
    tariff = load_tariff()
    factors = {line["factor"] for line in post().json()["breakdown"]}
    assert set(tariff["frequency"]["factors"]) | set(tariff["severity"]["factors"]) <= factors


@pytest.mark.parametrize("field,value", [
    ("driver_age", 17), ("bonus_malus", 40), ("population_density", 0), ("fuel_type", "Electric"),
    ("region_name", "Atlantis"), ("exposure", 0), ("exposure", 1.5),
])
def test_invalid_input_rejected(field, value):
    assert post(**{field: value}).status_code == 422


def test_no_gender_field():
    assert "gender" not in app.openapi()["components"]["schemas"]["QuoteRequest"]["properties"]


def test_offer_is_simulated_and_within_bounds():
    body = post().json()
    o = body["offer"]
    assert o["simulated"] is True
    assert 0.8 <= o["multiplier"] <= 1.3
    assert o["price"] == pytest.approx(o["technical_premium"] * o["multiplier"])
    assert 0 < o["expected_conversion"] < 1
    assert o["annual_technical_premium"] > body["annual_pure_premium"]


def test_offer_scales_with_exposure():
    full, half = post().json()["offer"], post(exposure=0.5).json()["offer"]
    assert half["price"] == pytest.approx(full["price"] / 2)
    assert half["expected_conversion"] == pytest.approx(full["expected_conversion"])


def test_senior_guard_caps_multiplier():
    assert post(driver_age=75).json()["offer"]["multiplier"] <= 1.10 + 1e-9


def test_sensitivity_curves_conversion_falls_with_price():
    for curve in post().json()["offer"]["sensitivity"]:
        conv = [p["conversion"] for p in curve["points"]]
        assert conv == sorted(conv, reverse=True)
        assert len(curve["points"]) == 11


def test_higher_sensitivity_lowers_conversion_above_market():
    curves = {c["price_sensitivity"]: c for c in post(bonus_malus=120).json()["offer"]["sensitivity"]}
    assert curves[6.0]["points"][-1]["conversion"] < curves[2.0]["points"][-1]["conversion"]


def test_no_protected_field_in_request_or_segments():
    from pricing.api import QuoteRequest, load_optimization

    banned = {"gender", "sex", "nationality", "ethnicity", "religion", "disability"}
    assert not banned & set(QuoteRequest.model_fields)
    assert not banned & set(load_optimization()["segment_factors"])
