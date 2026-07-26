# SaaS Revenue Forecast

End-to-end revenue forecasting system for a fictional multi-product B2B SaaS
company. MySQL (MariaDB via XAMPP) is the system of record — CSVs are only
the ingestion source; every downstream stage reads from and writes to the
database, and the dashboard reads only from MySQL's final output tables.

The company sells three product lines (Core Platform, Analytics Add-on,
Automation Suite), each offered in four tiers (Starter/Professional/Business/
Enterprise) with monthly or annual billing, to four customer segments
(Startup/SMB/Mid-Market/Enterprise) across five regions.

## Architecture

```
CSV files (data/raw/)
    -> raw_* tables          [src/ingest_csv.py]
    -> dim_/fact_ tables + monthly_revenue_summary   [src/process_data.py]
    -> ml_feature_table (leak-free, lagged)          [src/feature_engineering.py]
    -> model_evaluation_metrics                      [src/evaluate_model.py]
    -> historical_vs_predicted, revenue_forecast,
       forecast_drivers                              [src/forecast.py]
    -> src/data_access.py (query/aggregation layer, reads MySQL only)
    -> app.py + views/ (Streamlit dashboard, dark-mode SaaS UI)
```

Database: `saas_revenue_forecast` on a local MariaDB (XAMPP), reachable via
phpMyAdmin at `http://localhost/phpmyadmin`. Connection settings default to
XAMPP's `root` / no-password local instance — override with a `.env` file
(`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`; see `src/db.py`).

## Project Structure

```
.
├── data/raw/                    # Source CSVs (dim_*, fact_*) — immutable, ingested into MySQL
├── .streamlit/config.toml         # Dark theme config for the dashboard
├── src/
│   ├── db.py                      # Database connection/config
│   ├── db_writer.py               # Shared MySQL write helpers
│   ├── ingest_csv.py               # Phase 1: create DB + raw tables, load CSVs, validate
│   ├── process_data.py             # Phase 2: clean into dim_/fact_ tables + monthly_revenue_summary
│   ├── customer_status.py          # Shared active/new/churned-customer logic
│   ├── feature_engineering.py      # Phase 3: leak-free ml_feature_table
│   ├── train_model.py               # Model definitions + walk-forward backtest engine
│   ├── evaluate_model.py            # Phase 4: score all models, pick the best
│   ├── forecast.py                  # Phase 5: future forecast + intervals, writes output tables
│   ├── claude_insights.py           # Claude explains results — no prediction logic (not yet wired into the UI)
│   ├── data_access.py               # Dashboard backend: MySQL -> filtered/aggregated pandas
│   ├── theme.py                     # Design system: palette, dark Plotly styling, CSS, KPI card component
│   ├── info_metadata.py             # Centralized "ⓘ" panel content: source tables/columns/formulas per visual
│   ├── info_panel.py                # Reusable InfoButton + InfoModal (st.dialog) components
│   ├── sql_guard.py                  # Read-only SQL safety guard (SELECT-only, single statement, keyword blacklist, LIMIT cap)
│   ├── groq_client.py                 # Thin Groq API wrapper — the only place GROQ_API_KEY is read
│   ├── chatbot_schema.py              # Schema + business context fed to Groq for grounding
│   ├── chatbot_engine.py              # 2-stage pipeline: question -> SQL plan -> safe query -> grounded answer
│   └── chatbot_ui.py                  # Floating chat widget (bottom-right, every page)
├── views/
│   ├── about.py                     # Business Overview page (landing) — views.about.render()
│   ├── dashboard.py                 # Dashboard page (actuals only) — views.dashboard.render()
│   └── forecast.py                  # Revenue Forecast page (predictions only) — views.forecast.render()
├── app.py                        # Streamlit entry point: page config, sidebar nav, routing
└── requirements.txt
```

## Running the pipeline

```
python src/ingest_csv.py           # Phase 1
python src/process_data.py         # Phase 2
python src/feature_engineering.py  # Phase 3
python src/evaluate_model.py       # Phase 4 (optional standalone check)
python src/forecast.py             # Phase 5 — writes all output tables
streamlit run app.py               # Phase 6
```

`src/claude_insights.py` is ready but not yet wired into the UI — it's a
separate, dormant module unrelated to the floating chatbot below.

## Floating chatbot

Bottom-right on every page. Requires `GROQ_API_KEY` in `.env` (never
committed — see `.gitignore`); without it the widget still opens but says
so plainly instead of failing. Every answer is grounded: Groq first decides
whether the question needs data and, if so, writes a SQL query; that query
is validated by `src/sql_guard.py` (SELECT-only, one statement, keyword
blacklist, session forced read-only, 200-row cap) before it ever touches
MySQL; the results are then the *only* source Groq is allowed to answer
from. Out-of-scope or unanswerable questions get an explicit refusal
instead of a guess.

## MySQL tables

**Raw** (`raw_dim_customer`, `raw_dim_date`, `raw_dim_product_plan`,
`raw_fact_churn`, `raw_fact_customer_usage`, `raw_fact_revenue`,
`raw_fact_sales_pipeline`, `raw_fact_subscription`, `raw_fact_support_ticket`)
— near-verbatim CSV loads.

**Processed** (`dim_customer`, `dim_product_plan`, `fact_subscription`,
`fact_revenue`, `fact_customer_usage`, `fact_churn`, `fact_sales_pipeline`,
`fact_support_ticket`, `monthly_revenue_summary`) — cleaned, typed, with
validated referential integrity.

**ML** (`ml_feature_table`) — every predictor lagged one month behind the
target so nothing "sees the future"; revenue lags/rolling stats, MRR/ARR,
customer counts, usage, and pipeline metrics.

**Output** (`model_evaluation_metrics`, `historical_vs_predicted`,
`revenue_forecast`, `forecast_drivers`) — what the dashboard reads.
