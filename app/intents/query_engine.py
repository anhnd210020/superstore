"""
Query Engine Module
-------------------
Responsible for executing SQL SELECT queries on the local SQLite database
and returning results as a list of dictionaries.
"""

from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import sqlite3

# Path to SQLite database file
DB_PATH = Path("artifacts/salesmart.db")

def execute_sql(sql: str) -> List[Dict[str, Any]]:
    # Ensure the query is a valid SELECT statement
    if not isinstance(sql, str) or not sql.strip().lower().startswith("select"):
        raise ValueError("Only SELECT statements are allowed.")

    # Ensure database exists before executing
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    # Connect to the SQLite database
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Enable column-name-based access

    try:
        cursor = conn.execute(sql)
        # print([dict(row) for row in cursor.fetchall()])
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.OperationalError as e:
        msg = str(e)
        if "ambiguous column name" in msg.lower():
            raise RuntimeError(
                "SQL error: ambiguous column name detected. "
                "Please ensure all columns are prefixed with table aliases "
                "(e.g., fs.product_id, dp.product_name, dd.month_key)."
            ) from e
        raise RuntimeError(f"SQLite execution error: {msg}") from e
    finally:
        conn.close()  # Ensure the connection is closed even if an error occurs

def get_month_key_range() -> Tuple[Optional[str], Optional[str]]:
    """
    Return the (min_month_key, max_month_key) range from available tables.

    Searches common time-dimension or KPI tables to determine the
    overall temporal coverage of the dataset.

    Returns:
        Tuple[Optional[str], Optional[str]]: (min_month_key, max_month_key)
        If not found, returns (None, None).
    """
    if not DB_PATH.exists():
        return None, None

    candidates = [
        ("dim_date", "month_key"),
        ("kpi_monthly", "month_key"),
        ("kpi_prod_m", "month_key"),
        ("kpi_cat_m", "month_key"),
        ("kpi_geo_m", "month_key"),
        ("kpi_segment_m", "month_key"),
        ("kpi_shipmode_m", "month_key"),
    ]

    conn = sqlite3.connect(DB_PATH)
    try:
        for table, col in candidates:
            try:
                cur = conn.execute(f"SELECT MIN({col}), MAX({col}) FROM {table}")
                mn, mx = cur.fetchone() or (None, None)
                if mn and mx:
                    return str(mn), str(mx)
            except sqlite3.Error:
                continue
        return None, None
    finally:
        conn.close()
