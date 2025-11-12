# app/service/ask_pipeline.py
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Literal

# Import query execution, LLM client, and chart rendering modules
from app.intents import query_engine
from app.llm import llm_client
from app.vis import chart_renderer

ChartMode = Literal["auto", "text_only"]
FinalIntent = Literal["chart", "insight"]

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
    cols = {c.lower() for c in rows[0].keys()}  
    print(cols)
    return x in cols and y in cols

def is_time_series_result(rows: Sequence[Mapping[str, Any]]) -> bool:
    if len(rows) < 2:
        return False
    sample = rows[0]
    time_like_cols = {"month_key", "order_date", "order_month", "order_year"}
    return any(col in sample for col in time_like_cols)

def decide_final_intent(
    llm_intent: str,
    chart_mode: ChartMode,
    rows: Sequence[Mapping[str, Any]],
) -> FinalIntent:
    # 1) Luôn trả insight
    if chart_mode == "text_only":
        return "insight"

    # Normalize llm_intent
    li = (llm_intent or "insight").strip().lower()
    if li not in ("chart", "insight"):
        li = "insight"

    # Không có dữ liệu hoặc chỉ 1 dòng → chart không có ý nghĩa
    if not rows or len(rows) < 2:
        return "insight"

    # 2) Nếu LLM đã bảo CHART → tôn trọng nó (miễn có dữ liệu)
    if li == "chart":
        return "chart"

    # 3) Từ đây trở xuống: li == "insight"
    time_series = is_time_series_result(rows)

    if chart_mode == "auto":
        # Auto: chỉ tự động nâng insight → chart khi là time series
        if time_series:
            return "chart"
        return "insight"

    # Fallback an toàn
    return "insight"

def ask_once(
    question: str,
    chart_mode: ChartMode = "auto",
) -> Dict[str, Any]:
    """
    Main pipeline:
    1. Dùng LLM đề xuất SQL + viz spec + intent sơ bộ (llm_intent).
    2. Thực thi SQL để lấy dữ liệu.
    3. Backend quyết định final_intent dựa trên:
       - llm_intent
       - chart_mode (cấu hình khách hàng)
       - dữ liệu rows
    4. Nếu final_intent == "chart" và viz hợp lệ → render chart + insight.
       Ngược lại → chỉ insight text.
    """
    # Step 1: Generate SQL + viz spec
    query_spec = llm_client.llm_generate_sql(question)  

    sql: str = str(query_spec.get("sql") or "")
    llm_intent: str = str(
    query_spec.get("intent")
    or query_spec.get("llm_intent")
    or "insight"
)
    viz: Optional[Dict[str, Any]] = query_spec.get("viz")  

    # Step 2: Execute SQL
    rows: List[Dict[str, Any]] = query_engine.execute_sql(sql)
    print("Query returned rows:", rows)
    
    # Step 3: Backend quyết định intent cuối
    final_intent: FinalIntent = decide_final_intent(
        llm_intent=llm_intent,
        chart_mode=chart_mode,
        rows=rows,
    )    
    print(f"Decided final_intent: {final_intent} (llm_intent={llm_intent}, chart_mode={chart_mode})")

    # Step 4: Nếu final_intent là chart + viz hợp lệ → vẽ chart
    if final_intent == "chart" and _valid_chart_spec(rows, viz):
        # chuẩn hóa key về lowercase để khớp với viz['x'], viz['y']
        rows_norm = [{k.lower(): v for k, v in r.items()} for r in rows]

        chart = chart_renderer.make_chart_png(rows_norm, viz)
        png_bytes = chart["data_bytes"]

        insight = llm_client.llm_make_insight(
            intent="chart",
            params={"question": question, "sql": sql, "viz": viz},
            answer_table=rows[:15],
        )
        return {
            "intent": "chart",
            "chart_image": png_bytes,
            "insight_text": insight,
        }
    
    # Step 5: Ngược lại, luôn trả insight text
    insight = llm_client.llm_make_insight(
        intent="insight",
        params={"question": question, "sql": sql},
        answer_table=rows[:15],
    )
    return {
        "intent": "insight",
        "chart_image": None,
        "insight_text": insight,
    }
