# app/vis/chart_renderer.py
from __future__ import annotations

import base64
import io
from typing import Any, Dict, List

import matplotlib.pyplot as plt


def make_chart_png(
    rows: List[Dict[str, Any]],
    viz: Dict[str, Any],
    width: int = 1600, #900
    height: int = 700, #500
) -> Dict[str, Any]:
    """
    Render a simple chart (line/bar) to PNG base64 from rows and viz spec.

    Expected viz:
      {"chart_type":"line|bar","x":"...","y":"...","title":"...","sort":"x|y|none","limit":24}
    """
    if not rows or not viz:
        raise ValueError("rows and viz are required to render chart.")

    # Extract chart settings from the viz spec
    chart_type = str(viz.get("chart_type", "line")).lower()
    x_key = viz.get("x")
    y_key = viz.get("y")
    title = str(viz.get("title", ""))
    sort = str(viz.get("sort", "none")).lower()
    limit_raw = viz.get("limit")

    # Copy data to avoid mutating the original list
    data = rows[:]

    # Optional sorting based on X or Y axis
    if data and isinstance(data[0], dict):
        if sort == "x" and x_key in data[0]:
            data = sorted(data, key=lambda r: str(r.get(x_key)))
        elif sort == "y" and y_key in data[0]:
            data = sorted(
                data,
                key=lambda r: float(r.get(y_key) or 0.0),
                reverse=True,
            )

    # Limit number of records to plot (nếu có)
    if limit_raw is not None:
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = None
        if limit is not None and limit > 0:
            data = data[:limit]

    # Extract values for axes
    x_vals = [str(r.get(x_key)) for r in data]
    y_vals = [float(r.get(y_key) or 0.0) for r in data]

    # Create matplotlib figure with given width/height (in inches)
    plt.figure(figsize=(width / 100.0, height / 100.0), dpi=100)
    try:
        # Draw either a bar chart or line chart
        if chart_type == "bar":
            plt.bar(x_vals, y_vals)
        else:
            plt.plot(x_vals, y_vals, marker="o")

        # Basic chart styling
        plt.title(title)
        plt.xlabel(x_key)
        plt.ylabel(y_key)
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()

        # Save chart to memory buffer as PNG
        with io.BytesIO() as buf:
            plt.savefig(buf, format="png")
            data_bytes = buf.getvalue()
            png_b64 = base64.b64encode(data_bytes).decode("utf-8")
    finally:
        plt.close()

    # Return both raw bytes and base64 version of the PNG image
    return {
        "format": "png",
        "data_base64": png_b64,
        "data_bytes": data_bytes,
        "width": width,
        "height": height,
        "chart_type": chart_type,
        "x": x_key,
        "y": y_key,
        "title": title,
    }
