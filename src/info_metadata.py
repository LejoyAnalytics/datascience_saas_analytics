"""
Centralized metadata for every KPI/chart/table's "ⓘ" info panel.

This is the single source of truth the InfoModal (src/info_panel.py) renders
from — one entry per visual, keyed by the same visual_id used when placing
the InfoButton. Every field here describes the code as actually written in
src/data_access.py, src/customer_status.py, src/process_data.py,
src/train_model.py, src/evaluate_model.py, and src/forecast.py — if that
code changes, update the matching entry here rather than letting it drift.

Values that change at runtime (current filter selections, which model won,
its live MAE/RMSE/MAPE, the actual backtest window) are NOT hardcoded here —
they're passed in separately as `context`/`extra` at render time by the
views, sourced from the same data_access.py calls that power the visual
itself. This file only holds the static facts: which tables, which columns,
which formula.
"""

from __future__ import annotations

_DASHBOARD_FILTERS = ["Date range", "Customer segment", "Region", "Product / plan"]

DASHBOARD_INFO: dict[str, dict] = {
    "kpi-total-revenue": {
        "title": "Total Revenue",
        "represents": "Sum of recognized net revenue across all customers, for the selected date range and filters.",
        "source_tables": ["fact_revenue"],
        "columns_used": ["net_revenue", "revenue_date", "customer_id", "subscription_id"],
        "formula": "SUM(net_revenue)\nWHERE revenue_date BETWEEN <start_month> AND <end_month>\n  AND customer_id IN (customers matching segment/region filters)\n  AND subscription_id IN (subscriptions matching product/plan filter)",
        "aggregation": "Summed across the entire selected date range (not a monthly average).",
        "filters_applied": _DASHBOARD_FILTERS,
        "assumptions": [
            "net_revenue = gross_revenue − discount − refund, computed upstream when fact_revenue was built (src/process_data.py).",
            "A revenue row is included only if it matches ALL active filters at once (AND logic across segment, region, and product).",
            "The trend badge compares the last two months of the filtered monthly series, not the raw KPI total.",
        ],
        "code_ref": "src/data_access.py -> apply_filters(), kpi_summary()",
    },
    "kpi-mrr": {
        "title": "Current MRR",
        "represents": "Monthly Recurring Revenue: the sum of each active subscription's contracted mrr, as of the end of the last month in the selected date range.",
        "source_tables": ["fact_subscription"],
        "columns_used": ["mrr", "start_date", "end_date", "customer_id", "plan_id"],
        "formula": "SUM(mrr)\nWHERE start_date <= month_end\n  AND (end_date IS NULL OR end_date >= month_end)",
        "aggregation": "Point-in-time snapshot at the end of the last selected month — not summed across months.",
        "filters_applied": _DASHBOARD_FILTERS,
        "assumptions": [
            "mrr is the subscription's stored contracted monthly value (fact_subscription.mrr) — it is not recomputed from billed revenue transactions.",
            "A subscription with a NULL end_date is treated as still active.",
        ],
        "code_ref": "src/data_access.py -> _mrr_snapshot()",
    },
    "kpi-arr": {
        "title": "Current ARR",
        "represents": "Annual Recurring Revenue — the current MRR snapshot annualized.",
        "source_tables": ["fact_subscription"],
        "columns_used": ["mrr", "start_date", "end_date"],
        "formula": "ARR = Current MRR x 12",
        "aggregation": "Point-in-time snapshot, same month as Current MRR.",
        "filters_applied": _DASHBOARD_FILTERS,
        "assumptions": [
            "Simple x12 annualization of the MRR snapshot — does not separately model annual-billing discounts beyond what's already baked into the stored mrr value.",
        ],
        "code_ref": "src/data_access.py -> _mrr_snapshot()",
    },
    "kpi-active-customers": {
        "title": "Active Customers",
        "represents": "Distinct customers holding at least one subscription that overlaps the last month of the selected date range.",
        "source_tables": ["fact_subscription", "dim_customer", "dim_product_plan"],
        "columns_used": ["fact_subscription.customer_id", "fact_subscription.start_date", "fact_subscription.end_date", "dim_customer.segment", "dim_customer.region", "dim_product_plan.product_family"],
        "formula": "COUNT(DISTINCT customer_id)\nWHERE start_date <= month_end AND (end_date IS NULL OR end_date >= month_start)",
        "aggregation": "Point-in-time snapshot at the end of the last selected month.",
        "filters_applied": _DASHBOARD_FILTERS,
        "assumptions": [
            "A customer with subscriptions to multiple products is counted once, as long as at least one qualifying subscription is active.",
            "Subscriptions are pre-filtered to matching segment/region/product before this count runs, so 'active' means active *within the current filter scope*.",
        ],
        "code_ref": "src/customer_status.py -> monthly_customer_status() (active_customers)",
    },
    "kpi-new-customers": {
        "title": "New Customers",
        "represents": "Customers whose very first subscription (earliest start_date across all of their subscriptions) falls within the selected date range, summed across all months in range.",
        "source_tables": ["fact_subscription"],
        "columns_used": ["customer_id", "start_date"],
        "formula": "COUNT(customer_id) WHERE MIN(start_date) BETWEEN month_start AND month_end\n(summed across every month in the selected range)",
        "aggregation": "Monthly count, summed over the selected date range.",
        "filters_applied": _DASHBOARD_FILTERS,
        "assumptions": [
            "\"New\" is defined at the customer level (first-ever subscription) — a second product purchased by an existing customer does not count as new.",
        ],
        "code_ref": "src/customer_status.py -> monthly_customer_status() (new_customers)",
    },
    "kpi-churned-customers": {
        "title": "Churned Customers",
        "represents": "Customers with NO remaining active subscription as of a given month — full logo loss, not a single cancelled/downgraded product.",
        "source_tables": ["fact_subscription"],
        "columns_used": ["customer_id", "start_date", "end_date"],
        "formula": "A customer is churned in month M if EVERY one of their subscriptions has an end_date,\nand MAX(end_date) falls within month M.",
        "aggregation": "Monthly count, summed over the selected date range.",
        "filters_applied": _DASHBOARD_FILTERS,
        "assumptions": [
            "A customer who cancels one product but keeps another active subscription is NOT counted as churned.",
            "This is a \"lower is better\" metric — the trend badge is inverted, so an increase shows as negative (red).",
        ],
        "code_ref": "src/customer_status.py -> monthly_customer_status() (churned_customers)",
    },
    "kpi-churned-revenue": {
        "title": "Churned Revenue (MRR lost)",
        "represents": "Total MRR lost from subscription-cancellation events recorded in fact_churn, within the selected date range.",
        "source_tables": ["fact_churn"],
        "columns_used": ["mrr_lost", "churn_date", "customer_id", "subscription_id"],
        "formula": "SUM(mrr_lost) WHERE churn_date BETWEEN <start_month> AND <end_month>",
        "aggregation": "Summed across the selected date range.",
        "filters_applied": _DASHBOARD_FILTERS,
        "assumptions": [
            "mrr_lost is recorded once per cancelled subscription, at cancellation time — it's the subscription's mrr at the moment it churned, not a recomputed value.",
            "This is a \"lower is better\" metric — the trend badge is inverted.",
        ],
        "code_ref": "src/data_access.py -> kpi_summary() (churned_revenue)",
    },
    "chart-revenue-trend": {
        "title": "Revenue Trend",
        "represents": "Total recognized revenue per month, for the selected date range and filters.",
        "source_tables": ["fact_revenue"],
        "columns_used": ["net_revenue", "revenue_date"],
        "formula": "GROUP BY month(revenue_date): SUM(net_revenue)",
        "aggregation": "Monthly.",
        "filters_applied": _DASHBOARD_FILTERS,
        "assumptions": ["Same filtered revenue rows as the Total Revenue KPI, broken out by month instead of summed."],
        "code_ref": "src/data_access.py -> monthly_series() (total_revenue column)",
    },
    "chart-mrr-trend": {
        "title": "MRR Trend",
        "represents": "MRR snapshot (sum of active subscriptions' mrr) at the end of each month across the selected date range.",
        "source_tables": ["fact_subscription"],
        "columns_used": ["mrr", "start_date", "end_date"],
        "formula": "For each month M: SUM(mrr) WHERE start_date <= month_end(M) AND (end_date IS NULL OR end_date >= month_end(M))",
        "aggregation": "Monthly snapshots.",
        "filters_applied": _DASHBOARD_FILTERS,
        "code_ref": "src/data_access.py -> _mrr_snapshot()",
    },
    "chart-active-trend": {
        "title": "Active Customers Over Time",
        "represents": "Count of customers with an overlapping active subscription, at the end of each month across the selected date range.",
        "source_tables": ["fact_subscription"],
        "columns_used": ["customer_id", "start_date", "end_date"],
        "aggregation": "Monthly snapshots.",
        "filters_applied": _DASHBOARD_FILTERS,
        "code_ref": "src/customer_status.py -> monthly_customer_status()",
    },
    "chart-new-vs-churned": {
        "title": "New vs. Churned Customers",
        "represents": "New customers (first-ever subscription started that month) vs. fully churned customers (last remaining subscription ended that month), grouped by month.",
        "source_tables": ["fact_subscription"],
        "columns_used": ["customer_id", "start_date", "end_date"],
        "aggregation": "Monthly counts.",
        "filters_applied": _DASHBOARD_FILTERS,
        "code_ref": "src/customer_status.py -> monthly_customer_status()",
    },
    "chart-revenue-by-type": {
        "title": "Revenue by Type",
        "represents": "Monthly revenue split into New / Expansion / Renewal.",
        "source_tables": ["fact_revenue", "fact_subscription"],
        "columns_used": ["revenue_type", "net_revenue", "revenue_date", "subscription_id", "customer_id", "start_date"],
        "formula": (
            "New       = rows where revenue_type='New' on a customer's FIRST-EVER subscription\n"
            "Expansion = rows where revenue_type='New' on an ADDITIONAL subscription (cross-sell/upsell)\n"
            "Renewal   = all rows where revenue_type='Recurring' (ongoing billing of an existing subscription)"
        ),
        "aggregation": "Monthly, stacked by category.",
        "filters_applied": _DASHBOARD_FILTERS,
        "assumptions": [
            "Category logic depends on fact_revenue.revenue_type being exactly 'New' or 'Recurring', as written by the ingestion pipeline.",
            "\"First-ever subscription\" is determined by the earliest start_date per customer among the currently filtered subscriptions.",
        ],
        "code_ref": "src/data_access.py -> _revenue_category_breakdown()",
    },
    "chart-revenue-by-segment": {
        "title": "Revenue by Customer Segment",
        "represents": "Total net revenue for the selected date range, grouped by customer segment.",
        "source_tables": ["fact_revenue", "dim_customer"],
        "columns_used": ["fact_revenue.net_revenue", "dim_customer.segment"],
        "formula": "JOIN fact_revenue -> dim_customer ON customer_id\nGROUP BY segment: SUM(net_revenue)",
        "aggregation": "Summed across the selected date range, one bar per segment.",
        "filters_applied": _DASHBOARD_FILTERS,
        "assumptions": ["If a Customer Segment filter is already applied, this chart will only show the selected segment(s)."],
        "code_ref": "src/data_access.py -> revenue_by_segment()",
    },
    "chart-revenue-by-product": {
        "title": "Revenue by Product",
        "represents": "Total net revenue for the selected date range, grouped by product family.",
        "source_tables": ["fact_revenue", "fact_subscription", "dim_product_plan"],
        "columns_used": ["fact_revenue.net_revenue", "fact_subscription.plan_id", "dim_product_plan.product_family"],
        "formula": "JOIN fact_revenue -> fact_subscription -> dim_product_plan\nGROUP BY product_family: SUM(net_revenue)",
        "aggregation": "Summed across the selected date range, one bar per product family.",
        "filters_applied": _DASHBOARD_FILTERS,
        "code_ref": "src/data_access.py -> revenue_by_product()",
    },
}

FORECAST_INFO: dict[str, dict] = {
    "forecast-hero": {
        "title": "Next Month Forecast",
        "represents": "The next month's point forecast, its growth vs. the prior month, its 80% confidence interval, and the model that produced it — read directly from the earliest row of the stored revenue_forecast table.",
        "source_tables": ["revenue_forecast"],
        "columns_used": ["forecast_month", "predicted_revenue", "lower_bound", "upper_bound", "forecast_growth", "model_name", "model_version"],
        "formula": "growth = (predicted_revenue[t] − previous_value[t-1]) / previous_value[t-1] x 100\n(previous_value is the last ACTUAL month for the 1st forecast month, then the PRIOR forecast for later months)",
        "aggregation": "Single month (first row of the 6-month forecast horizon).",
        "filters_applied": ["None — this page has no filters; it always shows the full stored forecast."],
        "assumptions": ["The forecast is generated by src/forecast.py and stored in MySQL; this card only reads it, it never recomputes it."],
        "is_forecast": True,
        "interval_logic": (
            "lower/upper = predicted_revenue ± z x residual_std x sqrt(step)\n\n"
            "- z = 1.2816 (80% confidence, norm.ppf(0.9))\n"
            "- residual_std = std of (actual − predicted) from the winning model's 12-month walk-forward backtest\n"
            "- step = months-ahead (1..6) — uncertainty widens further into the future"
        ),
        "code_ref": "src/forecast.py -> build_revenue_forecast()",
    },
    "kpi-mae": {
        "title": "Mean Absolute Error (MAE)",
        "represents": "Average absolute dollar error of the winning model's one-month-ahead predictions during its 12-month walk-forward backtest.",
        "source_tables": ["model_evaluation_metrics"],
        "columns_used": ["mae", "model_name", "is_best"],
        "formula": "MAE = mean(|actual − predicted|) across the 12 backtest months",
        "aggregation": "Single value per model, over the 12-month backtest window.",
        "filters_applied": ["None — this page has no filters."],
        "is_forecast": True,
        "code_ref": "src/evaluate_model.py -> mae()",
    },
    "kpi-rmse": {
        "title": "Root Mean Squared Error (RMSE)",
        "represents": "Root-mean-squared dollar error of the winning model's one-month-ahead predictions during its 12-month walk-forward backtest. Penalizes large misses more than MAE.",
        "source_tables": ["model_evaluation_metrics"],
        "columns_used": ["rmse", "model_name", "is_best"],
        "formula": "RMSE = sqrt(mean((actual − predicted)^2)) across the 12 backtest months",
        "aggregation": "Single value per model, over the 12-month backtest window.",
        "filters_applied": ["None — this page has no filters."],
        "is_forecast": True,
        "code_ref": "src/evaluate_model.py -> rmse()",
    },
    "kpi-mape": {
        "title": "Mean Absolute Percentage Error (MAPE)",
        "represents": "Average absolute percentage error of the winning model's one-month-ahead predictions. This is the metric used to pick the winning model (lowest MAPE).",
        "source_tables": ["model_evaluation_metrics"],
        "columns_used": ["mape", "model_name", "is_best"],
        "formula": "MAPE = mean(|(actual − predicted) / actual|) x 100 across the 12 backtest months",
        "aggregation": "Single value per model, over the 12-month backtest window.",
        "filters_applied": ["None — this page has no filters."],
        "is_forecast": True,
        "code_ref": "src/evaluate_model.py -> mape()",
    },
    "chart-hist-vs-forecast": {
        "title": "Historical vs. Forecasted Revenue",
        "represents": "Actual recognized revenue through the last observed month, followed by the stored 6-month forecast with its 80% confidence band.",
        "source_tables": ["monthly_revenue_summary", "revenue_forecast"],
        "columns_used": ["monthly_revenue_summary.total_revenue", "monthly_revenue_summary.month", "revenue_forecast.predicted_revenue", "revenue_forecast.lower_bound", "revenue_forecast.upper_bound"],
        "aggregation": "Monthly — actuals from monthly_revenue_summary, forecast from revenue_forecast.",
        "filters_applied": ["None — this page has no filters; it always shows the full stored history and forecast."],
        "is_forecast": True,
        "code_ref": "views/forecast.py -> render()",
    },
    "panel-model-accuracy": {
        "title": "Model Accuracy Comparison",
        "represents": "Backtest accuracy of every candidate model (table), plus the winning model's actual-vs-predicted values for each of the 12 backtest months (chart).",
        "source_tables": ["model_evaluation_metrics", "historical_vs_predicted"],
        "columns_used": ["model_name", "mae", "rmse", "mape", "is_best", "month", "actual_revenue", "predicted_revenue"],
        "formula": "See MAE / RMSE / MAPE cards above for each metric's formula.",
        "aggregation": "One row per candidate model; backtest chart is monthly over the last 12 months.",
        "filters_applied": ["None — this page has no filters."],
        "assumptions": [
            "Backtest methodology: walk-forward / expanding-window. For each of the last 12 months, every model is fit (tree models are retrained) using only data strictly BEFORE that month, predicts that one month, then the window advances by one month and repeats.",
            "This yields 12 independent one-month-ahead predictions per model, so accuracy reflects genuine out-of-sample performance, not in-sample fit.",
            "Candidate models: naive, seasonal_naive, moving_avg_3, drift, holt_linear (classical/statsmodels), xgboost, lightgbm (gradient-boosted trees).",
            "Tree models (xgboost, lightgbm) use every column in ml_feature_table except month and total_revenue: revenue lags (1/2/3/6/12 months), rolling mean/std (3/6/12 months), MoM/YoY growth, and MRR/ARR/customer/usage/pipeline metrics — every one of those columns is shifted one month behind the target so the model can never see the future. Baseline/classical models use only the total_revenue series itself.",
        ],
        "is_forecast": True,
        "code_ref": "src/train_model.py -> walk_forward_backtest(); src/evaluate_model.py -> evaluate_all_models()",
    },
    "table-monthly-forecast": {
        "title": "Monthly Forecast Table",
        "represents": "The full stored 6-month forecast, one row per future month.",
        "source_tables": ["revenue_forecast"],
        "columns_used": ["forecast_month", "predicted_revenue", "lower_bound", "upper_bound", "forecast_growth", "model_name", "model_version", "created_at"],
        "aggregation": "Monthly, one row per forecasted month.",
        "filters_applied": ["None — this page has no filters."],
        "is_forecast": True,
        "code_ref": "src/forecast.py -> build_revenue_forecast(), written via src/db_writer.py write_table()",
    },
}

INFO: dict[str, dict] = {**DASHBOARD_INFO, **FORECAST_INFO}
