"""
Two-stage Groq pipeline: NL question -> SQL plan -> safe execution ->
grounded NL answer.

    User question -> [Stage 1: Groq] -> SQL (or "no query needed")
                   -> [sql_guard]    -> safe, read-only execution
                   -> [Stage 2: Groq] -> answer, grounded ONLY in the
                                          returned rows / static schema

This is the only place that decides what "grounded" means for the chatbot —
every answer must trace back to either a query result or the static
schema/business context passed to Stage 2, never general knowledge.
"""

from __future__ import annotations

import json
import re

import pandas as pd

import groq_client
from chatbot_schema import BUSINESS_DESCRIPTION, SCHEMA_DESCRIPTION
from sql_guard import UnsafeQueryError, run_safe_query

NO_DATA_MESSAGE = "I don't have enough data to answer this."

STAGE1_SYSTEM = f"""You are a routing planner for the CloudFlow Assistant, a chatbot embedded in a
SaaS revenue analytics app. Given the user's message, decide whether answering it well requires
a fresh database query.

{SCHEMA_DESCRIPTION}

Respond with ONLY a JSON object, no other text before or after it:
- {{"needs_query": true, "sql": "<a single MySQL SELECT statement>"}} — the message asks for
  CloudFlow-specific numbers or records (revenue, MRR/ARR, customers, subscriptions, usage, churn,
  support tickets, sales pipeline, forecasts, forecast accuracy, etc.)
- {{"needs_query": false}} — everything else: greetings and small talk, questions about what the
  assistant can do, general SaaS/business concept questions ("what is MRR", "how does churn work"),
  questions about CloudFlow's business model/story (answerable from the description below), or any
  other general conversation that doesn't need a fresh lookup.

Business description (context for the routing judgement only — not a data source):
{BUSINESS_DESCRIPTION}

The SQL must be exactly one read-only SELECT statement. Never write INSERT/UPDATE/DELETE/DROP/ALTER/CREATE or any other mutating statement, and never chain multiple statements."""

STAGE2_SYSTEM = f"""You are the CloudFlow Assistant, a friendly and knowledgeable helper embedded in a
SaaS revenue analytics dashboard for the fictional company CloudFlow.

{BUSINESS_DESCRIPTION}

You are a general-purpose conversational assistant first: greet people naturally, make small talk,
explain general SaaS/business concepts (e.g. what MRR means, how churn is typically measured, general
best practices) using your own knowledge, and discuss CloudFlow's business model/story using the
description above. Be warm and natural, like a helpful chat assistant — not a rigid data terminal.

The one hard rule: for anything involving CloudFlow's SPECIFIC numbers, records, or facts (actual
revenue figures, customer counts, exact dates, forecast values, model accuracy, etc.), you must rely
ONLY on the "Data" block given to you below for that question — never invent, estimate, or guess a
specific CloudFlow number that isn't in it. If the data needed for a specific data question wasn't
found or isn't available, say so plainly and, if helpful, mention what related data you do have
instead — you may use a phrase like "{NO_DATA_MESSAGE}" when nothing useful can be said, but prefer
being specifically helpful about what's missing over a flat refusal.

When you do have data for a specific question, answer should:
- Give a clear, direct answer first
- Include the relevant numbers, formatted naturally (e.g. $12,345 or 3.2%)
- Mention the relevant time period when applicable
- Briefly note the source table when it's useful context (e.g. "from monthly_revenue_summary")

Keep answers concise and conversational — a couple of sentences for chit-chat, a bit more for data
questions. Never mention SQL, JSON, routing, or other internal mechanics."""


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in Groq response.")
    return json.loads(match.group(0))


def _format_results(df: pd.DataFrame) -> str:
    if df.empty:
        return "(query returned no rows)"
    return df.to_csv(index=False)


def answer_question(question: str, page_context: str = "") -> str:
    if not groq_client.is_configured():
        return "The chatbot isn't configured yet — ask the administrator to set GROQ_API_KEY."

    # --- stage 1: decide if/what to query -----------------------------------
    try:
        plan_raw = groq_client.chat(
            messages=[
                {"role": "system", "content": STAGE1_SYSTEM},
                {"role": "user", "content": f"Current page in the app: {page_context}\n\nQuestion: {question}"},
            ],
            temperature=0.0, max_tokens=400, json_mode=True,
        )
        plan = _extract_json(plan_raw)
    except Exception:
        plan = {"needs_query": False}

    if plan.get("needs_query") and plan.get("sql"):
        try:
            df = run_safe_query(plan["sql"])
            data_block = f"SQL used:\n{plan['sql']}\n\nResults ({len(df)} row(s)):\n{_format_results(df)}"
        except UnsafeQueryError as e:
            data_block = f"(The generated query was rejected for safety: {e})"
        except Exception as e:
            data_block = f"(The query failed to execute: {e})"
    else:
        data_block = f"No database query was run for this question. Static schema/business context only:\n{SCHEMA_DESCRIPTION}"

    # --- stage 2: synthesize a grounded answer ------------------------------
    try:
        answer = groq_client.chat(
            messages=[
                {"role": "system", "content": STAGE2_SYSTEM},
                {"role": "user", "content": f"Question: {question}\n\nData:\n{data_block}"},
            ],
            temperature=0.1, max_tokens=500,
        )
    except Exception as e:
        return f"Sorry, I couldn't process that right now ({e})."

    return answer.strip() or NO_DATA_MESSAGE
