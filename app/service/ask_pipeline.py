# app/service/ask_pipeline.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.intents import query_engine
from app.llm import llm_client  
from app.vis import chart_renderer 

def _valid_chart_spec(
    rows: List[Dict[str, Any]],
    viz: Optional[Dict[str, Any]],
) -> bool:
    """Check minimal validity of a viz spec against returned rows."""
    if not rows or not viz:
        return False

    x = viz.get("x")
    y = viz.get("y")
    if not x or not y:
        return False

    cols = set(rows[0].keys())
    return x in cols and y in cols


def ask_once(question: str) -> Dict[str, Any]:
    """
    LLM (SQL) → Run SQL → (if confident chart & viz valid) render chart → else insight-only.
    """
    gen = llm_client.llm_generate_sql(question)  # {intent, confidence, reason, sql, notes, viz}

    sql: str = str(gen.get("sql") or "")
    intent: str = str(gen.get("intent") or "insight")
    confidence: float = float(gen.get("confidence") or 0.0)
    viz: Optional[Dict[str, Any]] = gen.get("viz")  # type: ignore[assignment]

    rows: List[Dict[str, Any]] = query_engine.execute_sql(sql)

    # Quyết định vẽ: KHÔNG hard-code từ khóa; chỉ dựa vào LLM + tính hợp lệ viz + dữ liệu thật.
    is_chart = (intent == "chart") and (confidence >= 0.8) and _valid_chart_spec(rows, viz)

    if is_chart:
        chart = chart_renderer.make_chart_png(rows, viz)  # type: ignore[arg-type]
        image_url = chart_renderer.save_chart_base64_to_file(chart["data_base64"])
        insight = llm_client.llm_make_insight(
            intent="chart",
            params={"question": question, "sql": sql, "viz": viz, "confidence": confidence},
            answer_table=rows[:10],
        )
        return {"image_url": image_url, "insight_text": insight}

    # Mặc định: insight-only
    insight = llm_client.llm_make_insight(
        intent="insight",
        params={"question": question, "sql": sql, "confidence": confidence},
        answer_table=rows[:10],
    )
    return {"insight_text": insight}
