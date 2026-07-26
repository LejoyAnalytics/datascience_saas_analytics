"""
Static grounding context for the chatbot: schema description (with actual
column names) and the CloudFlow business narrative.

Kept separate from info_metadata.py — that file drives the UI's per-visual
"ⓘ" explanations for a human reader; the LLM needs raw table/column names
and SQL-writing guidance at a different level of detail.
"""

SCHEMA_DESCRIPTION = """
CloudFlow's data lives in a MySQL/MariaDB database, in three layers.

RAW TABLES (raw_* — near-verbatim CSV loads, one row per source record):
- raw_dim_customer(customer_id, customer_name, industryregion, customer_segment, acquisition_date)
- raw_dim_date(date, month, quarter, year)
- raw_dim_product_plan(product_id, plan_id, plan_name, billing_frequency, price)
- raw_fact_subscription(subscription_id, customer_id, plan_id, start_date, end_date, renewal_date, status, mrr, arr)
- raw_fact_revenue(revenue_id, customer_id, subscription_id, revenue_date, gross_revenue, discount, refund, net_revenue, revenue_type)
- raw_fact_customer_usage(customer_id, usage_date, active_users, login_count, session_count, feature_usage, api_calls)
- raw_fact_churn(customer_id, subscription_id, churn_date, churn_reason, mrr_lost)
- raw_fact_sales_pipeline(opportunity_id, customer_id, expected_close_date, deal_value, stage, probability)
- raw_fact_support_ticket(ticket_id, customer_id, created_date, resolved_date, priority, category, resolution_time)

PROCESSED TABLES (cleaned/typed — prefer these for business questions):
- dim_customer(customer_id, customer_name, industry, region, segment, acquisition_date) — segment is one of Startup/SMB/Mid-Market/Enterprise
- dim_product_plan(plan_id, product_id, product_family, plan_name, plan_tier_name, plan_tier_order, billing_frequency, price) — product_family is Core Platform/Analytics Add-on/Automation Suite; plan_tier_name is Starter/Professional/Business/Enterprise
- fact_subscription(subscription_id, customer_id, plan_id, start_date, end_date, renewal_date, status, mrr, arr) — end_date is NULL while active; status is Active/Churned
- fact_revenue(revenue_id, customer_id, subscription_id, revenue_date, gross_revenue, discount, refund, net_revenue, revenue_type) — net_revenue = gross_revenue - discount - refund; revenue_type is New or Recurring; this is the source of truth for billed revenue
- fact_customer_usage(customer_id, usage_date, active_users, login_count, session_count, feature_usage, api_calls) — one row per customer per month
- fact_churn(customer_id, subscription_id, churn_date, churn_reason, mrr_lost) — one row per subscription cancellation
- fact_sales_pipeline(opportunity_id, customer_id, expected_close_date, deal_value, stage, probability) — stage is Prospecting/Qualification/Needs Analysis/Proposal/Negotiation/Closed Won/Closed Lost
- fact_support_ticket(ticket_id, customer_id, created_date, resolved_date, priority, category, resolution_time)
- monthly_revenue_summary(month, total_revenue, new_revenue, renewal_revenue, expansion_revenue, churn_revenue, active_customers, new_customers, churned_customers, mrr, arr, avg_active_users, total_login_count, avg_feature_usage, total_api_calls, usage_customer_count, pipeline_open_count, pipeline_open_value, pipeline_weighted_value, deals_won, deals_lost, won_value, win_rate) — one row per calendar month; the best table for "revenue over time", "MRR trend", "churned customers per month", "revenue by type", etc. A customer only counts as churned once ALL of their subscriptions have ended.

MODEL / FORECAST TABLES:
- ml_feature_table(month, total_revenue, ...many lagged predictor columns...) — internal model-training features; rarely useful for direct business questions
- model_evaluation_metrics(model_name, mae, rmse, mape, model_version, backtest_start, backtest_end, is_best, evaluated_at) — is_best=1 marks the model actually used for the live forecast; mae/rmse/mape are 12-month backtest accuracy (lower is better)
- historical_vs_predicted(month, actual_revenue, predicted_revenue, model_name, model_version) — the winning model's backtest, actual vs. predicted per month, for accuracy questions
- revenue_forecast(forecast_month, predicted_revenue, lower_bound, upper_bound, forecast_growth, model_name, model_version, created_at) — the actual future forecast (6 months ahead); lower_bound/upper_bound are an 80% confidence interval
- forecast_drivers(driver_name, current_value, prior_value, pct_change, direction, as_of_month, lookback_months) — key business metrics (MRR, ARR, active customers, expansion revenue, churn revenue, usage, pipeline, win rate) vs. 3 months prior, explaining what's moving the forecast

Rules for writing SQL:
- Prefer PROCESSED and MODEL/FORECAST tables over raw_* tables unless the question is explicitly about raw/staging data.
- Write only MySQL/MariaDB-compatible SELECT statements.
- Month columns (monthly_revenue_summary.month, revenue_forecast.forecast_month, etc.) are DATEs equal to the first day of the month.
- "Current revenue" or "latest revenue" means the most recent month in monthly_revenue_summary (MAX(month)).
- "Churned customers" should come from monthly_revenue_summary.churned_customers (summed over the relevant period) or fact_churn — not a naive COUNT of fact_subscription rows with status='Churned', since one customer can hold several subscriptions.
"""

BUSINESS_DESCRIPTION = """
CloudFlow is a fictional B2B SaaS company that sells a workflow automation
and analytics platform to teams and organizations, through three product
lines — Core Platform, Analytics Add-on, and Automation Suite — each
offered in four tiers (Starter, Professional, Business, Enterprise), billed
monthly or annually. Customers are grouped into four segments by company
size (Startup, SMB, Mid-Market, Enterprise) across five regions. CloudFlow
generates revenue entirely through recurring subscription fees (MRR/ARR).
"""
