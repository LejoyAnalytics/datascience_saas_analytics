"""
Phase 2: read raw_* tables from MySQL, clean them into processed dim_/fact_
tables, and build monthly_revenue_summary — all written back to MySQL.

Revenue attribution logic (how a billed revenue row becomes new / expansion
/ renewal): fact_revenue.revenue_type is 'New' on a subscription's first
billed month and 'Recurring' every month after. Combined with whether that
subscription was the customer's very first (a signup) or an additional one
added later (a cross-sell/upsell while the relationship continued):

    revenue_type='New',       first subscription for customer -> new_revenue
    revenue_type='New',       later subscription for customer -> expansion_revenue
    revenue_type='Recurring'  (either case)                   -> renewal_revenue

These three partition every revenue row exactly once, so
new + expansion + renewal == total for every month (checked below).

Run: python src/process_data.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from customer_status import monthly_customer_status
from db import get_engine
from db_writer import write_table

PLAN_TIER_ORDER = {"Starter": 1, "Professional": 2, "Business": 3, "Enterprise": 4}


def month_floor(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s).dt.to_period("M").dt.to_timestamp()


# --- cleaning: raw_* -> processed dim_/fact_ tables --------------------------

def clean_customers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    split = df["industryregion"].str.rsplit(" - ", n=1, expand=True)
    df["industry"] = split[0].str.strip()
    df["region"] = split[1].str.strip()
    df["acquisition_date"] = pd.to_datetime(df["acquisition_date"])
    df = df.rename(columns={"customer_segment": "segment"})
    return df[["customer_id", "customer_name", "industry", "region", "segment", "acquisition_date"]]


def clean_product_plans(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    family_tier = df["plan_name"].str.rsplit(" - ", n=1, expand=True)
    df["product_family"] = family_tier[0].str.strip()
    df["plan_tier_name"] = family_tier[1].str.strip()
    df["plan_tier_order"] = df["plan_tier_name"].map(PLAN_TIER_ORDER)
    df["price"] = df["price"].astype(float)
    return df[[
        "plan_id", "product_id", "product_family", "plan_name",
        "plan_tier_name", "plan_tier_order", "billing_frequency", "price",
    ]]


def clean_subscriptions(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"] = pd.to_datetime(df["end_date"])
    df["renewal_date"] = pd.to_datetime(df["renewal_date"])
    df["mrr"] = df["mrr"].astype(float)
    df["arr"] = df["arr"].astype(float)
    df["status"] = df["status"].str.strip()
    return df


def clean_revenue(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["revenue_date"] = pd.to_datetime(df["revenue_date"])
    for col in ["gross_revenue", "discount", "refund", "net_revenue"]:
        df[col] = df[col].astype(float)
    df["revenue_type"] = df["revenue_type"].str.strip()
    return df


def clean_usage(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["usage_date"] = pd.to_datetime(df["usage_date"])
    for col in ["active_users", "login_count", "session_count", "feature_usage", "api_calls"]:
        df[col] = df[col].astype(int)
    return df


def clean_churn(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["churn_date"] = pd.to_datetime(df["churn_date"])
    df["mrr_lost"] = df["mrr_lost"].astype(float)
    df["churn_reason"] = df["churn_reason"].str.strip()
    return df


def clean_pipeline(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["expected_close_date"] = pd.to_datetime(df["expected_close_date"])
    df["deal_value"] = df["deal_value"].astype(float)
    df["probability"] = df["probability"].astype(float)
    df["stage"] = df["stage"].str.strip()
    return df


def clean_support_tickets(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["created_date"] = pd.to_datetime(df["created_date"])
    df["resolved_date"] = pd.to_datetime(df["resolved_date"])
    df["priority"] = df["priority"].str.strip()
    df["category"] = df["category"].str.strip()
    return df


# --- monthly_revenue_summary --------------------------------------------------

def build_monthly_revenue_summary(
    subscriptions: pd.DataFrame, revenue: pd.DataFrame, churn: pd.DataFrame,
    usage: pd.DataFrame, pipeline: pd.DataFrame,
) -> pd.DataFrame:
    months = pd.date_range(
        month_floor(revenue["revenue_date"]).min(), month_floor(revenue["revenue_date"]).max(), freq="MS"
    )

    # revenue attribution
    sub_sorted = subscriptions.sort_values(["customer_id", "start_date"]).copy()
    sub_sorted["is_first_for_customer"] = ~sub_sorted.duplicated("customer_id", keep="first")
    rev = revenue.merge(
        sub_sorted[["subscription_id", "is_first_for_customer"]], on="subscription_id", how="left"
    )
    rev["month"] = month_floor(rev["revenue_date"])

    is_new_sub = rev["revenue_type"] == "New"
    is_first = rev["is_first_for_customer"]
    category = np.select(
        [is_new_sub & is_first, is_new_sub & ~is_first, ~is_new_sub],
        ["new", "expansion", "renewal"],
        default="unknown",
    )
    rev["category"] = category
    rev_by_month = rev.pivot_table(index="month", columns="category", values="net_revenue", aggfunc="sum", fill_value=0.0)
    rev_by_month = rev_by_month.reindex(months, fill_value=0.0)
    rev_by_month["total_revenue"] = rev_by_month.get("new", 0) + rev_by_month.get("expansion", 0) + rev_by_month.get("renewal", 0)
    rev_by_month = rev_by_month.rename(columns={"new": "new_revenue", "expansion": "expansion_revenue", "renewal": "renewal_revenue"})

    # churn revenue (MRR lost that month)
    churn_month = month_floor(churn["churn_date"])
    churn_revenue = churn.assign(month=churn_month).groupby("month")["mrr_lost"].sum().reindex(months, fill_value=0.0)

    # MRR/ARR month-end snapshot
    mrr_rows = []
    for month in months:
        month_end = month + pd.offsets.MonthEnd(0)
        active = subscriptions[
            (subscriptions["start_date"] <= month_end)
            & (subscriptions["end_date"].isna() | (subscriptions["end_date"] >= month_end))
        ]
        mrr_rows.append({"month": month, "mrr": active["mrr"].sum()})
    mrr_df = pd.DataFrame(mrr_rows).set_index("month")
    mrr_df["arr"] = mrr_df["mrr"] * 12

    # customer counts
    cust_status = monthly_customer_status(subscriptions, months).set_index("month")

    # usage
    usage_month = month_floor(usage["usage_date"])
    usage_agg = usage.assign(month=usage_month).groupby("month").agg(
        avg_active_users=("active_users", "mean"),
        total_login_count=("login_count", "sum"),
        avg_feature_usage=("feature_usage", "mean"),
        total_api_calls=("api_calls", "sum"),
        usage_customer_count=("customer_id", "nunique"),
    ).reindex(months, fill_value=0.0)

    # sales pipeline
    pipe_month = month_floor(pipeline["expected_close_date"])
    pipe = pipeline.assign(month=pipe_month)
    closed = pipe["stage"].isin(["Closed Won", "Closed Lost"])
    pipe_agg = pipe.groupby("month").apply(
        lambda g: pd.Series({
            "pipeline_open_count": (~g["stage"].isin(["Closed Won", "Closed Lost"])).sum(),
            "pipeline_open_value": g.loc[~g["stage"].isin(["Closed Won", "Closed Lost"]), "deal_value"].sum(),
            "pipeline_weighted_value": (g["deal_value"] * g["probability"]).sum(),
            "deals_won": (g["stage"] == "Closed Won").sum(),
            "deals_lost": (g["stage"] == "Closed Lost").sum(),
            "won_value": g.loc[g["stage"] == "Closed Won", "deal_value"].sum(),
        }),
        include_groups=False,
    ).reindex(months, fill_value=0.0)
    pipe_agg["win_rate"] = np.where(
        (pipe_agg["deals_won"] + pipe_agg["deals_lost"]) > 0,
        pipe_agg["deals_won"] / (pipe_agg["deals_won"] + pipe_agg["deals_lost"]),
        np.nan,
    )

    summary = (
        rev_by_month[["total_revenue", "new_revenue", "renewal_revenue", "expansion_revenue"]]
        .join(churn_revenue.rename("churn_revenue"))
        .join(cust_status)
        .join(mrr_df)
        .join(usage_agg)
        .join(pipe_agg)
    )
    summary.index.name = "month"
    return summary.reset_index()


def main():
    engine = get_engine()

    raw = {
        "customer": pd.read_sql("SELECT * FROM raw_dim_customer", engine),
        "product_plan": pd.read_sql("SELECT * FROM raw_dim_product_plan", engine),
        "subscription": pd.read_sql("SELECT * FROM raw_fact_subscription", engine),
        "revenue": pd.read_sql("SELECT * FROM raw_fact_revenue", engine),
        "usage": pd.read_sql("SELECT * FROM raw_fact_customer_usage", engine),
        "churn": pd.read_sql("SELECT * FROM raw_fact_churn", engine),
        "pipeline": pd.read_sql("SELECT * FROM raw_fact_sales_pipeline", engine),
        "support_ticket": pd.read_sql("SELECT * FROM raw_fact_support_ticket", engine),
    }

    cleaned = {
        "dim_customer": clean_customers(raw["customer"]),
        "dim_product_plan": clean_product_plans(raw["product_plan"]),
        "fact_subscription": clean_subscriptions(raw["subscription"]),
        "fact_revenue": clean_revenue(raw["revenue"]),
        "fact_customer_usage": clean_usage(raw["usage"]),
        "fact_churn": clean_churn(raw["churn"]),
        "fact_sales_pipeline": clean_pipeline(raw["pipeline"]),
        "fact_support_ticket": clean_support_tickets(raw["support_ticket"]),
    }

    print("Writing processed tables to MySQL...")
    for table_name, df in cleaned.items():
        n = write_table(df, table_name, engine)
        print(f"  {table_name:<24} {n:>6,} rows")

    summary = build_monthly_revenue_summary(
        cleaned["fact_subscription"], cleaned["fact_revenue"], cleaned["fact_churn"],
        cleaned["fact_customer_usage"], cleaned["fact_sales_pipeline"],
    )
    n = write_table(summary, "monthly_revenue_summary", engine)
    print(f"  {'monthly_revenue_summary':<24} {n:>6,} rows")

    # sanity check: total_revenue should equal new+expansion+renewal, and match raw net_revenue sum
    reconciled = np.allclose(
        summary["total_revenue"],
        summary["new_revenue"] + summary["expansion_revenue"] + summary["renewal_revenue"],
    )
    raw_total = cleaned["fact_revenue"]["net_revenue"].sum()
    summary_total = summary["total_revenue"].sum()
    print(f"\nRevenue partition reconciles: {reconciled}")
    print(f"Raw net_revenue total: ${raw_total:,.2f}  |  Summary total_revenue sum: ${summary_total:,.2f}  "
          f"|  match: {np.isclose(raw_total, summary_total)}")

    pd.set_option("display.width", 200)
    print("\nmonthly_revenue_summary tail:")
    print(summary[["month", "total_revenue", "new_revenue", "expansion_revenue", "renewal_revenue",
                    "churn_revenue", "mrr", "arr", "active_customers"]].tail(6).to_string(index=False))

    engine.dispose()


if __name__ == "__main__":
    main()
