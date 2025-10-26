"""
query_engine.py
----------------
Chức năng:
- Kết nối đến SQLite DataMart (salesmart.db)
- Cung cấp các hàm truy vấn dữ liệu thật dựa trên IntentParams
- Không chứa LLM, không chứa rule-based parsing, không sinh insight
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from pathlib import Path
import sqlite3
import pandas as pd

# Đường dẫn DB (chuẩn hoá lại cho gọn)
DB_PATH = Path("artifacts/salesmart.db")

# ---- Dataclass giống bên LLM router để truyền params ----
@dataclass
class IntentParams:
    intent: Optional[str] = None
    month_key: Optional[str] = None
    month_from: Optional[str] = None
    month_to: Optional[str] = None
    topn: int = 5
    metric: str = "sales"           # sales | profit | orders | qty
    groupby: Optional[str] = None   # product|category|subcategory|region|state|segment|ship_mode

# ---- Utility: connect DB ----
def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy DB {DB_PATH} – cần chạy datamart_build.py & kpi_compute.py trước.")
    return sqlite3.connect(DB_PATH)

# ---- Map cột metric / bảng tương ứng ----
_METRIC_COL = {
    "sales": "sales_m",
    "profit": "profit_m",
    "orders": "orders_m",
    "qty": "qty_m"
}

_TABLE_MAP = {
    "product": "kpi_prod_m",
    "category": "kpi_cat_m",
    "subcategory": "kpi_cat_m",
    "region": "kpi_geo_m",
    "state": "kpi_geo_m",
    "segment": "kpi_segment_m",
    "ship_mode": "kpi_shipmode_m",
}

_COL_SELECT = {
    "product": "product_id, product_name",
    "category": "category",
    "subcategory": "category, subcategory",
    "region": "region",
    "state": "region, state",
    "segment": "segment",
    "ship_mode": "ship_mode"
}

# ---- Các hàm QUERY CHÍNH ----

def query_top_n_in_month(p: IntentParams) -> List[Dict[str, Any]]:
    """Truy vấn top N theo metric/groupby trong 1 tháng cụ thể"""
    table = _TABLE_MAP[p.groupby]
    metric_col = _METRIC_COL[p.metric]
    select_col = _COL_SELECT[p.groupby]

    sql = f"""
        SELECT {select_col}, {metric_col} AS metric_value
        FROM {table}
        WHERE month_key = ?
        ORDER BY metric_value DESC
        LIMIT ?
    """
    with _connect() as conn:
        df = pd.read_sql_query(sql, conn, params=[p.month_key, p.topn])
    return df.to_dict(orient="records")

def query_compare_mom_group(p: IntentParams) -> List[Dict[str, Any]]:
    """So sánh MoM theo group"""
    table = _TABLE_MAP[p.groupby]
    metric_col = _METRIC_COL[p.metric]
    select_col = _COL_SELECT[p.groupby]

    sql = f"""
        SELECT {select_col},
               {metric_col} AS cur_value,
               {metric_col}_mom AS diff_abs,
               {metric_col}_mom_pct AS diff_pct
        FROM {table}
        WHERE month_key = ?
        ORDER BY diff_pct DESC
        LIMIT ?
    """
    with _connect() as conn:
        df = pd.read_sql_query(sql, conn, params=[p.month_key, p.topn])
    return df.to_dict(orient="records")

def query_most_negative_profit(p: IntentParams) -> List[Dict[str, Any]]:
    """Lấy nhóm lỗ nặng nhất (profit âm)"""
    table = _TABLE_MAP[p.groupby]
    select_col = _COL_SELECT[p.groupby]

    sql = f"""
        SELECT {select_col}, profit_m AS profit_value
        FROM {table}
        WHERE month_key = ?
        ORDER BY profit_value ASC
        LIMIT ?
    """
    with _connect() as conn:
        df = pd.read_sql_query(sql, conn, params=[p.month_key, p.topn])
    return df.to_dict(orient="records")

def query_trend_range(p: IntentParams) -> List[Dict[str, Any]]:
    """Xu hướng metric từ month_from → month_to"""
    metric_col = _METRIC_COL[p.metric]
    wh = []
    params = []
    if p.month_from:
        wh.append("month_dt >= date(?||'-01')")
        params.append(p.month_from)
    if p.month_to:
        wh.append("month_dt <= date(?||'-01')")
        params.append(p.month_to)
    wh_sql = "WHERE " + " AND ".join(wh) if wh else ""

    sql = f"""
        SELECT month_key, {metric_col} AS metric_value
        FROM kpi_monthly
        {wh_sql}
        ORDER BY month_dt ASC
    """
    with _connect() as conn:
        df = pd.read_sql_query(sql, conn, params=params)
    return df.to_dict(orient="records")

def query_latest_overview(month_key: str) -> Dict[str, Any]:
    """Tổng quan 1 tháng (sales/profit/orders + MoM)"""
    sql = """
        SELECT * 
        FROM kpi_monthly
        WHERE month_key = ?
    """
    with _connect() as conn:
        df = pd.read_sql_query(sql, conn, params=[month_key])
    if df.empty:
        return {}
    return df.iloc[0].to_dict()
