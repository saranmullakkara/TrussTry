"""
=====================================================================
  visualization/deformation_view.py

  Deformed shape overlay and standalone displacement-vector plots.

  Only change from the original: finish_axes() replaced by style_axes()
  and deformed/undeformed colours pulled from the shared palette tokens
  (C_DEFORMED, C_UNDEFORMED) so they match the dark theme.  No logic,
  no data flow, no API surface was altered.

  Depends on: visualization.geometry_view (shared helpers), core.model
  (type hints only)
=====================================================================
"""

from __future__ import annotations

from typing import List, Optional, Tuple, TYPE_CHECKING

import numpy as np
from matplotlib.axes import Axes

from visualization.geometry_view import (
    node_xy,
    span,
    draw_placeholder,
    style_axes,
    C_DEFORMED,
    C_UNDEFORMED,
    C_NODE,
    C_TEXT,
    C_TEXT_DIM,
)

if TYPE_CHECKING:
    from core.model import Model

__all__ = ["draw_deformed", "draw_displacement_vectors"]


# -----------------------------------------------------------------
# Shared internal helpers
# -----------------------------------------------------------------

def _deformed_coords(
    model: "Model", results: dict, scale: Optional[float] = None
) -> Tuple[List, np.ndarray, np.ndarray, np.ndarray, float]:
    """Computes exaggerated deformed coordinates for plotting."""
    node_ids, coords = node_xy(model)
    displacements = results.get("displacements", {})
    disp = np.array([displacements.get(nid, (0.0, 0.0)) for nid in node_ids])

    if scale is None:
        model_span = span(coords)
        max_disp = np.max(np.linalg.norm(disp, axis=1)) if disp.size else 0.0
        scale = 0.15 * model_span / max_disp if max_disp > 1e-12 else 1.0

    deformed = coords + scale * disp
    return node_ids, coords, deformed, disp, scale


def _overlay_displacement_vectors(
    ax: Axes, node_ids: List, coords: np.ndarray,
    deformed: np.ndarray, disp: np.ndarray,
) -> None:
    mags = np.linalg.norm(disp, axis=1)
    for i, nid in enumerate(node_ids):
        ax.annotate(
            "",
            xy=(deformed[i, 0], deformed[i, 1]),
            xytext=(coords[i, 0], coords[i, 1]),
            arrowprops=dict(arrowstyle="->", color="#fbbf24", linewidth=1.8),
        )
        ax.annotate(
            f"N{nid}\n|u|={mags[i]:.3e} m",
            (deformed[i, 0], deformed[i, 1]),
            textcoords="offset points", xytext=(8, 8),
            fontsize=8, color=C_TEXT_DIM,
        )


# -----------------------------------------------------------------
# Deformed shape view
# -----------------------------------------------------------------

def draw_deformed(
    ax: Axes,
    model: "Model",
    results: dict,
    scale: Optional[float] = None,
    show_vectors: bool = True,
) -> None:
    """Deformed vs undeformed overlay."""
    if not model.nodes or not results:
        draw_placeholder(ax, "No analysis results yet – run an analysis.")
        return

    ax.clear()
    node_ids, coords, deformed, disp, scale = _deformed_coords(
        model, results, scale
    )
    pos_u = {nid: coords[i] for i, nid in enumerate(node_ids)}
    pos_d = {nid: deformed[i] for i, nid in enumerate(node_ids)}

    for k, elem in enumerate(model.elements.values()):
        if elem.node_i not in pos_u or elem.node_j not in pos_u:
            continue
        xi, yi = pos_u[elem.node_i]
        xj, yj = pos_u[elem.node_j]
        ax.plot(
            [xi, xj], [yi, yj],
            linestyle="--", color=C_UNDEFORMED, linewidth=1.4,
            zorder=1, label="Undeformed" if k == 0 else None,
        )
        dxi, dyi = pos_d[elem.node_i]
        dxj, dyj = pos_d[elem.node_j]
        ax.plot(
            [dxi, dxj], [dyi, dyj],
            linestyle="-", color=C_DEFORMED, linewidth=2.4,
            zorder=2, label="Deformed (scaled)" if k == 0 else None,
        )

    ax.scatter(coords[:, 0], coords[:, 1], s=55, c=C_UNDEFORMED, zorder=3)
    ax.scatter(deformed[:, 0], deformed[:, 1], s=80, c=C_DEFORMED, zorder=4)

    if show_vectors:
        _overlay_displacement_vectors(ax, node_ids, coords, deformed, disp)

    if model.elements:
        leg = ax.legend(loc="best", fontsize=9)
        leg.get_frame().set_facecolor("#1c1c2e")
        leg.get_frame().set_edgecolor("#3a3a5c")
        for text in leg.get_texts():
            text.set_color(C_TEXT)

    style_axes(
        ax,
        f"Deformed vs Undeformed\n(displacements ×{scale:.1f} for visibility)",
        equal=True,
    )


# -----------------------------------------------------------------
# Displacement-vector-only view
# -----------------------------------------------------------------

def draw_displacement_vectors(
    ax: Axes, model: "Model", results: dict, scale: Optional[float] = None
) -> None:
    """Undeformed geometry with displacement-vector arrows only."""
    if not model.nodes or not results:
        draw_placeholder(ax, "No analysis results yet – run an analysis.")
        return

    ax.clear()
    node_ids, coords, deformed, disp, scale = _deformed_coords(
        model, results, scale
    )
    pos = {nid: coords[i] for i, nid in enumerate(node_ids)}

    for elem in model.elements.values():
        if elem.node_i not in pos or elem.node_j not in pos:
            continue
        xi, yi = pos[elem.node_i]
        xj, yj = pos[elem.node_j]
        ax.plot(
            [xi, xj], [yi, yj],
            linestyle="--", color=C_UNDEFORMED, linewidth=1.4, zorder=1,
        )

    ax.scatter(coords[:, 0], coords[:, 1], s=80, c=C_NODE, zorder=3)
    _overlay_displacement_vectors(ax, node_ids, coords, deformed, disp)
    style_axes(
        ax,
        f"Nodal Displacement Vectors\n(arrows ×{scale:.1f} for visibility)",
        equal=True,
    )
