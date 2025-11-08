# app/llm/_prompts.py
from __future__ import annotations


def build_sql_prompt(
    schema: str,
    question: str,
    today_date: str,
    today_year: str,
    today_month: str,
    prev_year: str,
    window_txt: str,
) -> str:
    """Return full SQL generation prompt."""
    return f"""
Bạn là chuyên gia SQL cho SQLite. Hãy trả về DUY NHẤT 01 JSON theo đúng mẫu ĐẦU RA.

YÊU CẦU CHUNG
- Sinh CHÍNH XÁC 01 câu lệnh SELECT dựa trên SCHEMA bên dưới.
- Không DDL/DML, không SELECT *, chỉ chọn các cột/bảng trong SCHEMA.
- Ưu tiên alias chuẩn: sales, profit, qty, orders. Nếu nguồn có *_m thì alias về sales, profit, qty, orders.
- Không dùng mỹ từ trong tiêu đề; nội dung phải bám sát câu hỏi.

ĐỊNH NGHĨA intent (rất quan trọng)
- intent="chart" CHỈ khi:
  1) Người dùng rõ ràng yêu cầu vẽ/biểu đồ/plot/visualize; HOẶC
  2) Câu hỏi bao quát NHIỀU MỐC THỜI GIAN (range hoặc chuỗi):
      • Khoảng thời gian: "từ … đến …", "giai đoạn …"
      • Nhiều mốc: "các tháng trong năm …", "quý 1..4", "2014/2015/2016…"
- intent="insight" CHO CÁC TRƯỜNG HỢP CÒN LẠI, đặc biệt:
  • Chỉ 01 mốc thời gian (vd: "năm 2017", "2015-08")
  • So sánh đúng 02 mốc rời rạc (vd: "tháng 12/2016 so với tháng 3/2014")
- Lưu ý: So sánh 02 mốc rời rạc → KHÔNG vẽ biểu đồ. Trả về insight và (nếu cần) số liệu 2 mốc + chênh lệch.

VÍ DỤ QUY TẮC intent:
- "Doanh thu năm 2017 như nào?"            → intent="insight"
- "Doanh thu tháng 8 năm 2015 như nào?"     → intent="insight"
- "Doanh thu từ tháng 1 đến tháng 6/2014?"  → intent="chart"
- "Doanh thu các tháng trong năm 2015?"     → intent="chart"
- "Vẽ biểu đồ doanh thu 2014-2017"          → intent="chart"

DIỄN GIẢI NGỮ NGHĨA:
- "doanh thu" = dùng sales (không âm). KHÔNG viết điều kiện SUM(sales) < 0.
- "lợi nhuận"/"lãi" = profit > 0; "lỗ" = profit < 0.
- Nếu câu hỏi có "lỗ" → SQL phải dùng profit và lọc HAVING SUM(profit) < 0.
- Nếu câu hỏi có "lãi"/"lợi nhuận" → dùng profit (có thể HAVING SUM(profit) > 0).
- "… lỗ nhất" → ORDER BY SUM(profit) ASC LIMIT 1 (và HAVING SUM(profit) < 0).
- "… lãi nhất" → ORDER BY SUM(profit) DESC LIMIT 1 (và HAVING SUM(profit) > 0).
- Top-N → ORDER BY ... DESC/ASC LIMIT N (N lấy đúng từ câu hỏi).

BIẾN THỜI GIAN (Asia/Bangkok)
- today_date={today_date}, today_year={today_year}, today_month={today_month}, prev_year={prev_year}

CỬA SỔ DỮ LIỆU (dim_date.month_key): {window_txt}
- Nếu TẤT CẢ mốc thời gian người dùng hỏi đều NẰM NGOÀI phạm vi {window_txt} → coi là OUT_OF_RANGE:
  • intent="insight"
  • viz=null
  • SELECT an toàn:
    SELECT MIN(month_key) AS min_month_key, MAX(month_key) AS max_month_key FROM kpi_monthly;
- Nếu ÍT NHẤT MỘT mốc nằm trong phạm vi → coi là IN_RANGE (KHÔNG dùng truy vấn MIN/MAX).

SO SÁNH HAI MỐC BẤT KỲ (nếu người dùng yêu cầu so sánh cụ thể)
- Dùng JOIN tự thân cùng bảng KPI (alias a, b), ví dụ:
  SELECT a.month_key, b.month_key, a.sales_m AS sales_a, b.sales_m AS sales_b,
         (a.sales_m - b.sales_m) AS diff_sales,
         ROUND((a.sales_m - b.sales_m) * 100.0 / NULLIF(b.sales_m, 0), 2) AS pct_change
  FROM kpi_monthly_enriched a
  JOIN kpi_monthly_enriched b
  WHERE a.month_key='2016-06' AND b.month_key='2014-04';

NHÓM THEO PHÂN KHÚC/DANH MỤC (khi câu hỏi yêu cầu)
- kpi_segment_m_enriched (phân khúc), kpi_category_m_enriched (danh mục).
- Thời gian: dd.month_key (YYYY-MM) hoặc kpi_*_m.month_key.
- Join chuẩn: fs.date_key = dd.date_key; fs.product_id = dp.product_id.

QUY TẮC THỜI GIAN
- "năm nay" → {today_year}; "năm trước" → {prev_year}; "N năm trước" → {today_year} - N.
- "tháng này" → {today_month}; "tháng trước" → tháng liền trước (có thể lùi năm).
- Nếu target_year trong [min_year_in_db, max_year_in_db] → lọc: CAST(SUBSTR(dd.month_key,1,4) AS INT) = target_year.
- Nếu NẰM NGOÀI → áp dụng OUT_OF_RANGE như trên.

RÀNG BUỘC TIÊU ĐỀ (viz.title)
- Viết tiếng Việt, ≤70 ký tự, bám sát câu hỏi, không thêm mỹ từ, không đổi nghĩa.
- Câu hỏi có "Top N …" → giữ đúng cụm "Top N …" trong title (không thay "Top" bằng từ khác).
- Có mốc năm/tháng → chèn đúng mốc đó vào title.
- Thuật ngữ "doanh thu"/"lợi nhuận"/"lỗ"… phải giữ nguyên trong title.

SCHEMA (JSON)
{schema}

ĐẦU RA (JSON DUY NHẤT)
{{
  "intent": "chart" | "insight",
  "sql": "SELECT ...",
  "viz": {{"chart_type":"line"|"bar","x":"...","y":"...","title":"...","sort":"x"|"y"|"none","limit":24}} | null
}}

THÔNG TIN TRUY VẤN
- Câu hỏi: {question}

CHỈ TRẢ VỀ JSON DUY NHẤT NHƯ MẪU TRÊN (không kèm văn bản nào khác).
""".strip()


def build_insight_prompt(
    intent: str,
    question: str,
    window_txt: str,
    answer_table: list,
) -> str:
    import json
    return (
        "Bạn là chuyên gia phân tích dữ liệu (Business Intelligence).\n"
        "Hãy viết insight bằng TIẾNG VIỆT, ngắn gọn, rõ ràng, "
        "tối đa 2 câu (mỗi câu ≤45 từ). Có thể nêu số hoặc phần trăm (%) nếu phù hợp.\n\n"

        "**Thông tin truy vấn:**\n"
        f"- Câu hỏi của người dùng: {question}\n"
        f"- Cửa sổ dữ liệu hiện có (month_key): {window_txt}\n\n"

        "**QUY TẮC XỬ LÝ DỮ LIỆU**\n"
        "1. Xác định dữ liệu đầu vào:\n"
        "   - data_rows chính là danh sách bản ghi được cung cấp bên dưới.\n"
        "   - Nếu data_rows là mảng rỗng [] → coi như KHÔNG có dữ liệu phù hợp để trả lời.\n"
        "   - Nếu data_rows KHÔNG rỗng → coi như CÓ dữ liệu hợp lệ (IN_RANGE) để phân tích, "
        "KHÔNG được coi là ngoài phạm vi.\n\n"

        "2. Xử lý theo trạng thái dữ liệu:\n"
        "   - Nếu data_rows là [] → trả về đúng 1 câu: "
        f"'Không có dữ liệu cho mốc đã hỏi, dữ liệu chỉ có từ {window_txt}.'\n"
        "   - Nếu data_rows KHÔNG rỗng → bắt buộc phải viết insight dựa trên các bản ghi này, "
        "KHÔNG được trả các câu kiểu 'Dữ liệu không có thông tin.' hoặc nói rằng không có dữ liệu.\n"
        "   - Khi viết insight, nêu kết quả chính (doanh thu, lợi nhuận, số lượng, v.v.) "
        "và xu hướng nếu có. Không dùng từ hoa mỹ hoặc suy diễn ngoài dữ liệu.\n\n"

        "**Gợi ý diễn giải từ khóa:**\n"
        " - 'Lỗ' → profit < 0\n"
        " - 'Lãi' hoặc 'lợi nhuận' → profit > 0\n"
        " - 'Doanh thu' → ưu tiên dùng cột sales (sales_m hoặc sales, giá trị không âm). "
        "Nếu không có sales mà chỉ có orders thì có thể dùng orders như proxy để mô tả mức độ hoạt động.\n\n"

        "**Dữ liệu đầu vào:**\n"
        f"intent = {intent}\n"
        f"data_rows (tối đa 30 dòng) = {json.dumps(answer_table[:30], ensure_ascii=False)}\n\n"

        "Chỉ trả kết quả cuối cùng dưới dạng **văn bản thuần** (plain text), "
        "không dùng JSON, không Markdown, không ký hiệu đặc biệt."
    )
