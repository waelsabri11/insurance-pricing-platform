"""Quote API: POST /quote prices a driver/vehicle profile with the GLM tariff.

Run: uv run uvicorn pricing.api:app --reload   (TARIFF_PATH overrides models/tariff.json)
"""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from pricing.rating import quote

DEFAULT_TARIFF = Path(__file__).resolve().parents[2] / "models" / "tariff.json"

Region = Literal[
    "Alsace", "Aquitaine", "Auvergne", "Basse-Normandie", "Bourgogne", "Bretagne", "Centre",
    "Champagne-Ardenne", "Corse", "Franche-Comte", "Haute-Normandie", "Ile-de-France",
    "Languedoc-Roussillon", "Limousin", "Lorraine", "Midi-Pyrenees", "Nord-Pas-de-Calais",
    "Pays-de-la-Loire", "Picardie", "Poitou-Charentes", "Provence-Alpes-Cotes-D'Azur", "Rhone-Alpes",
]
Brand = Literal["B1", "B2", "B3", "B4", "B5", "B6", "B10", "B11", "B12", "B13", "B14"]


class QuoteRequest(BaseModel):
    """Rating factors available in freMTPL2. There is deliberately no gender field: EU law
    (Test-Achats ruling, 2012) forbids gender as a pricing factor."""

    driver_age: int = Field(ge=18, le=100, examples=[35])
    vehicle_age: int = Field(ge=0, le=100, examples=[4])
    vehicle_power: int = Field(ge=4, le=15, description="Fiscal power class (4-15)", examples=[6])
    bonus_malus: int = Field(ge=50, le=230, description="French bonus-malus coefficient x100", examples=[50])
    population_density: int = Field(ge=1, le=27000, description="Inhabitants/km2 of the driver's town",
                                     examples=[600])
    fuel_type: Literal["Diesel", "Regular"]
    vehicle_brand: Brand
    region_name: Region
    exposure: float = Field(1.0, gt=0, le=1, description="Fraction of a year to price")


class FactorLine(BaseModel):
    factor: str
    rated_value: str | float
    frequency_relativity: float
    severity_relativity: float
    combined_relativity: float


class QuoteResponse(BaseModel):
    pure_premium: float = Field(description="Expected claim cost (EUR) for the requested exposure")
    annual_pure_premium: float
    expected_claim_frequency: float = Field(description="Claims per policy-year")
    expected_claim_severity: float = Field(description="EUR per claim, before the large-loss load")
    base_premium: float = Field(description="Annual pure premium of the base profile (all relativities = 1)")
    large_loss_load: float
    breakdown: list[FactorLine]
    model: str = "GLM frequency (Poisson) x severity (Gamma)"


@lru_cache(maxsize=1)
def load_tariff() -> dict:
    return json.loads(Path(os.environ.get("TARIFF_PATH", DEFAULT_TARIFF)).read_text())


app = FastAPI(title="Motor TPL quote API", version="1.0.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "trained_on_policies": load_tariff()["trained_on_policies"]}


@app.post("/quote", response_model=QuoteResponse)
def post_quote(req: QuoteRequest) -> QuoteResponse:
    profile = req.model_dump(exclude={"exposure"})
    return QuoteResponse(**quote(load_tariff(), profile, req.exposure))
