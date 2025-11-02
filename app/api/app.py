# app/api/app.py
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel
from app.dataops import insight_log
from app.vis import chart_store 
# Import the core pipeline that processes the user's question
from app.service import ask_pipeline

# Initialize the FastAPI application
app = FastAPI()

# Define the request body schema (input format)
class AskIn(BaseModel):
    question: str  # The user's natural language question

# Define the API endpoint for asking a question
@app.post("/ask", response_model=None)
def ask(in_: AskIn):
    result = ask_pipeline.ask_once(in_.question)

    chart_image = result.get("chart_image")
    if chart_image:
        saved_png = chart_store.save_chart_image_dated(chart_image)

        insight_text = result.get("insight_text", "")
        chart_store.write_chart_insight_jsonl(saved_png, in_.question, insight_text)

        return Response(content=chart_image, media_type="image/png")
    
    insight_text = result.get("insight_text", "")
    insight_log.log_insight(in_.question, insight_text)

    return {"insight_text": insight_text}