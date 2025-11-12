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

VAI TRÒ CỦA BẠN
- Nhiệm vụ chính: sinh CHÍNH XÁC 01 câu lệnh SELECT và GỢI Ý intent + cấu hình viz nếu phù hợp.
- intent ở đây chỉ là intent SƠ BỘ ("chart" hoặc "insight") do bạn đề xuất dựa trên câu hỏi.
- Hệ thống BI bên ngoài sẽ QUYẾT ĐỊNH CUỐI CÙNG có vẽ biểu đồ hay không,
  vì vậy bạn KHÔNG được mã hoá các chính sách khách hàng (ví dụ: khách không thích chart) vào trong intent.

YÊU CẦU CHUNG VỀ SQL
- Sinh CHÍNH XÁC 01 câu lệnh SELECT dựa trên SCHEMA bên dưới.
- Không DDL/DML, không SELECT *, chỉ chọn các cột/bảng trong SCHEMA.
- Ưu tiên alias chuẩn: sales, profit, qty, orders. Nếu nguồn có *_m thì alias về sales, profit, qty, orders.
- Không dùng mỹ từ trong tiêu đề; nội dung phải bám sát câu hỏi.

GỢI Ý CÁCH ĐỀ XUẤT intent SƠ BỘ (chỉ là gợi ý)
- intent="chart" khi câu hỏi:
  • Hỏi về xu hướng, so sánh theo NHIỀU mốc thời gian (chuỗi tháng, quý, năm, giai đoạn…).
  • Yêu cầu biểu đồ (line, bar) hoặc so sánh rõ ràng giữa các mốc thời gian.
- intent="insight" khi câu hỏi:
  • Tập trung vào 01 hoặc 02 mốc cụ thể (ví dụ: so sánh 2 tháng, 2 năm); HOẶC
  • Chủ yếu cần kết luận, giải thích, không nhất thiết phải xem cả đường xu hướng.
- Lưu ý: đây chỉ là intent sơ bộ để HỖ TRỢ hệ thống. Hệ thống có thể bỏ qua intent bạn gợi ý
  nếu dữ liệu không phù hợp hoặc cấu hình khách hàng không cho phép vẽ chart.

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
  • intent sơ bộ nên là "insight"
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

"- QUY TẮC CỘT GIẢM GIÁ (discount):\n"
"  * Cột 'discount' CHỈ tồn tại trong bảng fact_sales.\n"
"  * Nếu câu hỏi có từ 'giảm giá', 'discount', 'khuyến mãi', hoặc '% giảm', "
"    thì BẮT BUỘC dùng bảng fact_sales (alias fs) với cột fs.discount.\n"
"  * KHÔNG được dùng cột discount trong các bảng khác như kpi_prod_m, "
"    kpi_monthly, kpi_geo_m, v.v. vì chúng không có cột này.\n"
"  * Ví dụ đúng:\n"
"      SELECT dp.product_name, AVG(fs.discount) AS avg_discount\n"
"      FROM fact_sales AS fs\n"
"      JOIN dim_date AS dd ON fs.date_key = dd.date_key\n"
"      JOIN dim_product AS dp ON fs.product_id = dp.product_id\n"
"      WHERE dd.order_year = 2017 AND dd.order_month = 10\n"
"      GROUP BY dp.product_name\n"
"      ORDER BY avg_discount DESC\n"
"      LIMIT 1;\n"
"  * Ví dụ sai (tuyệt đối không dùng):\n"
"      SELECT ... FROM kpi_prod_m WHERE discount > 0\n"

"- QUY TẮC LỌC THEO NGÀY CỤ THỂ:\n"
"  * Nếu câu hỏi hỏi về MỘT NGÀY CỤ THỂ (ví dụ: 'ngày 11/11/2016', "
"    'ngày 5 tháng 3 năm 2015') thì:\n"
"    - ƯU TIÊN lọc trực tiếp trên fact_sales.order_date, "
"      dùng biểu thức DATE(order_date) = 'YYYY-MM-DD'.\n"
"    - KHÔNG dùng cột ngày trong dim_date (dd.date, dd.full_date, ...) "
"      để tránh sai khác định dạng.\n"
"  * Ví dụ đúng:\n"
"    SELECT COUNT(DISTINCT fs.order_id) AS orders\n"
"    FROM fact_sales AS fs\n"
"    WHERE DATE(fs.order_date) = '2016-11-11';\n"

ĐẦU RA (JSON DUY NHẤT)
{{
  "intent": "chart" | "insight",   // intent SƠ BỘ bạn đề xuất
  "sql": "SELECT ...",             // Câu lệnh SELECT duy nhất, hợp lệ cho SQLite
  "viz": null                      // Nếu không cần vẽ biểu đồ
         | {{
             "chart_type": "line" | "bar",
             "x": "...",          // tên cột trên trục X
             "y": "...",          // tên cột trên trục Y (thường là số: sales/profit/qty/...)
             "title": "...",      // tiêu đề biểu đồ bằng tiếng Việt, ngắn gọn
             "sort": "x" | "y" | "none",
             // CHỈ THÊM "limit" KHI CẦN GIỚI HẠN SỐ DÒNG (ranking/top-N).
             // KHÔNG ĐƯỢC THÊM "limit" CHO CÁC CÂU HỎI TIME SERIES (tháng/quý/năm liên tiếp).
             "limit": <số nguyên dương>   // (TÙY CHỌN)
           }}
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
    range_status: str = "UNKNOWN",
) -> str:
    import json
    return (
        "Bạn là chuyên gia phân tích dữ liệu (Business Intelligence).\n"
        "Hãy viết insight bằng TIẾNG VIỆT, ngắn gọn, rõ ràng, "
        "tối đa 2-3 câu (mỗi câu ≤80 từ). Có thể nêu số hoặc phần trăm (%) nếu phù hợp.\n\n"

        "**Thông tin truy vấn:**\n"
        f"- Câu hỏi của người dùng: {question}\n"
        f"- Cửa sổ dữ liệu hiện có (month_key): {window_txt}\n"
        f"- Trạng thái range_status do hệ thống cung cấp: {range_status} "
        "(OUT_OF_RANGE hoặc IN_RANGE).\n\n"

        "**Định nghĩa data_rows:**\n"
        " - data_rows là danh sách bản ghi đầu vào đã được hệ thống truy vấn sẵn.\n"
        " - Mỗi phần tử trong data_rows là một dict, chứa các cột như month_key, sales, profit, v.v.\n\n"

        "**QUY TẮC XỬ LÝ DỮ LIỆU**\n"
        "1. Xác định dữ liệu đầu vào:\n"
        "   - data_rows chính là danh sách bản ghi được cung cấp bên dưới.\n"
        "   - Nếu data_rows là mảng rỗng [] → coi như KHÔNG có dữ liệu phù hợp để trả lời.\n"
        "   - Nếu data_rows KHÔNG rỗng → coi như CÓ dữ liệu hợp lệ để phân tích.\n\n"

        "2. Xử lý theo trạng thái dữ liệu:\n"
        "   - TRƯỜNG HỢP A (OUT_OF_RANGE + data_rows trống):\n"
        "     + Điều kiện: range_status = 'OUT_OF_RANGE' VÀ data_rows = [].\n"
        "     + Khi đó phải trả ĐÚNG 1 câu duy nhất: "
        f"       'Không có dữ liệu cho mốc đã hỏi, dữ liệu chỉ có từ {window_txt}.'\n"
        "   - TRƯỜNG HỢP B (IN_RANGE + data_rows trống):\n"
        "     + Điều kiện: range_status = 'IN_RANGE' VÀ data_rows = [].\n"
        "     + Hiểu là: không có bản ghi nào thỏa điều kiện lọc (ví dụ không có bang nào lỗ).\n"
        "       → Phải trả ĐÚNG câu: 'Dữ liệu không có thông tin.' hoặc câu tương đương nghĩa.\n"
        "   - TRƯỜNG HỢP C (data_rows KHÔNG rỗng, bất kể range_status):\n"
        "     + HÃY GIẢ ĐỊNH rằng hệ thống đã truy vấn, lọc và sắp xếp data_rows "
        "       ĐÚNG theo câu hỏi (bao gồm các điều kiện như 'thứ 2', 'top 3', 'cao nhất', v.v.).\n"
        "     + Nhiệm vụ của bạn là CHỈ TẬP TRUNG vào việc diễn giải kết quả đó, "
        "       KHÔNG cần giải thích quá trình lọc, không cần nêu lý do thiếu dữ liệu kỹ thuật.\n"
        "     + TUYỆT ĐỐI KHÔNG được dùng các câu kiểu: "
        "       'Dữ liệu không có thông tin', 'Không đủ dữ liệu', "
        "       'Chỉ có một bản ghi nên không kết luận được', v.v. khi data_rows KHÔNG rỗng.\n"
        "     + Nếu data_rows chỉ có 1 dòng thì coi đó là KẾT QUẢ cuối cùng và "
        "       trả lời TRỰC TIẾP theo nghĩa câu hỏi. Ví dụ:\n"
        "       - 'Sản phẩm giảm giá mạnh nhất tháng 11/2017 là ...'\n"
        "       - 'Bang có doanh thu cao nhất là California.'\n"
        "     + Chỉ trong trường hợp TẤT CẢ các cột đều hoàn toàn vô nghĩa "
        "       (không có tên, không có bất kỳ số liệu nào liên quan đến câu hỏi) "
        "       thì mới được nói là 'Dữ liệu không đủ để trả lời', nhưng đây là trường hợp rất hiếm.\n"
        "   - Khi viết insight, ưu tiên nói THẲNG kết quả chính "
        "     (sản phẩm/bang/nhóm nào, cao hay thấp, lỗ hay lãi). "
        "     Không lan man giải thích lý do kỹ thuật, không mô tả cấu trúc dữ liệu.\n\n"

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