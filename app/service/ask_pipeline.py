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
    # Call LLM to produce SQL, visualization spec, and confidence
    gen = llm_client.llm_generate_sql(question)  

    # Extract generated fields safely with defaults
    sql: str = str(gen.get("sql") or "")
    intent: str = str(gen.get("intent") or "insight")
    confidence: float = float(gen.get("confidence") or 0.0)
    viz: Optional[Dict[str, Any]] = gen.get("viz")  

    # Execute SQL and get rows (list of dicts)
    rows: List[Dict[str, Any]] = query_engine.execute_sql(sql)

    # Determine whether to produce a chart
    is_chart = (intent == "chart") and (confidence >= 0.8) and _valid_chart_spec(rows, viz)

    if is_chart:
        # Generate chart PNG from rows and viz spec
        chart = chart_renderer.make_chart_png(rows, viz)
        png_bytes = chart["data_bytes"]
        return {"image_bytes": png_bytes}

    # Otherwise, request the LLM to create an insight text summary
    insight = llm_client.llm_make_insight(
        intent="insight",
        params={"question": question, "sql": sql, "confidence": confidence},
        answer_table=rows[:15],  # Limit preview table to 15 rows
    )
    return {"insight_text": insight}