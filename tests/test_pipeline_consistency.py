"""Checks that need the built warehouse and trained models (skipped on a fresh clone)."""

import json
from pathlib import Path

import duckdb
import pytest

from pricing import rating

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse.duckdb"
PRED = ROOT / "data" / "processed" / "policy_predictions.parquet"

pytestmark = pytest.mark.skipif(not (DB.exists() and PRED.exists()), reason="run `make pipeline` first")


@pytest.fixture(scope="module")
def sample():
    con = duckdb.connect(str(DB), read_only=True)
    df = con.sql(f"""
        select p.*, pr.pp_glm
        from marts.fct_policies p join read_parquet('{PRED}') pr using (policy_id)
        order by hash(policy_id) limit 500""").df()
    con.close()
    return df


def test_python_bands_match_dbt_bands(sample):
    assert (sample.driver_age.map(rating.driver_age_band) == sample.driver_age_band).all()
    assert (sample.vehicle_age.map(rating.vehicle_age_band) == sample.vehicle_age_band).all()


def test_api_rating_reproduces_training_predictions(sample):
    tariff = json.loads((ROOT / "models" / "tariff.json").read_text())
    for row in sample.to_dict("records"):
        assert rating.quote(tariff, row)["annual_pure_premium"] == pytest.approx(row["pp_glm"], rel=1e-9)
