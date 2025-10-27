"""
Query Engine Module
-------------------
Responsible for executing SQL SELECT queries on the local SQLite database
and returning results as a list of dictionaries.
"""

from pathlib import Path
from typing import Dict, List, Any
import sqlite3

# Path to SQLite database file
DB_PATH = Path("artifacts/salesmart.db")


def execute_sql(sql: str) -> List[Dict[str, Any]]:
    """
    Execute a SELECT SQL query on the SQLite database.

    Args:
        sql (str): SQL query string. Only SELECT statements are allowed.

    Returns:
        List[Dict[str, Any]]: Query results in list of dictionaries format.

    Raises:
        ValueError: If SQL string is not a SELECT statement.
        FileNotFoundError: If the database file does not exist.
    """
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
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()  # Ensure the connection is closed even if an error occurs
