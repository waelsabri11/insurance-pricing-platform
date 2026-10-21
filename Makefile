# One command end to end:  make pipeline
# Every step is also an Airflow task (dags/motor_pricing_dag.py) that calls the same target.
DBT = cd dbt && uv run dbt
DBT_FLAGS = --profiles-dir .

.PHONY: setup data dbt-build train dbt-post docs pipeline test lint serve docker-build docker-run clean

setup:
	uv sync

data:
	uv run python scripts/download_data.py

dbt-build:           ## staging -> intermediate -> marts, with all tests
	$(DBT) build $(DBT_FLAGS) --exclude tag:post_model

train:               ## GLM + GBM, metrics and figures in results/, tariff in models/
	uv run python -m pricing.train

dbt-post:            ## loss-ratio mart on the model predictions
	$(DBT) build $(DBT_FLAGS) --select tag:post_model+

docs:
	$(DBT) docs generate $(DBT_FLAGS)

pipeline: data dbt-build train dbt-post docs test

test:
	uv run pytest -q

lint:
	uv run ruff check src scripts tests dags

serve:
	uv run uvicorn pricing.api:app --port 8000

docker-build:
	docker build -t motor-quote-api .

docker-run:
	docker run --rm -p 8000:8000 motor-quote-api

clean:
	rm -rf data/processed data/warehouse.duckdb dbt/target dbt/logs
