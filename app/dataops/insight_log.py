# app/dataops/insight_log.py
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

LOG_PATH = Path("artifacts/diary/insights_log.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def log_insight(question: str, insight_text: str) -> None:
    now = time.time()
    rec = {
        "timestamp": datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S"),
        "question": question,
        "insight_text": insight_text,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
