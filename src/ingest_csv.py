"""
Phase 1: create the MySQL database, create raw_* staging tables (one per
source CSV, minimally typed), load the CSVs into them, and validate the
load (row counts, dtypes, relationships, duplicates, nulls, date ranges).

Raw tables are a straight staging layer — schema mirrors the CSVs closely
so nothing is lost or reshaped before Phase 2 cleans it.

Run: python src/ingest_csv.py
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path
from sqlalchemy import text

from db import ensure_database_exists, get_engine

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

# table_name -> (csv filename, DDL, date columns to parse on load)
RAW_TABLES = {
    "raw_dim_customer": (
        "dim_customer.csv",
        """
        CREATE TABLE raw_dim_customer (
            customer_id VARCHAR(20) PRIMARY KEY,
            customer_name VARCHAR(255),
            industryregion VARCHAR(255),
            customer_segment VARCHAR(50),
            acquisition_date DATE
        )
        """,
        ["acquisition_date"],
    ),
    "raw_dim_date": (
        "dim_date.csv",
        """
        CREATE TABLE raw_dim_date (
            date DATE PRIMARY KEY,
            month INT,
            quarter INT,
            year INT
        )
        """,
        ["date"],
    ),
    "raw_dim_product_plan": (
        "dim_product_plan.csv",
        """
        CREATE TABLE raw_dim_product_plan (
            plan_id VARCHAR(20) PRIMARY KEY,
            product_id VARCHAR(20),
            plan_name VARCHAR(255),
            billing_frequency VARCHAR(20),
            price DECIMAL(12,2)
        )
        """,
        [],
    ),
    "raw_fact_subscription": (
        "fact_subscription.csv",
        """
        CREATE TABLE raw_fact_subscription (
            subscription_id VARCHAR(20) PRIMARY KEY,
            customer_id VARCHAR(20),
            plan_id VARCHAR(20),
            start_date DATE,
            end_date DATE NULL,
            renewal_date DATE,
            status VARCHAR(20),
            mrr DECIMAL(12,2),
            arr DECIMAL(12,2)
        )
        """,
        ["start_date", "end_date", "renewal_date"],
    ),
    "raw_fact_revenue": (
        "fact_revenue.csv",
        """
        CREATE TABLE raw_fact_revenue (
            revenue_id VARCHAR(20) PRIMARY KEY,
            customer_id VARCHAR(20),
            subscription_id VARCHAR(20),
            revenue_date DATE,
            gross_revenue DECIMAL(12,2),
            discount DECIMAL(12,2),
            refund DECIMAL(12,2),
            net_revenue DECIMAL(12,2),
            revenue_type VARCHAR(20)
        )
        """,
        ["revenue_date"],
    ),
    "raw_fact_customer_usage": (
        "fact_customer_usage.csv",
        """
        CREATE TABLE raw_fact_customer_usage (
            customer_id VARCHAR(20),
            usage_date DATE,
            active_users INT,
            login_count INT,
            session_count INT,
            feature_usage INT,
            api_calls INT,
            PRIMARY KEY (customer_id, usage_date)
        )
        """,
        ["usage_date"],
    ),
    "raw_fact_churn": (
        "fact_churn.csv",
        """
        CREATE TABLE raw_fact_churn (
            customer_id VARCHAR(20),
            subscription_id VARCHAR(20) PRIMARY KEY,
            churn_date DATE,
            churn_reason VARCHAR(255),
            mrr_lost DECIMAL(12,2)
        )
        """,
        ["churn_date"],
    ),
    "raw_fact_sales_pipeline": (
        "fact_sales_pipeline.csv",
        """
        CREATE TABLE raw_fact_sales_pipeline (
            opportunity_id VARCHAR(20) PRIMARY KEY,
            customer_id VARCHAR(20),
            expected_close_date DATE,
            deal_value DECIMAL(12,2),
            stage VARCHAR(50),
            probability DECIMAL(4,2)
        )
        """,
        ["expected_close_date"],
    ),
    "raw_fact_support_ticket": (
        "fact_support_ticket.csv",
        """
        CREATE TABLE raw_fact_support_ticket (
            ticket_id VARCHAR(20) PRIMARY KEY,
            customer_id VARCHAR(20),
            created_date DATE,
            resolved_date DATE NULL,
            priority VARCHAR(20),
            category VARCHAR(50),
            resolution_time DECIMAL(10,2) NULL
        )
        """,
        ["created_date", "resolved_date"],
    ),
}

# child_table.fk_col -> parent_table.pk_col, checked after load
RELATIONSHIPS = [
    ("raw_fact_subscription", "customer_id", "raw_dim_customer", "customer_id"),
    ("raw_fact_subscription", "plan_id", "raw_dim_product_plan", "plan_id"),
    ("raw_fact_revenue", "customer_id", "raw_dim_customer", "customer_id"),
    ("raw_fact_revenue", "subscription_id", "raw_fact_subscription", "subscription_id"),
    ("raw_fact_customer_usage", "customer_id", "raw_dim_customer", "customer_id"),
    ("raw_fact_churn", "subscription_id", "raw_fact_subscription", "subscription_id"),
    ("raw_fact_sales_pipeline", "customer_id", "raw_dim_customer", "customer_id"),
    ("raw_fact_support_ticket", "customer_id", "raw_dim_customer", "customer_id"),
]


def create_raw_schema(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table_name in RAW_TABLES:
            conn.execute(text(f"DROP TABLE IF EXISTS `{table_name}`"))
        for table_name, (_, ddl, _) in RAW_TABLES.items():
            conn.execute(text(ddl))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))


def load_all_csvs(engine) -> dict[str, int]:
    loaded_counts = {}
    for table_name, (csv_name, _, date_cols) in RAW_TABLES.items():
        df = pd.read_csv(RAW_DIR / csv_name, parse_dates=date_cols or None)
        df.to_sql(table_name, engine, if_exists="append", index=False, chunksize=1000)
        loaded_counts[table_name] = len(df)
    return loaded_counts


def validate(engine, loaded_counts: dict[str, int]) -> bool:
    all_ok = True
    print("\n--- Row counts (CSV vs. loaded) ---")
    for table_name in RAW_TABLES:
        with engine.connect() as conn:
            db_count = conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`")).scalar()
        expected = loaded_counts[table_name]
        status = "OK" if db_count == expected else "FAIL"
        if status == "FAIL":
            all_ok = False
        print(f"  {table_name:<28} csv={expected:<6} db={db_count:<6} {status}")

    print("\n--- Null counts per column ---")
    for table_name in RAW_TABLES:
        with engine.connect() as conn:
            cols = conn.execute(text(f"SHOW COLUMNS FROM `{table_name}`")).fetchall()
            null_report = []
            for col in cols:
                col_name = col[0]
                n_nulls = conn.execute(
                    text(f"SELECT COUNT(*) FROM `{table_name}` WHERE `{col_name}` IS NULL")
                ).scalar()
                if n_nulls > 0:
                    null_report.append(f"{col_name}={n_nulls}")
        if null_report:
            print(f"  {table_name:<28} {', '.join(null_report)}")

    print("\n--- Duplicate primary keys ---")
    print("  enforced at load time by PRIMARY KEY constraints (load would have failed otherwise)")

    print("\n--- Referential integrity ---")
    for child_table, fk_col, parent_table, pk_col in RELATIONSHIPS:
        with engine.connect() as conn:
            orphans = conn.execute(text(f"""
                SELECT COUNT(*) FROM `{child_table}` c
                LEFT JOIN `{parent_table}` p ON c.`{fk_col}` = p.`{pk_col}`
                WHERE p.`{pk_col}` IS NULL
            """)).scalar()
        status = "OK" if orphans == 0 else f"FAIL ({orphans} orphans)"
        if orphans != 0:
            all_ok = False
        print(f"  {child_table}.{fk_col} -> {parent_table}.{pk_col:<15} {status}")

    print("\n--- Date ranges ---")
    for table_name, (_, _, date_cols) in RAW_TABLES.items():
        for col in date_cols:
            with engine.connect() as conn:
                min_d, max_d = conn.execute(text(f"SELECT MIN(`{col}`), MAX(`{col}`) FROM `{table_name}`")).one()
            print(f"  {table_name}.{col:<20} {min_d} to {max_d}")

    return all_ok


def main():
    ensure_database_exists()
    engine = get_engine()

    print("Creating raw schema...")
    create_raw_schema(engine)

    print("Loading CSVs...")
    loaded_counts = load_all_csvs(engine)
    for table_name, count in loaded_counts.items():
        print(f"  {table_name:<28} {count:>6,} rows")

    ok = validate(engine, loaded_counts)
    print(f"\n{'ALL CHECKS PASSED' if ok else 'SOME CHECKS FAILED - see above'}")
    engine.dispose()
    return ok


if __name__ == "__main__":
    main()
