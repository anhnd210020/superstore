# llm_client.py — Gemini client (SQLite SQL generation + insight)
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

import google.generativeai as genai
from dotenv import load_dotenv

# Model & env config
GEMINI_MODEL = "gemini-2.0-flash"
ENV_PATH = Path("/home/ducanhhh/superstore/.env")  # adjust if different

# Extract the first JSON object in a string
_JSON_RE = re.compile(r"\{[\s\S]*\}")


def _config() -> None:
    # Load .env explicitly from ENV_PATH to avoid CWD surprises
    load_dotenv(dotenv_path=str(ENV_PATH), override=True)

    raw = (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_API_KEY_GEMINI")
    )
    if not raw:
        raise RuntimeError("Missing GEMINI_API_KEY (or GOOGLE_API_KEY[_GEMINI]).")

    # Normalize common quoting issues when keys are stored as "key"
    api_key = raw.strip().strip('"').strip("'")
    if not api_key:
        raise RuntimeError("Empty GEMINI_API_KEY after stripping.")
    genai.configure(api_key=api_key)


def _safe_json(text: str) -> Dict[str, Any]:
    """
    Extract the first JSON object from a text blob.

    Args:
        text (str): Raw text possibly containing a JSON object.

    Returns:
        Dict[str, Any]: Parsed JSON dict.

    Raises:
        ValueError: If no JSON object is found or JSON is invalid.
    """
    match = _JSON_RE.search((text or "").strip())
    if not match:
        raise ValueError("LLM did not return a JSON object.")
    return json.loads(match.group(0))


def _resp_text(resp: Any) -> str:
    """
    Safely extract text content from a Gemini response object.

    Args:
        resp (Any): Raw response from google.generativeai.

    Returns:
        str: Extracted text (empty if not found).
    """
    try:
        # Typical path for SDK responses
        if getattr(resp, "text", None):
            return resp.text

        # Fallback path used by some SDK versions
        candidates = getattr(resp, "candidates", [])
        if candidates and hasattr(candidates[0], "content"):
            parts = getattr(candidates[0].content, "parts", None)
            if parts:
                return "".join(getattr(p, "text", "") for p in parts)
    except Exception:
        # Swallow extraction errors; caller will handle empty text
        pass
    return ""


def llm_generate_sql(question: str, schema_path: str = "schema_catalog.json") -> Dict[str, str]:
    """
    LLM #1: Generate a single SQLite SELECT statement to answer the question.

    Args:
        question (str): User's natural-language question.
        schema_path (str): Path to schema catalog JSON used as context.

    Returns:
        Dict[str, str]: {"sql": "...", "notes": "..."} (strings may be empty).

    Raises:
        FileNotFoundError: If schema_path cannot be read.
        ValueError/RuntimeError: On LLM/JSON/config issues.
    """
    _config()

    schema_file = Path(schema_path)
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")
    schema = schema_file.read_text(encoding="utf-8")

    # System prompt: concise, with concrete SQL conventions (Vietnamese as-is)
    sys_prompt = f"""
Bạn là chuyên gia SQL cho SQLite. Viết 1 câu SELECT duy nhất dựa trên SCHEMA JSON sau.
Chỉ dùng bảng/cột có trong schema. Không dùng INSERT/UPDATE/DELETE/DDL.

[SCHEMA JSON]
{schema}

[HƯỚNG DẪN NGẮN]
- Tổng hợp chuẩn:
  SUM(fact_sales.sales) AS sales,
  SUM(fact_sales.profit) AS profit,
  SUM(fact_sales.qty) AS qty,
  COUNT(DISTINCT fact_sales.order_id) AS orders.
- Thời gian: dùng dim_date.month_key (YYYY-MM) hoặc kpi_*_m.month_key.
- Join ngày: fact_sales.date_key = dim_date.date_key (khi cần).
- Sản phẩm: fact_sales.product_id = dim_product.product_id (khi cần).
- Nếu là 'top N' thì ORDER BY metric phù hợp + LIMIT N.
- Nếu N không rõ, dùng LIMIT 200.

[ĐẦU RA]
Chỉ in 1 JSON:
{{
  "sql": "SELECT ...",
  "notes": "<=25 từ"
}}
"""
    user = f"Câu hỏi: {question}"

    model = genai.GenerativeModel(GEMINI_MODEL)
    resp = model.generate_content([sys_prompt, user])

    data = _safe_json(_resp_text(resp))
    return {
        "sql": (data.get("sql") or "").strip(),
        "notes": (data.get("notes") or "").strip(),
    }


def llm_make_insight(intent: str, params: Dict[str, Any], answer_table: List[Dict[str, Any]]) -> str:
    """
    LLM #2: Generate a concise Vietnamese insight from tabular data.

    Args:
        intent (str): High-level intent label (e.g., "auto", "top_products").
        params (Dict[str, Any]): Context (e.g., question, sql).
        answer_table (List[Dict[str, Any]]): Query results used for summarization.

    Returns:
        str: Plain-text insight (max ~2 sentences).
    """
    _config()

    # Keep payload short; clip rows to reduce token usage and encourage crisp answers
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
