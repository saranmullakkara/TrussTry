"""
=====================================================================
  visualization/geometry_view.py

  Undeformed-structure rendering, plus the shared matplotlib helpers
  every other view in this package builds on (node/element lookup,
  support markers, axis styling, the "no results yet" placeholder).

  Why this file is first in the build order: deformation_view.py,
  stress_view.py, force_view.py, and matrix_view.py all import their
  shared helpers from here. Nothing in this file imports from any of
  them, so the dependency arrow inside visualization/ only ever
  points at geometry_view.py -- never in a circle.

  Ported from results_canvas.py's ResultsCanvas class, with one
  structural change: every method becomes a plain function that takes
  a matplotlib ``Axes`` it draws into, instead of a method on a
  FigureCanvasQTAgg subclass. That's what keeps this package Qt-free.
  gui/canvas.py (or gui/results_panel.py) owns the actual
  FigureCanvasQTAgg / Figure and hands these functions its own ax;
  visualization/ never creates a Qt widget or imports PySide6.

  Visual design
  -------------
  All views share a dark-theme palette defined once here and applied
  via style_axes().  Downstream views (deformation, stress, force,
  matrix) call style_axes() instead of the old finish_axes() and
  automatically inherit the look without any per-file colour choices.

  finish_axes() is kept as a thin alias of style_axes() so any
  external code that calls it continues to work unchanged.

  Palette tokens (module-level, referenced by all view modules)
  ─────────────────────────────────────────────────────────────
  C_BG          canvas / figure background
  C_AXES        axes area background
  C_GRID        subtle grid lines
  C_TEXT        primary axis labels and tick text
  C_TEXT_DIM    secondary labels (element numbers, node annotations)
  C_ELEMENT     default undeformed member colour
  C_NODE        default undeformed node colour
  C_HIGHLIGHT   pending-start node in add-element mode
  C_SUPPORT     support triangle fill
  C_DEFORMED    deformed member colour (used by deformation_view)
  C_UNDEFORMED  ghost undeformed member in deformed view

  Future compatibility notes
  --------------------------
  - draw_grid() already accepts a duck-typed config object; visible grid
    (Phase B) only needs config.visible = True, no code changes.
  - draw_undeformed() accepts drag_pos and highlight_node_id; box /
    multi-selection can be added by passing extra highlight sets.
  - style_axes() accepts a ``colorbar`` kwarg so result views that add
    a colorbar can hand it in and get consistent label styling for free.

  Depends on: core.model (type hints only)
=====================================================================
"""

from __future__ import annotations

from typing import List, Optional, Tuple, TYPE_CHECKING

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure

if TYPE_CHECKING:
    from core.model import Model

__all__ = [
    # data helpers
    "node_xy",
    "span",
    # palette tokens (imported by downstream view modules)
    "C_BG",
    "C_AXES",
    "C_GRID",
    "C_TEXT",
    "C_TEXT_DIM",
    "C_ELEMENT",
    "C_NODE",
    "C_HIGHLIGHT",
    "C_SUPPORT",
    "C_DEFORMED",
    "C_UNDEFORMED",
    # drawing helpers
    "draw_placeholder",
    "draw_supports",
    "style_axes",
    "finish_axes",   # kept for backward compatibility
    "draw_grid",
    "draw_undeformed",
]


# -----------------------------------------------------------------
# Palette – single source of truth for all views
# -----------------------------------------------------------------
C_BG         = "#0f0f17"   # figure / canvas background
C_AXES       = "#141420"   # axes area background
C_GRID       = "#26263a"   # subtle grid lines
C_TEXT       = "#c8c8d8"   # axis labels, tick marks
C_TEXT_DIM   = "#7878a0"   # secondary annotations (element labels)
C_ELEMENT    = "#4f9eff"   # undeformed member
C_NODE       = "#e8e8f0"   # undeformed node (white-ish on dark bg)
C_HIGHLIGHT  = "#ff5f7e"   # pending add-element start node
C_SUPPORT    = "#34d399"   # support triangle
C_DEFORMED   = "#ff6b6b"   # deformed member (used by deformation_view)
C_UNDEFORMED = "#3a3a5c"   # ghost undeformed member in deformed view


# -----------------------------------------------------------------
# Data helpers – reused by every other view module
# -----------------------------------------------------------------

def node_xy(model: "Model") -> Tuple[List, np.ndarray]:
    """Returns (node_ids, coords) with coords as an (N, 2) array in
    the same order as node_ids."""
    node_ids = list(model.nodes.keys())
    coords = np.array(
        [[model.nodes[nid].x, model.nodes[nid].y] for nid in node_ids]
    )
    return node_ids, coords


def span(coords: np.ndarray) -> float:
    """Characteristic size of the model's bounding box, used to scale
    marker offsets and displacement exaggeration. Never returns
    (near-)zero, so callers can safely divide by it."""
    if coords.size == 0:
        return 1.0
    spread = max(np.ptp(coords[:, 0]), np.ptp(coords[:, 1]))
    return spread if spread > 1e-9 else 1.0


# -----------------------------------------------------------------
# Shared drawing helpers
# -----------------------------------------------------------------

def draw_placeholder(ax: Axes, message: str) -> None:
    """Clears ax and shows a centred placeholder message on the dark
    background – used when there is nothing meaningful to plot yet."""
    fig = ax.figure
    fig.patch.set_facecolor(C_BG)
    ax.clear()
    ax.set_facecolor(C_AXES)
    ax.text(
        0.5, 0.5, message,
        ha="center", va="center",
        fontsize=11, color=C_TEXT_DIM,
        transform=ax.transAxes, wrap=True,
    )
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)


def draw_supports(
    ax: Axes, model: "Model", node_ids: List, coords: np.ndarray
) -> None:
    """Marks supported nodes with a filled triangle below the node."""
    s = span(coords)
    offset = 0.13 * s
    for i, nid in enumerate(node_ids):
        if nid not in model.boundary_conditions:
            continue
        bc = model.boundary_conditions[nid]
        x, y = coords[i, 0], coords[i, 1]

        if bc.fix_x and bc.fix_y:
            # Pin: solid filled triangle pointing up
            ax.scatter(
                [x], [y - offset],
                marker="^", s=260, c=C_SUPPORT,
                edgecolors=C_SUPPORT, linewidths=0,
                zorder=5, alpha=0.95,
            )
        elif bc.fix_y:
            # Roller (Y only): outline triangle
            ax.scatter(
                [x], [y - offset],
                marker="^", s=200, facecolors="none",
                edgecolors=C_SUPPORT, linewidths=1.8,
                zorder=5, alpha=0.9,
            )
        else:
            # Roller (X only): rotated outline triangle
            ax.scatter(
                [x - offset], [y],
                marker=">", s=200, facecolors="none",
                edgecolors=C_SUPPORT, linewidths=1.8,
                zorder=5, alpha=0.9,
            )


def style_axes(
    ax: Axes,
    title: str,
    xlabel: str = "X (m)",
    ylabel: str = "Y (m)",
    equal: bool = True,
    colorbar=None,
) -> None:
    """
    Apply the shared dark-theme styling to *ax* and its parent Figure.

    Parameters
    ----------
    ax       : the Axes to style
    title    : chart title (supports ``\\n`` for two-line titles)
    xlabel   : x-axis label (pass ``""`` to suppress)
    ylabel   : y-axis label (pass ``""`` to suppress)
    equal    : if True set aspect ratio to equal (geometry / deformed views)
    colorbar : if a Colorbar object is supplied its label and tick colours
               are updated to match the dark palette

    Future extensions
    -----------------
    Extra keyword arguments can be added here (e.g. ``legend_handles``)
    without touching any of the four downstream view modules.
    """
    fig: Figure = ax.figure

    # Figure and axes backgrounds
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_AXES)

    # Spines: keep left + bottom only, colour them to match the grid
    for side, spine in ax.spines.items():
        if side in ("top", "right"):
            spine.set_visible(False)
        else:
            spine.set_color(C_GRID)
            spine.set_linewidth(0.8)

    # Grid
    ax.grid(True, color=C_GRID, linestyle="--", linewidth=0.6, alpha=0.7)
    ax.set_axisbelow(True)

    # Tick and label colours
    ax.tick_params(colors=C_TEXT, labelsize=9, length=3)
    ax.xaxis.label.set_color(C_TEXT)
    ax.yaxis.label.set_color(C_TEXT)

    # Title and axis labels
    ax.set_title(title, color=C_TEXT, fontsize=11, fontweight="normal", pad=8)
    if xlabel:
        ax.set_xlabel(xlabel, color=C_TEXT, fontsize=9)
    if ylabel:
        ax.set_ylabel(ylabel, color=C_TEXT, fontsize=9)

    # Aspect ratio
    if equal:
        ax.set_aspect("equal", adjustable="datalim")

    # Colorbar styling (optional – result views pass theirs in)
    if colorbar is not None:
        colorbar.ax.yaxis.set_tick_params(color=C_TEXT, labelcolor=C_TEXT)
        colorbar.outline.set_edgecolor(C_GRID)
        colorbar.set_label(colorbar.ax.get_ylabel(), color=C_TEXT)

    fig.tight_layout()


# Backward-compatibility alias: finish_axes() → style_axes()
def finish_axes(
    ax: Axes,
    title: str,
    xlabel: str = "X (m)",
    ylabel: str = "Y (m)",
    equal: bool = True,
) -> None:
    """Deprecated alias for style_axes(). Kept so external callers
    that import finish_axes directly continue to work unchanged."""
    style_axes(ax, title, xlabel=xlabel, ylabel=ylabel, equal=equal)


def draw_grid(ax: Axes, config: object) -> None:
    """Draw background snap-grid lines at ``config.spacing`` intervals.

    Duck-typed: any object with ``.visible`` (bool) and ``.spacing``
    (float > 0) works.  When ``config.visible`` is False (the default)
    this is a cheap no-op – no cost until the user enables the visible
    grid (future Phase B).
    """
    visible = getattr(config, "visible", False) if config is not None else False
    if not visible:
        return

    spacing = getattr(config, "spacing", None)
    if not spacing or spacing <= 0:
        return

    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()

    x = np.floor(xmin / spacing) * spacing
    while x <= xmax:
        ax.axvline(x, color=C_GRID, linewidth=0.5, zorder=0)
        x += spacing

    y = np.floor(ymin / spacing) * spacing
    while y <= ymax:
        ax.axhline(y, color=C_GRID, linewidth=0.5, zorder=0)
        y += spacing


# -----------------------------------------------------------------
# Undeformed geometry view
# -----------------------------------------------------------------

def draw_undeformed(
    ax: Axes,
    model: "Model",
    highlight_node_id: Optional[int] = None,
    drag_pos: Optional[Tuple[int, float, float]] = None,
    grid_config: Optional[object] = None,
) -> None:
    """Undeformed structure: nodes, node numbers, elements, element
    numbers, and support markers. Safe to call with an empty model.

    Parameters
    ----------
    ax : Axes
        The matplotlib Axes to draw into (cleared on entry).
    model : Model
        The structural model to render.
    highlight_node_id : int | None
        When set, this node is drawn in the highlight colour (red-pink)
        to indicate it is the pending start-node for a two-click Add
        Element operation.  All other nodes use C_NODE.
    drag_pos : (int, float, float) | None
        When set to ``(node_id, x, y)``, that node is rendered live at
        ``(x, y)`` instead of its stored model position – used for the
        in-progress node-drag preview. The model itself is untouched;
        the real position is only committed on release (gui/canvas.py).
    grid_config : object | None
        Duck-typed config forwarded to draw_grid().  None = no grid.

    Future extension points
    -----------------------
    - selected_node_ids: set[int] for box/multi-selection highlights
    - load_vectors: bool to overlay nodal load arrows
    - These can be added as keyword arguments without changing callers.
    """
    if not model.nodes:
        draw_placeholder(ax, "No geometry yet – add nodes and elements.")
        return

    ax.clear()
    node_ids, coords = node_xy(model)

    # Live drag preview: substitute the dragged node's coordinates
    # without touching the model.
    if drag_pos is not None:
        drag_id, drag_x, drag_y = drag_pos
        if drag_id in node_ids:
            coords = coords.copy()
            coords[node_ids.index(drag_id)] = [drag_x, drag_y]

    pos = {nid: coords[i] for i, nid in enumerate(node_ids)}

    # Draw background snap grid (no-op unless config.visible is True)
    draw_grid(ax, grid_config)

    # ── Elements ──────────────────────────────────────────────────
    for elem in model.elements.values():
        if elem.node_i not in pos or elem.node_j not in pos:
            continue
        xi, yi = pos[elem.node_i]
        xj, yj = pos[elem.node_j]
        ax.plot(
            [xi, xj], [yi, yj],
            color=C_ELEMENT, linewidth=2.2,
            solid_capstyle="round", zorder=1,
        )
        mid_x = (xi + xj) / 2
        mid_y = (yi + yj) / 2
        ax.annotate(
            f"E{elem.id}", (mid_x, mid_y),
            color=C_ELEMENT, fontsize=8, ha="center", va="center",
            bbox=dict(
                boxstyle="round,pad=0.25",
                fc=C_AXES, ec=C_ELEMENT,
                alpha=0.85, linewidth=0.8,
            ),
            zorder=2,
        )

    # ── Nodes ─────────────────────────────────────────────────────
    for i, nid in enumerate(node_ids):
        is_highlighted = (nid == highlight_node_id)
        c = C_HIGHLIGHT if is_highlighted else C_NODE
        ax.scatter(
            [coords[i, 0]], [coords[i, 1]],
            s=80, c=c,
            edgecolors=C_HIGHLIGHT if is_highlighted else C_ELEMENT,
            linewidths=1.5,
            zorder=3,
        )
        ax.annotate(
            f"N{nid}", (coords[i, 0], coords[i, 1]),
            textcoords="offset points", xytext=(7, 7),
            fontsize=9, fontweight="bold", color=C_TEXT,
            zorder=4,
        )

    # ── Supports ──────────────────────────────────────────────────
    draw_supports(ax, model, node_ids, coords)

    # ── Loads (nodal force arrows) ────────────────────────────────
    _draw_load_arrows(ax, model, pos, coords)

    # ── Finish ────────────────────────────────────────────────────
    mode_hint = "" if highlight_node_id is None else "  [click end node]"
    style_axes(
        ax,
        f"Geometry{mode_hint}",
        xlabel="X (m)", ylabel="Y (m)", equal=True,
    )


def _draw_load_arrows(
    ax: Axes,
    model: "Model",
    pos: dict,
    coords: np.ndarray,
) -> None:
    """Draw nodal load arrows on the geometry view.

    Arrow length is scaled to 20 % of the model span so they are
    always visible regardless of absolute force magnitude.  The exact
    scaling is cosmetic – it does NOT affect any analysis output.

    Future: a ``show_loads`` flag can suppress this via a keyword arg
    on draw_undeformed() without touching any other code.
    """
    if not model.loads:
        return

    s = span(coords)
    arrow_scale = 0.20 * s        # 20 % of bounding-box span
    max_mag = max(
        (abs(ld.fx) ** 2 + abs(ld.fy) ** 2) ** 0.5
        for ld in model.loads.values()
    )
    if max_mag < 1e-12:
        return

    for nid, ld in model.loads.items():
        if nid not in pos:
            continue
        x, y = pos[nid]
        mag = (ld.fx ** 2 + ld.fy ** 2) ** 0.5
        nx = ld.fx / max_mag * arrow_scale
        ny = ld.fy / max_mag * arrow_scale

        ax.annotate(
            "",
            xy=(x + nx, y + ny),
            xytext=(x, y),
            arrowprops=dict(
                arrowstyle="-|>",
                color="#fbbf24",
                lw=1.8,
                mutation_scale=12,
            ),
            zorder=6,
        )
        # Force label at arrow tip
        label = f"{mag / 1e3:.2g} kN" if mag >= 1e3 else f"{mag:.2g} N"
        ax.annotate(
            label,
            (x + nx, y + ny),
            textcoords="offset points", xytext=(4, 4),
            fontsize=7, color="#fbbf24", zorder=7,
        )
