# llm_client.py — Gemini client (force 2.0 Flash)
import os, re, json
from pathlib import Path
import google.generativeai as genai
from dotenv import load_dotenv

_GEMINI_MODEL = "gemini-2.0-flash"

# ---- .env path (chỉnh đúng đường dẫn của bạn) ----
ENV_PATH = Path("/home/ducanhhh/superstore/.env")

def _config():
    # Nạp .env đúng file, cho phép ghi đè biến sẵn có
    load_dotenv(dotenv_path=str(ENV_PATH), override=True)

    # Lấy key theo nhiều tên & làm sạch
    raw_key = (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_API_KEY_GEMINI")
    )
    if not raw_key:
        raise RuntimeError("Missing GEMINI_API_KEY env.")

    api_key = raw_key.strip().strip('"').strip("'")  # bỏ ngoặc/khoảng trắng thừa
    if not api_key:
        raise RuntimeError("Empty GEMINI_API_KEY after stripping.")
    genai.configure(api_key=api_key)

_JSON_RE = re.compile(r"\{[\s\S]*\}")

def _safe_json(s: str):
    m = _JSON_RE.search((s or "").strip())
    if not m:
        raise ValueError("LLM didn't return JSON.")
    return json.loads(m.group(0))

def _resp_text(resp) -> str:
    # Phòng khi SDK không set resp.text
    try:
        if getattr(resp, "text", None):
            return resp.text
        # fallback gom text từ candidates/parts
        cands = getattr(resp, "candidates", [])
        if cands and hasattr(cands[0], "content") and getattr(cands[0].content, "parts", None):
            return "".join(getattr(p, "text", "") for p in cands[0].content.parts)
    except Exception:
        pass
    return ""

def llm_parse_question(question: str) -> dict:
    _config()
    sys_prompt = """
        Bạn là bộ phân tích truy vấn bán hàng. Nhiệm vụ: chuyển câu hỏi tự nhiên (tiếng Việt) thành 1 JSON duy nhất theo đúng schema yêu cầu.

        [DATASET CONTEXT]
        Bộ dữ liệu Superstore (Mỹ), đã làm sạch cơ bản, ~9.800 dòng, 21 cột, giai đoạn 2014–2017. Mỗi dòng là 1 giao dịch bán hàng.

        Nhóm thuộc tính & cột chính:
        - Đơn hàng: Order ID, Order Date, Ship Date, Ship Mode
        - Khách hàng: Customer ID, Customer Name, Segment ∈ {Consumer, Corporate, Home Office}
        - Địa lý: Country, City, State, Postal Code, Region
        - Sản phẩm: Product ID, Category ∈ {Furniture, Office Supplies, Technology}, Sub-Category, Product Name
        - Kinh doanh: Sales, Quantity, Discount, Profit

        [QUY ƯỚC & GIỚI HẠN]
        - Thời gian mặc định: dữ liệu có từ 2014–2017. Nếu người dùng nói “tháng này/tháng trước” thì để null, backend sẽ tự resolve theo tháng có dữ liệu mới nhất.
        - Metric hợp lệ: sales | profit | orders | qty
        - Groupby hợp lệ: product | category | subcategory | region | state | segment | ship_mode
        - Không tự suy diễn số liệu; KHÔNG viết SQL; chỉ trả về JSON tham số để backend truy vấn KPI có sẵn.
        - Nếu câu hỏi mơ hồ về thời gian, ưu tiên intent “latest_month_overview”.

        [SCHEMA JSON BẮT BUỘC]
        {
        "intent": "top_n_by_metric_in_month | compare_mom_group | most_negative_profit | trend_range | latest_month_overview",
        "metric": "sales|profit|orders|qty",
        "groupby": "product|category|subcategory|region|state|segment|ship_mode|null",
        "topn": 5,
        "month_key": "YYYY-MM|null",
        "month_from": "YYYY-MM|null",
        "month_to": "YYYY-MM|null"
        }

        [HƯỚNG DẪN DIỄN GIẢI]
        - “Top/bán chạy/đứng đầu”: dùng intent top_n_by_metric_in_month (mặc định groupby=product nếu không nói rõ).
        - “So với tháng trước/MoM”: dùng intent compare_mom_group.
        - “Lỗ nhiều nhất/âm nhất”: dùng intent most_negative_profit (groupby mặc định=subcategory).
        - “Xu hướng/từ…đến…”: dùng intent trend_range (dùng month_from, month_to).
        - “Tổng quan tháng này/hiện tại”: dùng intent latest_month_overview.

        [ĐẦU RA]
        - Chỉ in DUY NHẤT 1 JSON object theo schema trên, không giải thích thêm.
    """
    user = f"Câu hỏi: {question}"
    model = genai.GenerativeModel(_GEMINI_MODEL)
    resp = model.generate_content([sys_prompt, user])
    return _safe_json(_resp_text(resp))

def llm_make_insight(intent: str, params: dict, answer_table: list[dict]) -> str:
    _config()
    prompt = f"""
Bạn là chuyên gia BI. Viết insight TIẾNG VIỆT ngắn gọn cho dữ liệu bán hàng.
- Tối đa 2 câu, <= 45 từ/câu, có số/%, tránh rườm rà.
intent={intent}
params={json.dumps(params, ensure_ascii=False)}
data_rows(<=10)={json.dumps(answer_table[:10], ensure_ascii=False)}
Chỉ trả văn bản insight (không JSON/markdown).
"""
    model = genai.GenerativeModel(_GEMINI_MODEL)
    resp = model.generate_content(prompt)
    return (_resp_text(resp) or "").strip()
