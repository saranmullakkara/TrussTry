"""
=====================================================================
  visualization/force_view.py

  Structure with each member coloured red (tension) or blue
  (compression), line thickness scaled by relative magnitude.

  Only change from the original: finish_axes() replaced by style_axes()
  and node / annotation colours pulled from the shared palette.
  No logic or API surface altered.

  Depends on: visualization.geometry_view (shared helpers), core.model
  (type hints only)
=====================================================================
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from visualization.geometry_view import (
    node_xy,
    draw_placeholder,
    style_axes,
    C_NODE,
    C_TEXT,
    C_AXES,
)

if TYPE_CHECKING:
    from core.model import Model

__all__ = ["draw_axial_forces"]

# Tension / compression colours – warm red and cool blue work well
# on the dark background (slightly brightened vs the stock defaults).
_C_TENSION     = "#ff6b6b"
_C_COMPRESSION = "#4f9eff"
_C_ZERO        = "#5a5a7a"


def draw_axial_forces(ax: Axes, model: "Model", results: dict) -> None:
    """Structure with each member coloured by tension/compression state,
    line thickness scaled by relative magnitude."""
    forces = results.get("element_axial_force") if results else None
    if not model.elements or not forces:
        draw_placeholder(ax, "No analysis results yet – run an analysis.")
        return

    ax.clear()
    node_ids, coords = node_xy(model)
    pos = {nid: coords[i] for i, nid in enumerate(node_ids)}

    max_abs_force = max((abs(f) for f in forces.values()), default=0.0)
    for elem in model.elements.values():
        if elem.node_i not in pos or elem.node_j not in pos:
            continue
        force = forces.get(elem.id, 0.0)
        if force > 1e-6:
            color = _C_TENSION
        elif force < -1e-6:
            color = _C_COMPRESSION
        else:
            color = _C_ZERO
        lw = 2 + 6 * (abs(force) / max_abs_force if max_abs_force > 0 else 0)
        xi, yi = pos[elem.node_i]
        xj, yj = pos[elem.node_j]
        ax.plot(
            [xi, xj], [yi, yj],
            color=color, linewidth=lw,
            zorder=1, solid_capstyle="round",
        )
        label = "T" if force > 1e-6 else ("C" if force < -1e-6 else "0")
        ax.annotate(
            f"E{elem.id}: {force:.1f} N ({label})",
            ((xi + xj) / 2, (yi + yj) / 2),
            fontsize=8, ha="center", va="center",
            color=C_TEXT,
            bbox=dict(boxstyle="round,pad=0.2", fc=C_AXES, alpha=0.85, ec="none"),
        )

    ax.scatter(coords[:, 0], coords[:, 1], s=80, c=C_NODE, zorder=2)
    for i, nid in enumerate(node_ids):
        ax.annotate(
            f"N{nid}", (coords[i, 0], coords[i, 1]),
            textcoords="offset points", xytext=(7, 7),
            fontsize=9, color=C_TEXT,
        )

    legend_elems = [
        Line2D([0], [0], color=_C_TENSION,     lw=3, label="Tension (+)"),
        Line2D([0], [0], color=_C_COMPRESSION, lw=3, label="Compression (−)"),
        Line2D([0], [0], color=_C_ZERO,        lw=3, label="~Zero-force"),
    ]
    leg = ax.legend(handles=legend_elems, loc="best", fontsize=9)
    leg.get_frame().set_facecolor("#1c1c2e")
    leg.get_frame().set_edgecolor("#3a3a5c")
    for text in leg.get_texts():
        text.set_color(C_TEXT)

    style_axes(ax, "Axial Forces  (T = tension, C = compression)", equal=True)
