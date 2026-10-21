"""Download freMTPL2freq / freMTPL2sev into data/raw/ as parquet.

Primary source: the CASdatasets R package on GitHub (Dutang & Charpentier), which is the
original publication of the data. Fallback: OpenML (ids 41214 / 41215), whose copy is a
slightly different snapshot (678,013 policies / 26,639 claims vs 677,991 / 26,444).
Files already present are skipped.
"""

import sys
import tempfile
import urllib.request
from pathlib import Path

import pandas as pd

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
CAS_URL = "https://raw.githubusercontent.com/dutangc/CASdatasets/master/data/{name}.rda"
OPENML_IDS = {"freMTPL2freq": 41214, "freMTPL2sev": 41215}


def from_casdatasets(name: str) -> pd.DataFrame:
    import rdata

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{name}.rda"
        urllib.request.urlretrieve(CAS_URL.format(name=name), path)
        return rdata.read_rda(path)[name]


def from_openml(name: str) -> pd.DataFrame:
    from sklearn.datasets import fetch_openml

    return fetch_openml(data_id=OPENML_IDS[name], as_frame=True, parser="auto").frame


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True)
    for col in df.columns:
        if isinstance(df[col].dtype, pd.CategoricalDtype) or pd.api.types.is_string_dtype(df[col]):
            df[col] = df[col].astype(str).str.strip("'")
    # R writes some ids in scientific notation ("1e+05"); go through float to parse them
    df["IDpol"] = pd.to_numeric(df["IDpol"]).round().astype("int64")
    return df


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for name in OPENML_IDS:
        out = RAW / f"{name}.parquet"
        if out.exists():
            print(f"{out.name} already present, skipping")
            continue
        try:
            df, source = from_casdatasets(name), "CASdatasets"
        except Exception as exc:  # network or format problem: try the OpenML mirror
            print(f"CASdatasets download failed ({exc}); trying OpenML", file=sys.stderr)
            df, source = from_openml(name), "OpenML"
        df = normalise(df)
        df.to_parquet(out, index=False)
        print(f"wrote {out.name} from {source}: {len(df):,} rows")


if __name__ == "__main__":
    main()
