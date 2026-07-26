"""Business Overview — CloudFlow company overview, business model, and data model explainer.

The landing page: pure documentation, no new metrics logic, no changes to Dashboard/Forecast.
Live numbers (customer/plan/subscription counts, total revenue, date range,
churned customers, per-table row counts) are pulled from the same MySQL
tables the rest of the app reads, via src/data_access.py — nothing here is
hardcoded.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from customer_status import fully_churned_customer_count  # noqa: E402
from data_access import (  # noqa: E402
    DataUnavailableError, filter_options, get_table_row_counts, load_dashboard_frames,
)
from theme import get_palette, kpi_card, page_header, panel_header, panel_start  # noqa: E402

TABLE_INFO = [
    ("dim_customer", "Customer profile — company name, industry, region, segment, and signup date. One row per customer."),
    ("dim_product_plan", "The product catalog — every plan across all product families, tiers, and billing frequencies, with list price."),
    ("fact_subscription", "Subscription contracts — plan, seats, start/end dates, status, and contracted MRR/ARR. One row per subscription."),
    ("fact_revenue", "Billed revenue transactions — gross, discount, refund, and net revenue, flagged as a new or recurring charge."),
    ("fact_customer_usage", "Monthly product usage per customer — active users, logins, sessions, feature usage, API calls."),
    ("fact_churn", "Subscription cancellations — churn date, reason, and MRR lost. One row per cancelled subscription."),
    ("fact_sales_pipeline", "Sales opportunities — deal stage, value, and win probability, for tracking the sales funnel."),
    ("fact_support_ticket", "Customer support tickets — priority, category, and resolution time."),
]

CAPABILITIES = [
    ("📊", "Current Business Dashboard", "Live KPIs and trend charts — revenue, MRR, ARR, active/new/churned customers — filterable by date range, segment, region, and product."),
    ("💰", "Revenue Analysis", "Revenue broken down by type (new, expansion, renewal), customer segment, and product family."),
    ("📈", "Revenue Forecasting", "A 6-month forward revenue forecast with 80% confidence intervals, from a walk-forward-validated model."),
    ("👥", "Customer & Subscription Analysis", "Active, new, and fully-churned customer counts, plus MRR/ARR trends, tracked monthly."),
    ("📉", "Churn Analysis", "Churned customers and MRR lost, tracked over time and broken down by churn reason."),
    ("🖱️", "Usage Data", "Login, session, feature, and API activity is captured per customer per month and available in the database — not yet surfaced as its own dashboard view."),
]


def render():
    palette = get_palette()

    page_header(
        "Company", "Business Overview",
        "Who CloudFlow is, how it makes money, and the data model behind every number in this app.",
    )

    try:
        with st.spinner("Loading data from MySQL..."):
            customers, plans, subscriptions, revenue, churn = load_dashboard_frames()
    except DataUnavailableError as e:
        st.error(f"Couldn't load dataset overview. {e}")
        st.stop()

    counts = get_table_row_counts()
    opts = filter_options(customers, plans, revenue)
    total_revenue = float(revenue["net_revenue"].sum())
    churned_customers = fully_churned_customer_count(subscriptions)

    industries = sorted(customers["industry"].dropna().unique().tolist())
    regions = sorted(customers["region"].dropna().unique().tolist())
    product_families = sorted(plans["product_family"].dropna().unique().tolist())
    tiers = sorted(plans[["plan_tier_name", "plan_tier_order"]].drop_duplicates().itertuples(index=False), key=lambda r: r.plan_tier_order)
    tier_names = [t.plan_tier_name for t in tiers]

    # --- hero: CloudFlow ------------------------------------------------------------

    with st.container(key="about-hero"):
        st.markdown(
            f"""
            <div class="page-eyebrow" style="color:rgba(255,255,255,0.85);">B2B SaaS · Fictional company</div>
            <div style="font-size:2.3rem; font-weight:800; color:white; margin: 4px 0 8px 0;">CloudFlow</div>
            <div style="color:rgba(255,255,255,0.9); font-size:0.98rem; max-width: 820px; line-height:1.6;">
                CloudFlow is a workflow automation and analytics platform for growing teams, sold as
                {', '.join(product_families[:-1])}{' and ' if len(product_families) > 1 else ''}{product_families[-1] if product_families else ''} —
                three integrated product lines available in {len(tier_names)} tiers
                ({', '.join(tier_names)}). Every number in this app — revenue, MRR, forecasts, churn —
                is generated from CloudFlow's simulated customer, subscription, and revenue data.
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")
    st.write("")

    # --- dataset overview -------------------------------------------------------------

    st.markdown("<div class='section-title' style='margin-bottom:10px;'>Dataset overview</div>", unsafe_allow_html=True)
    row1 = st.columns(3)
    with row1[0]:
        kpi_card("about-customers", "Customers", f"{counts['dim_customer']:,}", sparkline_color=palette.accent_purple)
    with row1[1]:
        kpi_card("about-plans", "Products & Plans", f"{counts['dim_product_plan']:,}", sparkline_color=palette.accent_blue)
    with row1[2]:
        kpi_card("about-subs", "Subscriptions", f"{counts['fact_subscription']:,}", sparkline_color=palette.accent_cyan)

    st.write("")
    row2 = st.columns(3)
    with row2[0]:
        kpi_card("about-revenue", "Total Revenue (all-time)", f"${total_revenue:,.0f}", sparkline_color=palette.positive)
    with row2[1]:
        kpi_card("about-daterange", "Date Range", f"{opts['min_month']:%b %Y} – {opts['max_month']:%b %Y}", sparkline_color=palette.accent_blue)
    with row2[2]:
        kpi_card("about-churned", "Churned Customers", f"{churned_customers:,}", sparkline_color=palette.negative)

    st.write("")
    st.write("")

    # --- company overview + business model ---------------------------------------------

    col_a, col_b = st.columns(2)
    with col_a:
        with panel_start("company-overview"):
            panel_header("Company Overview")
            st.markdown(
                f"""
                <div class="prose">
                <p><strong>CloudFlow</strong> is a fictional <strong>B2B SaaS</strong> company that sells a
                workflow automation and analytics platform to teams and organizations.</p>
                <p>Its customers span industries including {', '.join(industries[:6])}{', and others' if len(industries) > 6 else ''},
                across {len(regions)} regions ({', '.join(regions)}), and are grouped into four segments —
                <strong>Startup, SMB, Mid-Market, and Enterprise</strong> — based on company size.</p>
                <p>CloudFlow generates revenue entirely through <strong>recurring subscription fees</strong>.
                Customers pay monthly or annually for one or more of its product lines, priced by plan tier
                and number of seats.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with col_b:
        with panel_start("business-model"):
            panel_header("Business Model")
            st.markdown(
                f"""
                <div class="prose">
                <ul>
                <li><strong>Subscriptions &amp; plans</strong> — each customer subscribes to one or more product lines
                ({', '.join(product_families)}), each available in {len(tier_names)} tiers, billed monthly or annually.</li>
                <li><strong>MRR</strong> (Monthly Recurring Revenue) — the total contracted monthly value of every
                currently active subscription.</li>
                <li><strong>ARR</strong> (Annual Recurring Revenue) — MRR annualized (MRR × 12).</li>
                <li><strong>Renewals</strong> — recurring subscriptions bill automatically each period until
                cancelled; most revenue comes from renewals of existing subscriptions.</li>
                <li><strong>Upgrades &amp; downgrades</strong> — customers can add seats or move to a higher tier
                (expansion revenue), or reduce seats/tier (contraction) at any time.</li>
                <li><strong>Churn</strong> — a customer is only counted as fully churned once <em>every</em>
                subscription they hold has ended; losing one product while keeping another is a downgrade,
                not churn.</li>
                </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.write("")

    # --- data sources --------------------------------------------------------------------

    with panel_start("data-sources"):
        panel_header("Data Sources", "The 8 tables behind every chart and KPI in this app")
        for row_start in range(0, len(TABLE_INFO), 4):
            cols = st.columns(4)
            for col, (name, desc) in zip(cols, TABLE_INFO[row_start:row_start + 4]):
                with col:
                    st.markdown(
                        f"""
                        <div class="source-card">
                            <span class="source-count">{counts.get(name, 0):,} rows</span>
                            <div class="source-name">{name}</div>
                            <div class="source-desc">{desc}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            st.write("")

    st.write("")

    # --- data flow diagram -----------------------------------------------------------------

    with panel_start("data-flow"):
        panel_header("How the data connects", "Two dimension tables describe who/what; every fact table hangs off the subscription")
        st.markdown(
            """
            <div class="flow-row">
                <div class="flow-box dim">dim_customer<span class="flow-sub">Who the customer is</span></div>
                <div class="flow-box dim">dim_product_plan<span class="flow-sub">What they can buy</span></div>
            </div>
            <div class="flow-arrow">↓</div>
            <div class="flow-row">
                <div class="flow-box core">fact_subscription<span class="flow-sub">The contract: plan + seats + start/end date</span></div>
            </div>
            <div class="flow-arrow">↓</div>
            <div class="flow-row">
                <div class="flow-box fact">fact_revenue<span class="flow-sub">Billed $</span></div>
                <div class="flow-box fact">fact_churn<span class="flow-sub">Cancellations</span></div>
                <div class="flow-box fact">fact_customer_usage<span class="flow-sub">Product activity</span></div>
                <div class="flow-box fact">fact_sales_pipeline<span class="flow-sub">Deals in progress</span></div>
                <div class="flow-box fact">fact_support_ticket<span class="flow-sub">Support load</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")

    # --- analytics capabilities --------------------------------------------------------------

    with panel_start("capabilities"):
        panel_header("Analytics Capabilities", "What this application supports today")
        for row_start in range(0, len(CAPABILITIES), 3):
            cols = st.columns(3)
            for col, (icon, title, desc) in zip(cols, CAPABILITIES[row_start:row_start + 3]):
                with col:
                    st.markdown(
                        f"""
                        <div class="source-card">
                            <div class="source-name" style="color:{palette.text_primary}; font-family:'Inter',sans-serif;">
                                {icon} {title}
                            </div>
                            <div class="source-desc">{desc}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            st.write("")
