# app/vis/chart_store.py
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/ducanhhh/superstore/artifacts/charts")

def save_chart_image_dated(chart_image: bytes) -> str:
    """
    Save chart image as artifacts/charts/YYYY-MM-DD/HHMMSS.png.
    If multiple charts are saved within the same second, append milliseconds.
    Returns the absolute file path as a string.
    """
    now = datetime.now()  # uses the system timezone (e.g., Asia/Bangkok)
    date_dir = ROOT / now.strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)

    base_name = now.strftime("%H%M%S")
    fpath = date_dir / f"{base_name}.png"

    # Avoid overwriting if multiple images are saved in the same second
    if fpath.exists():
        ms = int(now.microsecond / 1000)
        fpath = date_dir / f"{base_name}_{ms:03d}.png"

    fpath.write_bytes(chart_image)
    return str(fpath)

def write_chart_insight_jsonl(png_path: str, question: str, insight_text: str) -> str:
    """
    Write a JSONL file next to the chart image with the same base name and a .jsonl extension.
    Each line contains: {timestamp, question, insight_text}.
    Returns the path to the .jsonl file.
    """
    p = Path(png_path)
    out = p.with_suffix(".jsonl")

    now = time.time()
    line = (
        '{'
        f'"timestamp": "{datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")}", '
        f'"question": {repr(question)}, '
        f'"insight_text": {repr(insight_text)}'
        '}'
    )

    with out.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

    return str(out)
