# app/vis/chart_renderer.py
from __future__ import annotations

import base64
import io
import uuid
from pathlib import Path
from typing import Any, Dict, List

import matplotlib.pyplot as plt


def make_chart_png(
    rows: List[Dict[str, Any]],
    viz: Dict[str, Any],
    width: int = 900,
    height: int = 500,
) -> Dict[str, Any]:
    """
    Render a simple chart (line/bar) to PNG base64 from rows and viz spec.

    Expected viz:
      {"chart_type":"line|bar","x":"...","y":"...","title":"...","sort":"x|y|none","limit":24}
    """
    if not rows or not viz:
        raise ValueError("rows and viz are required to render chart.")

    chart_type = str(viz.get("chart_type", "line")).lower()
    x_key = viz.get("x")
    y_key = viz.get("y")
    title = str(viz.get("title", ""))
    sort = str(viz.get("sort", "none")).lower()
    limit = int(viz.get("limit", 24))

    data = rows[:]
    if data and isinstance(data[0], dict):
        if sort == "x" and x_key in data[0]:
            data = sorted(data, key=lambda r: str(r.get(x_key)))
        elif sort == "y" and y_key in data[0]:
            data = sorted(
                data,
                key=lambda r: float(r.get(y_key) or 0.0),
                reverse=True,
            )
    data = data[:limit]

    x_vals = [str(r.get(x_key)) for r in data]
    y_vals = [float(r.get(y_key) or 0.0) for r in data]

    plt.figure(figsize=(width / 100.0, height / 100.0), dpi=100)
    try:
        if chart_type == "bar":
            plt.bar(x_vals, y_vals)
        else:
            plt.plot(x_vals, y_vals, marker="o")

        plt.title(title)
        plt.xlabel(x_key)
        plt.ylabel(y_key)
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()

        with io.BytesIO() as buf:
            plt.savefig(buf, format="png")
            png_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    finally:
        plt.close()

    return {
        "format": "png",
        "data_base64": png_b64,
        "width": width,
        "height": height,
        "chart_type": chart_type,
        "x": x_key,
        "y": y_key,
        "title": title,
    }


def save_chart_base64_to_file(
    png_b64: str,
    out_dir: str = "artifacts/charts",
    prefix: str = "chart_",
) -> str:
    """
    Save base64 PNG to a file under out_dir and return the served image URL (/static/...).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    fname = f"{prefix}{uuid.uuid4().hex}.png"
    fpath = out / fname
    with open(fpath, "wb") as f:
        f.write(base64.b64decode(png_b64))

    return f"/static/{fname}"
