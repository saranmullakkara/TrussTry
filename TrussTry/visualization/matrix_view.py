"""
=====================================================================
  visualization/matrix_view.py

  Heatmap of the assembled global stiffness matrix K_global, labelled
  by DOF (ux/uy per node), with a colorbar.

  Only change from the original: finish_axes() replaced by style_axes()
  and tick / colorbar colours pulled from the shared palette so the
  dark theme is consistent.  No logic or API surface altered.

  Depends on: visualization.geometry_view (shared helpers), core.model
  (type hints only)
=====================================================================
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from matplotlib.axes import Axes

from visualization.geometry_view import draw_placeholder, style_axes, C_TEXT

if TYPE_CHECKING:
    from core.model import Model

__all__ = ["draw_global_stiffness_matrix"]


def draw_global_stiffness_matrix(ax: Axes, model: "Model", results: dict) -> None:
    """Heatmap of the assembled global stiffness matrix K_global."""
    K = results.get("K_global") if results else None
    if K is None:
        draw_placeholder(ax, "No analysis results yet – run an analysis.")
        return

    ax.clear()
    node_ids = list(results.get("displacements", {}).keys()) or list(model.nodes.keys())
    labels = []
    for nid in node_ids:
        labels += [f"N{nid}x", f"N{nid}y"]

    n = K.shape[0]
    vmax = np.max(np.abs(K)) if np.max(np.abs(K)) > 0 else 1.0
    im = ax.imshow(K, cmap="coolwarm", vmin=-vmax, vmax=vmax)

    if len(labels) == n:
        ax.set_xticks(range(n))
        ax.set_xticklabels(labels, rotation=90, fontsize=7, color=C_TEXT)
        ax.set_yticks(range(n))
        ax.set_yticklabels(labels, fontsize=7, color=C_TEXT)

    cbar = ax.figure.colorbar(im, ax=ax, label="Stiffness (N/m)")
    style_axes(
        ax,
        f"Global Stiffness Matrix K  ({n} × {n})",
        xlabel="", ylabel="", equal=False,
        colorbar=cbar,
    )
