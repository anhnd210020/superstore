# app/api/app.py
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict
from fastapi.middleware.cors import CORSMiddleware

from app.intents.router_llm import run_router_llm_first
from app.llm.llm_client import llm_make_insight

app = FastAPI(title="SalesInsightAI Q&A API", version="0.4.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

class AskPayload(BaseModel):
    question: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/ask")
def ask(payload: AskPayload) -> Dict[str, Any]:
    r = run_router_llm_first(payload.question)
    try:
        insight = llm_make_insight(r["params"]["intent"], r["params"], r["answer_table"])
    except Exception:
        insight = "Không tạo được insight từ LLM."
    # ✅ Chỉ trả về insight_text
    return {"insight_text": insight}
