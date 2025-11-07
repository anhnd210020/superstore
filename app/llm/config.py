# app/llm/_config.py
from __future__ import annotations

from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv

ENV_PATH = Path("/home/ducanhhh/superstore/.env")  # adjust if different


def configure_gemini() -> None:
    """Load API key from .env and configure Gemini SDK."""
    load_dotenv(dotenv_path=str(ENV_PATH), override=True)

    import os
    raw = (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_API_KEY_GEMINI")
    )
    if not raw:
        raise RuntimeError("Missing GEMINI_API_KEY (or GOOGLE_API_KEY[_GEMINI]).")

    api_key = raw.strip().strip('"').strip("'")
    if not api_key:
        raise RuntimeError("Empty GEMINI_API_KEY after stripping.")
    genai.configure(api_key=api_key)