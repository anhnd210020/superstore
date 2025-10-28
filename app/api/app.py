# app/api/app.py
"""
Main FastAPI application entry point.

Auto behavior:
- If the question implies a chart intent: return image/png directly and
  include the short insight in the 'X-Insight' response header.
- Otherwise: return minimal JSON: {"insight_text": "..."}.
"""
from __future__ import annotations

from base64 import b64encode
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.service.ask_pipeline import ask_once

app = FastAPI()

# Serve saved charts at /static/...
STATIC_DIR = Path("artifacts/charts")
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class AskIn(BaseModel):
    question: str


def _resolve_image_path_from_url(image_url: str) -> Path:
    """
    Convert '/static/<fname>.png' to filesystem path 'artifacts/charts/<fname>.png'.
    """
    prefix = "/static/"
    if not image_url.startswith(prefix):
        raise ValueError("Invalid image_url.")
    fname = image_url[len(prefix) :]
    if "/" in fname or "\\" in fname:
        raise ValueError("Invalid file name.")
    return STATIC_DIR / fname


@app.post("/ask", response_model=None)
def ask(in_: AskIn):
    result = ask_once(in_.question)

    # Chart branch: ask_pipeline returns {"image_url": "...", "insight_text": "..."}
    image_url = result.get("image_url")
    if image_url:
        fpath = _resolve_image_path_from_url(image_url)
        if not fpath.exists():
            raise HTTPException(status_code=404, detail="Chart image not found.")

        png_bytes = fpath.read_bytes()
        insight_txt = (result.get("insight_text") or "") if isinstance(result, dict) else ""

        insight_b64 = b64encode(insight_txt.encode("utf-8")).decode("ascii")
        headers = {
            "X-Insight-Base64": insight_b64,
            "X-Insight-Encoding": "base64-utf8",
        }
        return Response(content=png_bytes, media_type="image/png", headers=headers)

    # Insight-only branch: ask_once returned {"insight_text": "..."}
    return result
