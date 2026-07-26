"""Database output — the one place every pipeline stage writes its results
back to MySQL, so table-replace/append semantics stay consistent."""

from __future__ import annotations

import pandas as pd
from sqlalchemy.engine import Engine


def write_table(df: pd.DataFrame, table_name: str, engine: Engine, if_exists: str = "replace") -> int:
    df.to_sql(table_name, engine, if_exists=if_exists, index=False, chunksize=1000)
    return len(df)


def append_rows(df: pd.DataFrame, table_name: str, engine: Engine) -> int:
    df.to_sql(table_name, engine, if_exists="append", index=False, chunksize=1000)
    return len(df)
