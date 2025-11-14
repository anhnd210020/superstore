import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path("/home/ducanhhh/superstore/artifacts/salesmart.db")
OUTPUT_PATH = Path("/home/ducanhhh/superstore/schema_catalog.json")

# Các bảng KHÔNG export cho LLM (vẫn tồn tại trong DB, chỉ là không cho vào schema_catalog.json)
EXCLUDED_FOR_LLM = {
    "state_year_profit",  # gây nhiễu cho câu hỏi lỗ/lãi theo bang + năm
}

# Mô tả bảng cho LLM (tùy chọn, có thể bổ sung dần)
TABLE_DESCRIPTIONS = {
    "kpi_geo_m": (
        "Bảng KPI theo bang và tháng. "
        "month_key = 'YYYY-MM'. "
        "Có các cột như state, sales_m, profit_m, qty_m. "
        "Dùng cho câu hỏi về doanh thu / lợi nhuận theo bang trong một năm hoặc giai đoạn."
    ),
    # thêm mô tả cho các bảng khác nếu muốn
}

def get_table_schema(conn, table_name: str) -> dict:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name});")
    columns = {row[1]: row[2] for row in cur.fetchall()}
    return {"description": "", "columns": columns}


def build_schema_catalog(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cur.fetchall() if not row[0].startswith("sqlite_")]

    schema = {"dialect": "sqlite", "tables": {}}

    for t in sorted(tables):
        schema["tables"][t] = get_table_schema(conn, t)

    date_range = None
    for candidate in ["fact_sales", "kpi_monthly"]:
        try:
            cur.execute(f"SELECT MIN(order_date), MAX(order_date) FROM {candidate};")
            row = cur.fetchone()
            if row and row[0] and row[1]:
                fmt = lambda d: datetime.fromisoformat(d).strftime("%Y-%m-%d")
                date_range = {
                    "min_order_date": fmt(row[0]),
                    "max_order_date": fmt(row[1]),
                }
                break
        except sqlite3.Error:
            continue

    if not date_range:
        try:
            cur.execute("SELECT MIN(month_dt), MAX(month_dt) FROM kpi_monthly;")
            row = cur.fetchone()
            if row and row[0] and row[1]:
                fmt = lambda d: datetime.fromisoformat(d).strftime("%Y-%m-%d")
                date_range = {
                    "min_order_date": fmt(row[0]),
                    "max_order_date": fmt(row[1]),
                }
        except sqlite3.Error:
            date_range = None

    if date_range:
        schema["data_summary"] = {"date_range": date_range}
    else:
        schema["data_summary"] = {"date_range": "unknown"}

    conn.close()
    return schema


def main():
    print("Building schema catalog from:", DB_PATH)
    schema = build_schema_catalog(DB_PATH)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    dr = schema.get("data_summary", {}).get("date_range", {})
    print("schema_catalog.json generated successfully!")
    print("Date range:", dr.get("min_order_date"), "→", dr.get("max_order_date"))
    print("Saved to:", OUTPUT_PATH)


if __name__ == "__main__":
    main()
