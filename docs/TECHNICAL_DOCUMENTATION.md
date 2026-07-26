# CloudFlow Revenue Analytics — Technical Documentation

**System:** SaaS Revenue Forecasting & Churn Analytics Platform
**Subject company (fictional):** CloudFlow — multi-product B2B SaaS vendor
**Version:** dev branch, July 2026
**Stack:** Python, MySQL/TiDB, Streamlit, XGBoost/LightGBM/statsmodels, Groq, Anthropic Claude

---

## 1. Purpose

CloudFlow Revenue Analytics is an end-to-end system that takes raw operational
CSV exports from a fictional B2B SaaS company and turns them into:

1. A validated, queryable MySQL data warehouse.
2. A leak-free machine learning feature set.
3. A 6-month forward revenue forecast, selected from seven competing models
   via walk-forward backtesting.
4. An interactive Streamlit dashboard (business overview, live KPIs, and the
   forecast) with a grounded, SQL-backed conversational assistant.

The company sells three product lines (Core Platform, Analytics Add-on,
Automation Suite), each in four tiers (Starter/Professional/Business/
Enterprise), billed monthly or annually, to four customer segments (Startup/
SMB/Mid-Market/Enterprise) across five regions.

## 2. Architecture

```
data/raw/*.csv  (9 source files, immutable)
      │
      ▼
raw_* tables              Phase 1 — src/ingest_csv.py
      │                   create DB, create staging tables, load, validate
      ▼
dim_*/fact_* tables        Phase 2 — src/process_data.py
+ monthly_revenue_summary  clean, type, enforce referential integrity
      │
      ▼
ml_feature_table           Phase 3 — src/feature_engineering.py
                            every predictor lagged 1 month behind target
      │
      ▼
model_evaluation_metrics   Phase 4 — src/evaluate_model.py (optional standalone check)
                            walk-forward backtest, 7 candidate models
      │
      ▼
historical_vs_predicted,   Phase 5 — src/forecast.py
revenue_forecast,          fit winning model on full history,
forecast_drivers           roll forward 6 months, write output tables
      │
      ▼
src/data_access.py          query/aggregation layer — the dashboard's
                            only path to MySQL
      │
      ▼
app.py + views/              Phase 6 — Streamlit dashboard
```

Every stage reads from and writes to MySQL — CSVs are only the initial
ingestion source, never read again downstream. The dashboard never touches
the CSVs or the raw/staging tables directly.

## 3. Database

**Engine:** MySQL-compatible. Local development uses MariaDB via XAMPP
(`localhost:3306`); production uses **TiDB Cloud Serverless** (MySQL
wire-protocol compatible, reached over TLS on port 4000).

**Connection management** (`src/db.py`): all credentials come from
environment variables (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`,
`DB_NAME`, `DB_SSL`), loaded via `python-dotenv` locally or Streamlit Cloud's
secrets store in production. `DB_SSL` is opt-in (defaults off) since local
XAMPP doesn't support TLS at all, while TiDB Cloud requires it.

**Table families:**

| Family | Tables | Purpose |
|---|---|---|
| Raw | `raw_dim_customer`, `raw_dim_date`, `raw_dim_product_plan`, `raw_fact_churn`, `raw_fact_customer_usage`, `raw_fact_revenue`, `raw_fact_sales_pipeline`, `raw_fact_subscription`, `raw_fact_support_ticket` | Near-verbatim CSV loads, minimally typed |
| Processed | `dim_customer`, `dim_product_plan`, `fact_subscription`, `fact_revenue`, `fact_customer_usage`, `fact_churn`, `fact_sales_pipeline`, `fact_support_ticket`, `monthly_revenue_summary` | Cleaned, typed, validated referential integrity |
| ML | `ml_feature_table` | Every predictor lagged 1 month behind the target — revenue lags/rolling stats, MRR/ARR, customer counts, usage, pipeline metrics |
| Output | `model_evaluation_metrics`, `historical_vs_predicted`, `revenue_forecast`, `forecast_drivers` | What the dashboard reads |

Row counts (current dataset): 60 customers, 24 plans, 91 subscriptions,
2,094 revenue transactions, 1,953 usage records, 17 churn events, 150 sales
opportunities, 340 support tickets, 59 months of revenue history.

## 4. Forecasting methodology

`src/train_model.py` defines seven one-step-ahead candidate models:

| Model | Type | Notes |
|---|---|---|
| `naive` | Baseline | Last observed value |
| `seasonal_naive` | Baseline | Value from 12 months prior |
| `moving_avg_3` | Baseline | Trailing 3-month mean |
| `drift` | Baseline | Last value + average historical change |
| `holt_linear` | Classical (statsmodels) | Holt's linear exponential smoothing |
| `xgboost` | Gradient-boosted trees | Fit on leak-free feature columns |
| `lightgbm` | Gradient-boosted trees | Fit on leak-free feature columns |

**Validation:** walk-forward backtest with an expanding window over the
trailing 12 months. For each month *i* in the test window, every model is
fit/derived using only rows before *i*, predicts row *i*, then the window
advances one month. This produces 12 independent one-month-ahead forecasts
per model rather than a single train/test split, giving a far more honest
estimate of live performance.

**Model selection:** `src/evaluate_model.py` scores all seven on MAPE and
writes results to `model_evaluation_metrics`; `src/forecast.py` picks the
lowest-MAPE model, refits it on the complete history, and rolls forward
6 months with an 80% confidence interval derived from backtest residual
standard deviation.

**Current champion (this dataset):** `drift`, MAPE 2.18%, MAE $486, RMSE
$615 — the simplest baseline outperforms the tree-based models here, which
is a realistic outcome on ~59 months of relatively smooth, trend-dominated
revenue data with no strong seasonal or nonlinear signal for the trees to
exploit.

**Explicitly not yet built:** churn prediction and anomaly detection models.
Both have sidebar entries in the dashboard that route to a shared
"coming soon" placeholder rather than a stub prediction — no functionality
is promised that doesn't exist yet.

## 5. Dashboard application

**Framework:** Streamlit, single entry point `app.py`, five logical pages
under `views/`: Business Overview (`about.py`), Dashboard (`dashboard.py`),
Revenue Forecast (`forecast.py`), Churn Prediction and Anomaly Detection
(both routed to `coming_soon.py`).

**Navigation:** hand-rolled with `st.button` + `st.session_state` rather than
Streamlit's built-in page nav, specifically so the active nav item can get a
full gradient treatment via CSS — the built-in nav doesn't expose enough
styling hooks for that. An icon-only "nav rail" (`nav_rail()` in
`src/theme.py`) is rendered separately in the main content area to keep
navigation reachable when the real sidebar is collapsed.

**Design system** (`src/theme.py`): two complete palettes (dark/light)
switched via `st.session_state["theme_mode"]`, injected as CSS on every
rerun rather than relying on client-side theme state, so charts and markup
are rebuilt fresh with the correct colors every time. Shared components:
KPI cards with sparklines and trend badges, a themed HTML table (used
instead of `st.dataframe` so both themes stay fully controllable), Plotly
chart styling, and an info-button/modal system that surfaces the source
tables/columns/formula behind every number on request.

**Known Streamlit-version-drift issues found and fixed during development:**
the dropdown/multiselect popover background selector (`[data-baseweb="menu"]`)
and the sidebar's block-container selector (`.block-container`) both stopped
matching in the installed Streamlit version's current DOM; both were
identified by inspecting the live DOM with Playwright and replaced with the
real elements (`[data-testid="stSelectboxVirtualDropdown"]`,
`[data-testid="stSidebarContent"]`).

## 6. Conversational assistant (floating chatbot)

Bottom-right on every page (`src/chatbot_ui.py`), backed by Groq
(`GROQ_API_KEY`, model configurable via `GROQ_MODEL`). Two-stage grounded
pipeline (`src/chatbot_engine.py`):

1. Groq decides whether the question needs data, and if so, writes a SQL
   query against the known schema (`src/chatbot_schema.py` supplies the
   business/table context).
2. That query passes through `src/sql_guard.py` before it ever touches
   MySQL: SELECT-only, single statement, keyword blacklist, session forced
   read-only, 200-row cap.
3. The query results are the *only* source Groq is allowed to answer from —
   out-of-scope or unanswerable questions get an explicit refusal rather
   than a guess.

A separate, currently dormant module (`src/claude_insights.py`, Anthropic
Claude-backed) is implemented but not wired into the UI — reserved for a
future "generate insights" feature on the dashboard.

## 7. Deployment

- **Source control:** GitHub (`LejoyAnalytics/datascience_saas_analytics`),
  `main` and `dev` branches.
- **Hosting:** Streamlit Community Cloud, deployed from `app.py`.
- **Database:** TiDB Cloud Serverless (free tier), populated by running the
  five pipeline phases once against the cloud connection string.
- **Secrets:** local development uses a gitignored `.env`; production secrets
  (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_SSL`,
  `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `GROQ_MODEL`) live in Streamlit Cloud's
  own secrets store, which also exposes them as environment variables so the
  existing `os.getenv()`-based config needs no code changes between
  environments.

## 8. Tech stack summary

| Layer | Technology |
|---|---|
| Language | Python 3 |
| Data pipeline | pandas, SQLAlchemy, PyMySQL |
| Database | MySQL / MariaDB (dev), TiDB Cloud Serverless (prod) |
| ML / forecasting | scikit-learn, XGBoost, LightGBM, statsmodels |
| Dashboard | Streamlit, Plotly |
| Conversational assistant | Groq API (chat), Anthropic Claude API (dormant insights module) |
| Hosting | Streamlit Community Cloud |
| Testing/verification tooling | Playwright (used during development to verify UI/theme behavior against the live DOM) |

## 9. Repository layout

```
.
├── data/raw/                 Source CSVs — immutable, ingested into MySQL
├── .streamlit/config.toml    Base theme config
├── src/
│   ├── db.py                     Connection/config (env-driven, optional TLS)
│   ├── db_writer.py               Shared MySQL write helpers
│   ├── ingest_csv.py               Phase 1
│   ├── process_data.py             Phase 2
│   ├── customer_status.py          Shared active/new/churned logic
│   ├── feature_engineering.py      Phase 3
│   ├── train_model.py               Model definitions + backtest engine
│   ├── evaluate_model.py            Phase 4
│   ├── forecast.py                  Phase 5
│   ├── claude_insights.py           Dormant — not wired into the UI
│   ├── data_access.py               Dashboard's only path to MySQL
│   ├── theme.py                     Design system, CSS, KPI components
│   ├── info_metadata.py / info_panel.py   Per-visual "ⓘ" source/formula panels
│   ├── sql_guard.py                  Read-only SQL safety guard
│   ├── groq_client.py / chatbot_schema.py / chatbot_engine.py / chatbot_ui.py
├── views/
│   ├── about.py                    Business Overview
│   ├── dashboard.py                 Dashboard (actuals only)
│   ├── forecast.py                  Revenue Forecast (predictions only)
│   └── coming_soon.py                Shared placeholder (Churn Prediction, Anomaly Detection)
├── app.py                       Entry point: page config, sidebar nav, routing
└── requirements.txt
```

## 10. Running it locally

```
python src/ingest_csv.py           # Phase 1
python src/process_data.py         # Phase 2
python src/feature_engineering.py  # Phase 3
python src/evaluate_model.py       # Phase 4 (optional standalone check)
python src/forecast.py             # Phase 5 — writes all output tables
streamlit run app.py               # Phase 6
```

## 11. Roadmap

- Churn Prediction module (currently a placeholder nav item).
- Anomaly Detection module (currently a placeholder nav item).
- Wiring `src/claude_insights.py` into the dashboard as a "generate
  insights" feature.
