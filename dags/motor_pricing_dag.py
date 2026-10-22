"""Airflow DAG for the motor pricing platform.

Each task shells out to the Makefile target of the same name, so Airflow only orchestrates:
the work runs in the project's own uv environment, and `make pipeline` runs the identical
steps without Airflow. Airflow therefore lives in its own environment (see README).
"""

import os
from datetime import datetime

from airflow import DAG

try:  # Airflow 3
    from airflow.providers.standard.operators.bash import BashOperator
except ImportError:  # Airflow 2
    from airflow.operators.bash import BashOperator

PROJECT_DIR = os.environ.get(
    "PRICING_PROJECT_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def make(target: str) -> BashOperator:
    return BashOperator(task_id=target.replace("-", "_"), bash_command=f"make -C {PROJECT_DIR} {target}")


with DAG(
    dag_id="motor_pricing",
    description="freMTPL2 -> dbt marts -> GLM/GBM pricing -> price optimization -> loss-ratio mart -> docs",
    start_date=datetime(2026, 1, 1),
    schedule="@monthly",
    catchup=False,
    max_active_runs=1,
    tags=["pricing", "dbt"],
) as dag:
    data, dbt_build, train, optimize, dbt_post, docs, test = (
        make(t) for t in ("data", "dbt-build", "train", "optimize", "dbt-post", "docs", "test"))
    data >> dbt_build >> train >> optimize >> dbt_post >> [docs, test]
