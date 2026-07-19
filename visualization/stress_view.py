"""
=====================================================================
  visualization/stress_view.py

  Structure coloured by element axial stress (coolwarm colormap, with
  a colorbar) – tension and compression stand out at a glance.

  Only change from the original: finish_axes() replaced by style_axes()
  and node / annotation colours pulled from the shared palette so the
  dark theme is consistent.  No logic or API surface altered.

  Depends on: visualization.geometry_view (shared helpers), core.model
  (type hints only)
=====================================================================
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize

from visualization.geometry_view import (
    node_xy,
    draw_placeholder,
    style_axes,
    C_NODE,
    C_TEXT,
    C_TEXT_DIM,
    C_AXES,
)

if TYPE_CHECKING:
    from core.model import Model

__all__ = ["draw_stress_contours"]


def draw_stress_contours(ax: Axes, model: "Model", results: dict) -> None:
    """Structure coloured by element axial stress (coolwarm, with a colorbar)."""
    stresses = results.get("element_stress") if results else None
    if not model.elements or not stresses:
        draw_placeholder(ax, "No analysis results yet – run an analysis.")
        return

    ax.clear()
    node_ids, coords = node_xy(model)
    pos = {nid: coords[i] for i, nid in enumerate(node_ids)}

    segments, colors, elems = [], [], []
    for elem in model.elements.values():
        if elem.node_i not in pos or elem.node_j not in pos:
            continue
        segments.append([pos[elem.node_i], pos[elem.node_j]])
        colors.append(stresses.get(elem.id, 0.0))
        elems.append(elem)

    if not segments:
        draw_placeholder(ax, "No analysis results yet – run an analysis.")
        return

    max_abs = max(np.max(np.abs(colors)), 1.0)
    norm = Normalize(vmin=-max_abs, vmax=max_abs)
    lc = LineCollection(segments, cmap="coolwarm", norm=norm, linewidths=5)
    lc.set_array(np.array(colors))
    ax.add_collection(lc)

    ax.scatter(coords[:, 0], coords[:, 1], s=80, c=C_NODE, zorder=3)
    for i, nid in enumerate(node_ids):
        ax.annotate(
            f"N{nid}", (coords[i, 0], coords[i, 1]),
            textcoords="offset points", xytext=(7, 7),
            fontsize=9, color=C_TEXT,
        )
    for elem, seg in zip(elems, segments):
        mid_x = (seg[0][0] + seg[1][0]) / 2
        mid_y = (seg[0][1] + seg[1][1]) / 2
        ax.annotate(
            f"{stresses[elem.id] / 1e6:.2f} MPa", (mid_x, mid_y),
            fontsize=8, ha="center", va="bottom",
            color=C_TEXT_DIM, fontweight="bold",
        )

    cbar = ax.figure.colorbar(lc, ax=ax)
    cbar.set_label("Axial Stress (Pa)  [+ tension / − compression]")
    ax.autoscale_view()
    style_axes(ax, "Element Axial Stress", equal=True, colorbar=cbar)
