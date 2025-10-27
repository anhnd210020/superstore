"""
Pipeline to process user questions using LLM and database.
Steps:
1. LLM generates SQL from natural language.
2. Execute SQL on database.
3. LLM summarizes results into human-readable insight.
"""

from typing import Dict, Any, List

from app.llm import llm_client 
from app.intents import query_engine


def ask_once(question: str) -> Dict[str, Any]:
    """
    Execute the full pipeline one time:
    LLM (SQL generation) → Run SQL → LLM (insight generation) → Response.

    Args:
        question (str): Natural language question from the user.

    Returns:
        Dict[str, Any]: Structured response with SQL, table data, and insight.
    """
    # Step 1: Use LLM to generate SQL query from the user's question
    gen = llm_client.llm_generate_sql(question)
    sql: str = gen.get("sql", "")

    # Step 2: Execute the SQL query against local SQLite database
    rows: List[Dict[str, Any]] = query_engine.execute_sql(sql)

    # Step 3: Generate human-readable insight from SQL results
    insight: str = llm_client.llm_make_insight(
        intent="auto",
        params={"question": question, "sql": sql},
        answer_table=rows
    )
    # Final structured response
    return {
        "question": question,
        "insight_text": insight,
        "notes": gen.get("notes", "")
    }
