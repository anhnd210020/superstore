# app/llm/_utils.py
from __future__ import annotations

import json
import re
from typing import Any, Dict

# Greedy JSON capture
_JSON_RE = re.compile(r"\{[\s\S]*\}")


def safe_json(text: str) -> Dict[str, Any]:
    """Return the first JSON object found in text, or raise."""
    match = _JSON_RE.search((text or "").strip())
    if not match:
        raise ValueError("LLM did not return a JSON object.")
    return json.loads(match.group(0))


def resp_text(resp: Any) -> str:
    """Extract plain text from Gemini response safely."""
    if getattr(resp, "text", None):
        return resp.text

    try:
        candidates = getattr(resp, "candidates", [])
        if candidates and hasattr(candidates[0], "content"):
            parts = getattr(candidates[0].content, "parts", None)
            if parts:
                return "".join(getattr(p, "text", "") for p in parts)
    except Exception:
        pass
    return ""