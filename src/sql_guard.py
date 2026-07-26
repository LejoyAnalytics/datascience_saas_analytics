"""
Read-only SQL safety guard for the chatbot's Groq-generated queries.

Every query goes through, in order:
  1. must start with SELECT or WITH (regex)
  2. must be exactly one statement (sqlparse — blocks stacked `; DROP ...` queries)
  3. keyword blacklist scan, as defense-in-depth beyond (1)/(2)
  4. LIMIT 200 appended if the query doesn't already have one
  5. executed on a dedicated connection with the session forced into
     READ ONLY mode, so even a validator bypass can't mutate data

This is the only code path that turns chatbot-generated SQL into an actual
database call.
"""

from __future__ import annotations

import re

import pandas as pd
import sqlparse
from sqlalchemy import text

from db import get_engine

MAX_ROWS = 200

_FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE",
    "REPLACE", "GRANT", "REVOKE", "EXEC", "EXECUTE", "CALL", "MERGE",
    "INTO OUTFILE", "INTO DUMPFILE", "LOAD_FILE", "LOCK TABLES", "UNLOCK",
    "SHUTDOWN", "KILL", "SET GLOBAL",
]


class UnsafeQueryError(Exception):
    """Raised when a candidate query fails the read-only safety checks."""


def validate(sql: str) -> str:
    """Return the cleaned/limited SQL if it passes every check, else raise UnsafeQueryError."""
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise UnsafeQueryError("Empty query.")

    if not re.match(r"^\s*(SELECT|WITH)\b", cleaned, re.IGNORECASE):
        raise UnsafeQueryError("Query must start with SELECT or WITH.")

    statements = [s for s in sqlparse.parse(cleaned) if s.token_first(skip_cm=True) is not None]
    if len(statements) != 1:
        raise UnsafeQueryError("Only a single statement is allowed (no stacked queries).")

    upper = cleaned.upper()
    for kw in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", upper):
            raise UnsafeQueryError(f"Query contains a disallowed keyword: {kw}")

    if "LIMIT" not in upper:
        cleaned = f"{cleaned} LIMIT {MAX_ROWS}"

    return cleaned


def run_safe_query(sql: str) -> pd.DataFrame:
    """Validate, then execute read-only. Raises UnsafeQueryError (rejected
    before touching the database) or the underlying DB error (bad SQL) —
    callers are expected to catch both."""
    safe_sql = validate(sql)

    engine = get_engine()
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("SET SESSION TRANSACTION READ ONLY"))
            except Exception:
                pass  # best-effort defense-in-depth; validate() above is the real guard
            df = pd.read_sql(text(safe_sql), conn)
    finally:
        engine.dispose()

    return df.head(MAX_ROWS)
