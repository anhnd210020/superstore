# app/api/app.py
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel

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
    # Call the main pipeline to handle the question and get result
    result = ask_pipeline.ask_once(in_.question)

    # If a chart (image) is returned, send it as PNG bytes
    image_bytes = result.get("image_bytes")
    if image_bytes:
        return Response(content=image_bytes, media_type="image/png")
    
    return result
