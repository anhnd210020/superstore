# app/llm/llm_client.py — Gemini client (SQLite SQL generation + insight)
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from dotenv import load_dotenv

GEMINI_MODEL = "gemini-2.0-flash"
ENV_PATH = Path("/home/ducanhhh/superstore/.env")  # adjust if different

# Extract the first JSON object in a string (greedy to capture full object)
_JSON_RE = re.compile(r"\{[\s\S]*\}")


def _config() -> None:
    """Load API key from .env and configure Gemini SDK."""
    load_dotenv(dotenv_path=str(ENV_PATH), override=True)

    raw = (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_API_KEY_GEMINI")
    )
    if not raw:
        raise RuntimeError("Missing GEMINI_API_KEY (or GOOGLE_API_KEY[_GEMINI]).")

    api_key = raw.strip().strip('"').strip("'")
    if not api_key:
        raise RuntimeError("Empty GEMINI_API_KEY after stripping.")
    genai.configure(api_key=api_key)


def _safe_json(text: str) -> Dict[str, Any]:
    """
    Extract and parse the first JSON object from text.

    Raises:
        ValueError: If no JSON object is found or JSON is invalid.
    """
    match = _JSON_RE.search((text or "").strip())
    if not match:
        raise ValueError("LLM did not return a JSON object.")
    return json.loads(match.group(0))


def _resp_text(resp: Any) -> str:
    """
    Extract plain text from a Gemini response object.

    Returns:
        str: Extracted text; empty string if unavailable.
    """
    try:
        if getattr(resp, "text", None):
            return resp.text

        candidates = getattr(resp, "candidates", [])
        if candidates and hasattr(candidates[0], "content"):
            parts = getattr(candidates[0].content, "parts", None)
            if parts:
                return "".join(getattr(p, "text", "") for p in parts)
    except Exception:
        pass
    return ""


def llm_generate_sql(question: str, schema_path: str = "schema_catalog.json") -> Dict[str, Any]:
    """
    Use Gemini to generate a single SELECT SQL and optional viz spec from a question.
    """
    _config()

    schema_file = Path(schema_path)
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")
    schema = schema_file.read_text(encoding="utf-8")

    sys_prompt = f"""
Bạn là chuyên gia SQL & trực quan hoá cho SQLite. Nhiệm vụ:
1) Viết đúng **một** câu SELECT duy nhất dựa trên SCHEMA JSON.
2) Xác định intent:
   - "chart": CHỈ khi người dùng RÕ RÀNG yêu cầu vẽ/biểu đồ/đồ thị/plot/visualize.
   - "insight": các trường hợp còn lại.
3) Nếu intent="chart", trả thêm đặc tả viz TỐI THIỂU:
   - chart_type: "line" | "bar" (ưu tiên 2 loại này)
   - x: tên cột trục X
   - y: tên cột giá trị
   - title: tiêu đề ngắn gọn
   - sort: "x" | "y" | "none"
   - limit: số nguyên (mặc định 24)
4) Ghi "confidence" (0..1) cho quyết định intent, và "reason" (<= 20 từ).

[SCHEMA JSON]
{schema}

[HƯỚNG DẪN NGẮN]
- Chỉ dùng bảng/cột có trong schema. Không INSERT/UPDATE/DELETE/DDL.
- Tổng hợp mẫu:
  SUM(fact_sales.sales) AS sales,
  SUM(fact_sales.profit) AS profit,
  SUM(fact_sales.qty) AS qty,
  COUNT(DISTINCT fact_sales.order_id) AS orders.
- Thời gian: dim_date.month_key (YYYY-MM) hoặc kpi_*_m.month_key.
- Join: fact_sales.date_key = dim_date.date_key; fact_sales.product_id = dim_product.product_id.
- Top N: ORDER BY metric DESC + LIMIT N (nếu N không rõ, LIMIT 200).

[ĐẦU RA CHỈ 1 JSON]
{{
  "intent": "chart" | "insight",
  "confidence": 0.0,
  "reason": "<=20 từ, vì sao chọn intent",
  "sql": "SELECT ...",
  "notes": "<=25 từ",
  "viz": {{"chart_type":"...","x":"...","y":"...","title":"...","sort":"...","limit":24}} | null
}}
"""
    user = f"Câu hỏi: {question}"
    model = genai.GenerativeModel(GEMINI_MODEL)
    resp = model.generate_content([sys_prompt, user])

    data = _safe_json(_resp_text(resp))
    return {
        "intent": (data.get("intent") or "insight").strip(),
        "confidence": float(data.get("confidence") or 0.0),
        "reason": (data.get("reason") or "").strip(),
        "sql": (data.get("sql") or "").strip(),
        "notes": (data.get("notes") or "").strip(),
        "viz": data.get("viz") or None,
    }


def llm_make_insight(
    intent: str,
    params: Dict[str, Any],
    answer_table: List[Dict[str, Any]],
) -> str:
    """
    Use Gemini to produce a concise Vietnamese insight (<= 2 sentences).
    """
    _config()

    prompt = (
        "Bạn là chuyên gia BI. Viết insight TIẾNG VIỆT ngắn gọn cho dữ liệu bán hàng.\n"
        "- Tối đa 2 câu, <= 45 từ/câu, có số/%.\n"
        f"intent={intent}\n"
        f"params={json.dumps(params, ensure_ascii=False)}\n"
        f"data_rows(<=10)={json.dumps(answer_table[:10], ensure_ascii=False)}\n"
        "Chỉ trả văn bản insight (không JSON/markdown)."
    )

    model = genai.GenerativeModel(GEMINI_MODEL)
    resp = model.generate_content(prompt)
    return (_resp_text(resp) or "").strip()
