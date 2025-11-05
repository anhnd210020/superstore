# app/llm/llm_client.py — Gemini client (SQLite SQL generation + insight)
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

import json
import os
import re

import google.generativeai as genai
from dotenv import load_dotenv

from app.intents import query_engine

GEMINI_MODEL = "gemini-2.0-flash"
ENV_PATH = Path("/home/ducanhhh/superstore/.env")  # adjust if different

# Greedy JSON capture (first object) anywhere in text.
_JSON_RE = re.compile(r"\{[\s\S]*\}")

# Relative-year patterns (Vietnamese phrasing).
_REL_YEARS_RE = re.compile(
    r"\b(\d{1,2})(?:\s*/\s*(\d{1,2})){0,10}\s*năm\s*trước\b", re.IGNORECASE
)
_SINGLE_REL_YEAR_RE = re.compile(r"\b(\d{1,2})\s*năm\s*trước\b", re.IGNORECASE)
_LAST_YEAR_RE = re.compile(r"\bnăm\s*trước\b", re.IGNORECASE)
_THIS_YEAR_RE = re.compile(r"\bnăm\s*nay\b", re.IGNORECASE)


def _config() -> None:
    """Load API key from .env and configure Gemini SDK."""
    # Keep .env loading deterministic; override process env if present.
    load_dotenv(dotenv_path=str(ENV_PATH), override=True)

    # Accept multiple env var names to reduce setup friction.
    raw = (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_API_KEY_GEMINI")
    )
    if not raw:
        raise RuntimeError("Missing GEMINI_API_KEY (or GOOGLE_API_KEY[_GEMINI]).")

    # Defensive trim around common .env quoting issues.
    api_key = raw.strip().strip('"').strip("'")
    if not api_key:
        raise RuntimeError("Empty GEMINI_API_KEY after stripping.")
    genai.configure(api_key=api_key)

def _safe_json(text: str) -> Dict[str, Any]:
    """Return the first JSON object found in text, or raise."""
    match = _JSON_RE.search((text or "").strip())
    if not match:
        raise ValueError("LLM did not return a JSON object.")
    return json.loads(match.group(0))


def _resp_text(resp: Any) -> str:
    """Extract plain text from a Gemini response object safely."""
    # Prefer .text when present (typical SDK shape).
    if getattr(resp, "text", None):
        return resp.text

    # Fallback: dig into candidates -> content.parts[].text
    try:
        candidates = getattr(resp, "candidates", [])
        if candidates and hasattr(candidates[0], "content"):
            parts = getattr(candidates[0].content, "parts", None)
            if parts:
                return "".join(getattr(p, "text", "") for p in parts)
    except Exception:
        pass
    return ""

def _normalize_question_dates(question: str, today_year: int) -> str:
    """
    Normalize relative years to absolute (VN):
    e.g., with today_year=2025: '8/9/10/11 năm trước' -> 'năm 2017/2016/2015/2014'.
    """
    q = question

    # Handle multi values: "8/9/10/11 năm trước"
    def _multi_sub(m: re.Match) -> str:
        nums = [m.group(1)]
        for i in range(2, 12):  # allow up to ~11 items
            g = m.group(i)
            if g is None:
                break
            nums.append(g)
        years: List[str] = []
        for n in nums:
            try:
                k = int(n)
                if 0 <= k <= 50:  # sanity bound
                    years.append(str(today_year - k))
            except ValueError:
                continue
        return "năm " + "/".join(years) if years else m.group(0)

    q = _REL_YEARS_RE.sub(_multi_sub, q)

    # Single: "10 năm trước"
    def _single_sub(m: re.Match) -> str:
        try:
            k = int(m.group(1))
            if 0 <= k <= 50:
                return f"năm {today_year - k}"
        except ValueError:
            pass
        return m.group(0)

    q = _SINGLE_REL_YEAR_RE.sub(_single_sub, q)

    # Bare "năm trước" and "năm nay"
    q = _LAST_YEAR_RE.sub(f"năm {today_year - 1}", q)
    q = _THIS_YEAR_RE.sub(f"năm {today_year}", q)
    return q

def _build_sql_prompt(schema: str, today_date: str, today_year: str,
                      today_month: str, prev_year: str, window_txt: str) -> str:
    """Compact, prescriptive SQL+viz instruction block for Gemini."""
    # Keep prompt terse; enforce JSON-only with minimal rules.
    return f"""
Bạn là chuyên gia SQL cho SQLite. Trả về **DUY NHẤT** 1 JSON theo mẫu bên dưới.

YÊU CẦU
- Viết đúng 1 câu SELECT dựa trên SCHEMA.
- intent:
  * "chart" CHỈ khi người dùng rõ ràng yêu cầu vẽ/biểu đồ/plot/visualize.
  * "insight" cho các trường hợp còn lại.
- Nếu intent="chart", thêm viz tối thiểu:
  {{chart_type: "line"|"bar", x: "...", y: "...", title: "việt ngắn", sort: "x"|"y"|"none", limit: 24}}
- Thêm trường draw_chart (true/false) để chỉ định có vẽ biểu đồ hay không.

QUY TẮC CHỌN INTENT (rất quan trọng)
- Nếu câu hỏi chỉ chứa **một mốc thời gian duy nhất** (ví dụ: “năm 2017”, “tháng 2015-08”) → intent="insight", draw_chart=false.
- Chỉ vẽ biểu đồ khi câu hỏi bao quát **nhiều mốc thời gian** (range hoặc chuỗi):
  • Khoảng thời gian: “từ … đến …”, “giai đoạn …”
  • Tập nhiều mốc: “các tháng trong năm …”, “quý 1..4”, “2014/2015/2016…”
- Ví dụ ⇒ intent:
  • “Doanh thu năm 2017 như nào?” → insight, draw_chart=false
  • “Doanh thu tháng 8 năm 2015 như nào?” → insight, draw_chart=false
  • “Doanh thu từ tháng 1 đến tháng 6 năm 2014?” → chart, draw_chart=true
  • “Doanh thu các tháng trong năm 2015?” → chart, draw_chart=true

  DIỄN GIẢI NGỮ NGHĨA (cực kỳ quan trọng)
- "doanh thu" = sales. Doanh thu **không âm**; KHÔNG viết điều kiện `SUM(sales) < 0`.
- "lợi nhuận", "lãi" = profit > 0; "lỗ" = profit < 0.
- Nếu câu hỏi có "lỗ" → trong SQL phải dùng **profit** và lọc **`HAVING SUM(profit) < 0`**.
- Nếu câu hỏi có "lãi"/"lợi nhuận" → dùng **profit** (có thể `HAVING SUM(profit) > 0`).
- "… lỗ nhất" → `ORDER BY SUM(profit) ASC LIMIT 1` (kèm `HAVING SUM(profit) < 0`).
- "… lãi nhất" → `ORDER BY SUM(profit) DESC LIMIT 1` (kèm `HAVING SUM(profit) > 0`).
- Top-N: dùng `ORDER BY ... DESC/ASC LIMIT N` tùy ngữ nghĩa; ghi rõ N từ câu hỏi.

RÀNG BUỘC TIÊU ĐỀ (title) — PHẢI BÁM SÁT CÂU HỎI
- Tiêu đề viết tiếng Việt, ≤ 70 ký tự, **không thêm mỹ từ/không đổi nghĩa**.
- Nếu câu hỏi có “Top N …” → **giữ đúng cụm “Top N …” trong title** (không thay “Top” bằng từ khác).
  Nếu câu hỏi kiểu "Top các danh mục lỗ nhiều nhất năm 2017?" (không có N) thì có thể bỏ "Top" trong title,
  ví dụ: "Các danh mục lỗ nhiều nhất năm 2017".
- Nếu câu hỏi có mốc năm/tháng → **chèn đúng mốc đó** vào title (vd: “2017”).
- Nếu câu hỏi nói “doanh thu”, “lợi nhuận”, etc → title **phải giữ đúng thuật ngữ đó**.

BIẾN THỜI GIAN (Asia/Bangkok)
- today_date={today_date}, today_year={today_year}, today_month={today_month}, prev_year={prev_year}

CỬA SỔ DỮ LIỆU (dim_date.month_key): {window_txt}
- Nếu mốc hỏi NẰM NGOÀI phạm vi: đặt intent="insight", viz=null, notes="OUT_OF_RANGE"
  và SELECT an toàn:
  SELECT MIN(month_key) AS min_month_key, MAX(month_key) AS max_month_key FROM kpi_monthly;
- Nếu người dùng yêu cầu so sánh HAI MỐC thời gian bất kỳ (vd: “tháng 6/2016 và tháng 4/2014”, “năm 2017 với 2015”) →
  sử dụng phép JOIN giữa hai alias (a, b) của cùng bảng KPI (vd: kpi_monthly_enriched).
  Ví dụ:
  SELECT a.month_key, b.month_key, a.sales_m, b.sales_m,
         (a.sales_m - b.sales_m) AS diff_sales,
         ROUND((a.sales_m - b.sales_m)*100.0/b.sales_m, 2) AS pct_change
  FROM kpi_monthly_enriched a
  JOIN kpi_monthly_enriched b
  WHERE a.month_key='2016-06' AND b.month_key='2014-04';
- Nếu người dùng hỏi theo nhóm (segment/category) → dùng bảng tương ứng:
  kpi_segment_m_enriched hoặc kpi_category_m_enriched.
- Nếu bất kỳ mốc năm/tháng người dùng hỏi nằm trong {window_txt} thì TUYỆT ĐỐI KHÔNG đặt notes="OUT_OF_RANGE" và không dùng truy vấn MIN/MAX. 
Chỉ dùng OUT_OF_RANGE khi tất cả mốc đều nằm ngoài.

QUY TẮC THỜI GIAN
- "năm nay"→{today_year}; "năm trước"→{prev_year}; "N năm trước"→{today_year}-N
- "tháng này"→{today_month}; "tháng trước"→tháng liền trước (có thể lùi năm)
- Nếu target_year ∈ [min_year_in_db, max_year_in_db] → lọc:
  CAST(SUBSTR(dd.month_key,1,4) AS INT)=target_year
- Nếu NẰM NGOÀI → áp dụng OUT_OF_RANGE như trên.

SCHEMA (JSON)
{schema}

HƯỚNG DẪN TRUY VẤN & ALIAS
- Chỉ dùng cột/bảng trong schema; không DDL/DML; không SELECT *.
- Thời gian: dd.month_key (YYYY-MM) hoặc kpi_*_m.month_key.
- Join chuẩn: fs.date_key=dd.date_key; fs.product_id=dp.product_id.
- Tổng hợp ví dụ (ALIAS CHUẨN): SUM(fs.sales) AS sales, SUM(fs.profit) AS profit, SUM(fs.qty) AS qty, COUNT(DISTINCT fs.order_id) AS orders.
- Nếu nguồn có *_m → alias về tên chuẩn: sales_m AS sales, profit_m AS profit, qty_m AS qty, orders_m AS orders.
- Với câu hỏi **một mốc thời gian duy nhất**, phải trả về **giá trị số cụ thể** (ví dụ tổng doanh thu/năm đó) → intent="insight", draw_chart=false.
- Tiêu đề biểu đồ phải tiếng Việt, ngắn, bám sát câu hỏi.

ĐẦU RA (JSON DUY NHẤT)
{{
  "intent": "chart"|"insight",
  "draw_chart": false|true,
  "reason": "...",
  "sql": "SELECT ...",
  "notes": "...",
  "viz": {{"chart_type":"...","x":"...","y":"...","title":"...","sort":"...","limit":24}} | null
}}
""".strip()


def llm_generate_sql(question: str, schema_path: str = "schema_catalog.json") -> Dict[str, Any]:
    """Ask Gemini to generate a single SELECT SQL and optional viz spec."""
    _config()

    schema_file = Path(schema_path)
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")
    schema = schema_file.read_text(encoding="utf-8")

    # Compute current dates in Asia/Bangkok for consistent relative interpretation.
    now_bkk = datetime.now(ZoneInfo("Asia/Bangkok"))
    today_date = now_bkk.strftime("%Y-%m-%d")
    today_year = now_bkk.strftime("%Y")
    today_month = now_bkk.strftime("%Y-%m")
    prev_year = str(now_bkk.year - 1)

    # Pre-normalize relative-year phrasing before sending to LLM.
    norm_question = _normalize_question_dates(question, now_bkk.year)

    # Retrieve data window for guardrails and user messaging.
    mn, mx = query_engine.get_month_key_range()

    window_txt = f"{mn} đến {mx}" if (mn and mx) else "KHÔNG RÕ"

    sys_prompt = _build_sql_prompt(
        schema=schema,
        today_date=today_date,
        today_year=today_year,
        today_month=today_month,
        prev_year=prev_year,
        window_txt=window_txt,
    )

    # Keep user message separate for better grounding.
    user_msg = (
    f"Câu hỏi (đã chuẩn hoá thời gian): {norm_question}\n"
)

    model = genai.GenerativeModel(
    GEMINI_MODEL,
    generation_config={
        "temperature": 0.0,
    },
)

    resp = model.generate_content([sys_prompt, user_msg])

    data = _safe_json(_resp_text(resp))
    print("LLM generated SQL:", data)
    return {
        "intent": (data.get("intent") or "insight").strip(),
        "draw_chart": bool(data.get("draw_chart")),
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
    """Ask Gemini to produce a concise Vietnamese insight (<= 2 sentences)."""
    _config()

    # Provide window again so the LLM can decide OUT_OF_RANGE messaging.
    mn, mx = query_engine.get_month_key_range()
    window_txt = f"{mn} đến {mx}" if (mn and mx) else "KHÔNG RÕ"

    prompt = (
    "Bạn là chuyên gia BI. Viết insight TIẾNG VIỆT ngắn gọn (≤2 câu, ≤45 từ/câu),"
    " có thể nêu số/% khi phù hợp.\n"
    f"Câu hỏi của người dùng là: {params.get('question')}.\n"
    f"- Cửa sổ dữ liệu (month_key): {window_txt}\n"
    "- QUY TẮC:\n"
    "  * Xác định phạm vi mốc thời gian trong câu hỏi so với cửa sổ trên:\n"
    "    - Nếu **bất kỳ mốc** nằm TRONG cửa sổ → coi là **IN_RANGE**.\n"
    "    - Chỉ khi **tất cả mốc** đều ngoài cửa sổ → coi là **OUT_OF_RANGE**.\n"
    "  * Nếu data_rows **trống** hoặc chỉ gồm min/max-window và trạng thái là **OUT_OF_RANGE** → chỉ trả: "
    f"'Không có dữ liệu cho mốc đã hỏi, dữ liệu chỉ có từ {window_txt}.'\n"
    "  * Nếu data_rows **trống** nhưng trạng thái là **IN_RANGE** (ví dụ lọc 'lỗ' mà không có nhóm nào lỗ) → chỉ trả: "
    f"'Dữ liệu không có thông tin cho mốc đã hỏi trong phạm vi {window_txt}.'\n"
    "  * Nếu có dữ liệu hợp lệ → tóm tắt ngắn, nêu số chính (sales/profit/qty) khi phù hợp. Tránh mỹ từ.\n"
    "Gợi ý diễn giải:\n"
    "  - 'lỗ' → dựa trên profit âm; 'lãi/lợi nhuận' → profit dương; 'doanh thu' → sales (không âm).\n"
    f"intent={intent}\n"
    f"data_rows(<=10)={json.dumps(answer_table[:10], ensure_ascii=False)}\n"
    "Chỉ trả văn bản (không JSON/markdown)."
)

    model = genai.GenerativeModel(
    GEMINI_MODEL,
    generation_config={
        "temperature": 0.0,
    },
)
    resp = model.generate_content(prompt)
    print("LLM generated insight:", _resp_text(resp))
    return (_resp_text(resp) or "").strip()
