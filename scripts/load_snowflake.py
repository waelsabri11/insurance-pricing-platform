"""Load the raw parquet files (and model predictions) into Snowflake.

Requires `uv sync --extra snowflake`, warehouse/snowflake_setup.sql already run, and the
SNOWFLAKE_* variables used by dbt/profiles.yml. Then: `DBT_TARGET=snowflake make dbt-build`.
Not executed yet in this repository (no Snowflake account attached).
"""

import os
from pathlib import Path

import snowflake.connector

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "RAW.FREMTPL2FREQ": ROOT / "data" / "raw" / "freMTPL2freq.parquet",
    "RAW.FREMTPL2SEV": ROOT / "data" / "raw" / "freMTPL2sev.parquet",
    "MODEL_OUTPUTS.POLICY_PREDICTIONS": ROOT / "data" / "processed" / "policy_predictions.parquet",
}


def main() -> None:
    con = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"], user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"], role=os.environ.get("SNOWFLAKE_ROLE", "TRANSFORMER"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "PRICING_XS"), database="MOTOR_PRICING")
    cur = con.cursor()
    for table, path in FILES.items():
        if not path.exists():
            print(f"skip {table}: {path} not found")
            continue
        stage_path = f"@RAW.LANDING/{path.stem}/"
        cur.execute(f"put file://{path} {stage_path} overwrite = true auto_compress = false")
        cur.execute(f"""
            create or replace table {table} using template (
                select array_agg(object_construct(*)) from table(infer_schema(
                    location => '{stage_path}', file_format => 'RAW.PARQUET_FMT')))""")
        cur.execute(f"""copy into {table} from {stage_path}
                        file_format = (format_name = 'RAW.PARQUET_FMT') match_by_column_name = case_sensitive""")
        print(table, cur.fetchall())
    con.close()


if __name__ == "__main__":
    main()
