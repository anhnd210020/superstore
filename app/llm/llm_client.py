# app/llm/llm_client.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import google.generativeai as genai

from app.intents import query_engine

from .config import configure_gemini
from .date_normalizer import normalize_question_dates
from .prompts import build_sql_prompt, build_insight_prompt
from .utils import safe_json, resp_text

GEMINI_MODEL = "gemini-2.0-flash"


def llm_generate_sql(
    question: str, schema_path: str = "schema_catalog.json"
) -> Dict[str, Any]:
    """Generate SQL + viz from user question."""
    configure_gemini()

    schema_file = Path(schema_path)
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")
    schema = schema_file.read_text(encoding="utf-8")

    now_bkk = datetime.now(tz=__import__("zoneinfo").ZoneInfo("Asia/Bangkok"))
    today_date = now_bkk.strftime("%Y-%m-%d")
    today_year = now_bkk.strftime("%Y")
    today_month = now_bkk.strftime("%Y-%m")
    prev_year = str(now_bkk.year - 1)

    norm_question = normalize_question_dates(question, now_bkk.year)
    mn, mx = query_engine.get_month_key_range()
    window_txt = f"{mn} đến {mx}" if (mn and mx) else "KHÔNG RÕ"

    sys_prompt = build_sql_prompt(
        question, schema, today_date, today_year, today_month, prev_year, window_txt
    )
    user_msg = f"Câu hỏi (đã chuẩn hoá thời gian): {norm_question}\n"

    model = genai.GenerativeModel(GEMINI_MODEL, generation_config={"temperature": 0.0})
    resp = model.generate_content([sys_prompt, user_msg])

    data = safe_json(resp_text(resp))
    return {
        "intent": (data.get("intent") or "insight").strip(),
        "sql": (data.get("sql") or "").strip(),
        "viz": data.get("viz") or None,
    }


def llm_make_insight(
    intent: str,
    params: Dict[str, Any],
    answer_table: List[Dict[str, Any]],
) -> str:
    """Generate short Vietnamese insight from query result."""
    configure_gemini()

    mn, mx = query_engine.get_month_key_range()
    window_txt = f"{mn} đến {mx}" if (mn and mx) else "KHÔNG RÕ"

    prompt = build_insight_prompt(
        intent=intent,
        question=params.get("question", ""),
        window_txt=window_txt,
        answer_table=answer_table,
    )

    model = genai.GenerativeModel(GEMINI_MODEL, generation_config={"temperature": 0.0})
    resp = model.generate_content(prompt)
    result = resp_text(resp).strip()
    return result