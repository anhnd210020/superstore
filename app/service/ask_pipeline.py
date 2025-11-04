# app/service/ask_pipeline.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Import query execution, LLM client, and chart rendering modules
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

    # Extract x/y axis names from the visualization spec
    x = viz.get("x")
    y = viz.get("y")
    if not x or not y:
        return False

    # Ensure that the x and y columns exist in the query result
    cols = set(rows[0].keys())
    return x in cols and y in cols


def ask_once(question: str) -> Dict[str, Any]:
    """
    Main pipeline:
    1. Use LLM to generate SQL and visualization spec.
    2. Execute SQL query to get data.
    3. If chart intent is confident and valid → render chart.
    4. Otherwise → generate textual insight only.
    """
    # Step 1: Generate SQL + viz spec
    query_spec = llm_client.llm_generate_sql(question)  

    sql: str = str(query_spec.get("sql") or "")
    intent: str = str(query_spec.get("intent") or "insight")
    draw_chart: bool = bool(query_spec.get("draw_chart"))
    viz: Optional[Dict[str, Any]] = query_spec.get("viz")  

    # Step 2: Execute SQL
    rows: List[Dict[str, Any]] = query_engine.execute_sql(sql)

    # Step 3: Determine whether to render chart
    is_chart = (intent == "chart") and draw_chart and _valid_chart_spec(rows, viz)

    if is_chart:
        chart = chart_renderer.make_chart_png(rows, viz)  # type: ignore[arg-type]
        png_bytes = chart["data_bytes"]
        insight = llm_client.llm_make_insight(
            intent="chart",
            params={"question": question, "sql": sql, "viz": viz, "draw_chart": draw_chart},
            answer_table=rows[:15],
        )
        return {"chart_image": png_bytes, "insight_text": insight}

    # Step 4: Text insight only
    insight = llm_client.llm_make_insight(
        intent="insight",
        params={"question": question, "sql": sql, "draw_chart": draw_chart},
        answer_table=rows[:15],
    )
    return {"insight_text": insight}

