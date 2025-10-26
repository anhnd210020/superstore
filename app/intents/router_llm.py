# router_llm.py — LLM-parse + query only (no NLG inside)
from typing import Any, Dict, List, Optional
import sqlite3
from pathlib import Path

from app.llm.llm_client import llm_parse_question  # chỉ dùng parse
from app.intents.query_engine import (
    IntentParams,
    DB_PATH,
    query_top_n_in_month,
    query_compare_mom_group,
    query_most_negative_profit,
    query_trend_range,
    query_latest_overview,
)

_ALLOWED_INTENTS = {
    "top_n_by_metric_in_month",
    "compare_mom_group",
    "most_negative_profit",
    "trend_range",
    "latest_month_overview",
}
_ALLOWED_GROUPBY = {"product","category","subcategory","region","state","segment","ship_mode"}
_ALLOWED_METRICS = {"sales","profit","orders","qty"}

def _latest_month() -> Optional[str]:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT month_key FROM kpi_monthly ORDER BY month_dt DESC LIMIT 1").fetchone()
    return row[0] if row else None

def _with_defaults(p: IntentParams) -> IntentParams:
    if not p.intent or p.intent not in _ALLOWED_INTENTS:
        p.intent = "latest_month_overview"
    if not p.metric or p.metric not in _ALLOWED_METRICS:
        p.metric = "sales"
    if not p.topn or p.topn < 1:
        p.topn = 5
    if p.intent == "top_n_by_metric_in_month" and (not p.groupby or p.groupby not in _ALLOWED_GROUPBY):
        p.groupby = "product"
    if p.intent == "compare_mom_group" and (not p.groupby or p.groupby not in _ALLOWED_GROUPBY):
        p.groupby = "category"
    if p.intent == "most_negative_profit" and (not p.groupby or p.groupby not in _ALLOWED_GROUPBY):
        p.groupby = "subcategory"
    if p.intent in {"top_n_by_metric_in_month","compare_mom_group","most_negative_profit","latest_month_overview"}:
        p.month_key = p.month_key or _latest_month()
    return p

def run_router_llm_first(question: str) -> Dict[str, Any]:
    parsed = llm_parse_question(question)

    p = IntentParams(
        intent=parsed.get("intent"),
        metric=parsed.get("metric"),
        groupby=parsed.get("groupby"),
        topn=int(parsed.get("topn") or 5),
        month_key=parsed.get("month_key"),
        month_from=parsed.get("month_from"),
        month_to=parsed.get("month_to"),
    )
    p = _with_defaults(p)

    # Query only
    if p.intent == "top_n_by_metric_in_month":
        table = query_top_n_in_month(p)
        kpis = {"month_key": p.month_key, "metric": p.metric, "groupby": p.groupby, "topn": p.topn}
    elif p.intent == "compare_mom_group":
        table = query_compare_mom_group(p)
        kpis = {"month_key": p.month_key, "metric": p.metric, "groupby": p.groupby, "topn": p.topn}
    elif p.intent == "most_negative_profit":
        p.metric = "profit"  # cố định nghĩa
        table = query_most_negative_profit(p)
        kpis = {"month_key": p.month_key, "groupby": p.groupby, "topn": p.topn}
    elif p.intent == "trend_range":
        table = query_trend_range(p)
        kpis = {"metric": p.metric, "month_from": p.month_from, "month_to": p.month_to}
    else:  # latest_month_overview
        row = query_latest_overview(p.month_key)
        table = [row] if row else []
        kpis = {"month_key": p.month_key}

    return {
        "params": {
            "intent": p.intent, "metric": p.metric, "groupby": p.groupby,
            "topn": p.topn, "month_key": p.month_key,
            "month_from": p.month_from, "month_to": p.month_to
        },
        "answer_table": table,
        "kpis": kpis,
        # Không sinh insight ở router; caller muốn thì tự gọi llm_make_insight(...)
    }
