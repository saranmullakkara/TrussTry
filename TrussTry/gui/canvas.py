"""
=====================================================================
  gui/canvas.py

  Central canvas widget: a QTabWidget with one FigureCanvasQTAgg per
  visualization type.  Each tab hands its matplotlib Axes to the
  corresponding stateless drawing function in visualization/.

  Tab map
  -------
  "geometry"    → visualization.geometry_view.draw_undeformed
  "deformation" → visualization.deformation_view.draw_deformed
  "stress"      → visualization.stress_view.draw_stress_contours
  "force"       → visualization.force_view.draw_axial_forces
  "matrix"      → visualization.matrix_view.draw_global_stiffness_matrix

  Interactive editing (geometry tab only)
  ----------------------------------------
  The geometry tab supports three modes set via set_mode():

    "select"      – click near a node to emit node_selected(nid)
    "add_node"    – click empty canvas to emit node_requested(x, y)
    "add_element" – click two existing nodes in sequence to emit
                    element_requested(ni, nj)

  Signals emitted (connected in MainWindow):
    node_requested(x: float, y: float)
    element_requested(ni: int, nj: int)
    node_selected(nid: int)
    node_move_requested(nid: int, x: float, y: float)

  Only the geometry tab registers matplotlib mouse handlers.
  All other tabs remain purely passive renderers.

  Grid snapping
  -------------
  New-node placement (add_node mode) and node dragging (select mode)
  both run raw click/drag coordinates through gui.snap.snap_point()
  before they are used, using a shared GridConfig set via
  set_snap_config(). This is the single place snapping is applied on
  the canvas -- see gui/snap.py for the snap engine itself.

  Node dragging (select mode)
  ----------------------------
  Clicking and holding on a node in select mode begins a drag.
  motion_notify_event drives a live (snap-aware) redraw as the mouse
  moves; button_release_event commits the move as a single
  MoveNodeCommand via node_move_requested, so a whole drag is one
  undo step.

  This file is the ONLY place in the codebase that imports PySide6
  *and* matplotlib together. visualization/ remains Qt-free.

  Depends on: PySide6, matplotlib, core.model (type hints),
              visualization.*
=====================================================================
"""

from __future__ import annotations

from typing import Optional, Tuple, TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from visualization.geometry_view import draw_undeformed, node_xy, span
from visualization.deformation_view import draw_deformed
from visualization.stress_view import draw_stress_contours
from visualization.force_view import draw_axial_forces
from visualization.matrix_view import draw_global_stiffness_matrix

from gui.snap import GridConfig, snap_point

if TYPE_CHECKING:
    from core.model import Model


class _PlotTab(QWidget):
    """A single tab: one Figure → one Axes → one drawing function."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.fig = Figure(facecolor="#0f0f17", tight_layout=True)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasQTAgg(self.fig)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)

    def redraw(self) -> None:
        self.canvas.draw_idle()


class CanvasWidget(QTabWidget):
    """
    Tabbed matplotlib canvas.

    Public API used by MainWindow
    ─────────────────────────────
    set_model(model)       – swap the model reference (called on Open)
    set_results(results)   – store the latest solver output
    refresh()              – repaint the currently visible tab
    show_tab(name)         – switch to a named tab and repaint it
    set_mode(mode)         – set canvas editing mode (geometry tab only)
    set_snap_config(cfg)   – set the shared GridConfig used for snapping

    Interactive signals (geometry tab)
    ────────────────────────────────────
    node_requested(x, y)      – user clicked empty canvas in add_node mode
    element_requested(ni, nj) – user completed two-node pick in add_element mode
    node_selected(nid)        – user clicked an existing node in select mode
    node_move_requested(nid, x, y) – user finished dragging a node in select mode
    """

    # Editing signals – connected by MainWindow to command dispatch
    node_requested   = Signal(float, float)
    element_requested = Signal(int, int)
    node_selected    = Signal(int)
    node_move_requested = Signal(int, float, float)

    _TAB_KEYS = ["geometry", "deformation", "stress", "force", "matrix"]
    _TAB_LABELS = {
        "geometry":    "Geometry",
        "deformation": "Deformed Shape",
        "stress":      "Stress",
        "force":       "Axial Forces",
        "matrix":      "K Matrix",
    }

    # Fraction of bounding-box span used as the node hit-test radius.
    # 0.08 feels responsive without being overly greedy.
    _PICK_FRACTION = 0.08
    # Absolute fallback when the model has only one node (span → 1.0)
    _PICK_MIN = 0.25

    def __init__(self, model: "Model", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model = model
        self._results: Optional[dict] = None
        self._tabs: dict[str, _PlotTab] = {}

        # Editing state
        self._mode: str = "select"
        self._pending_start: Optional[int] = None   # for add_element two-click

        # Snapping – shared config, applied via gui.snap.snap_point()
        self._snap_config: GridConfig = GridConfig(enabled=False)

        # Drag state (select mode) – None when no drag is in progress
        self._dragging_node_id: Optional[int] = None
        self._drag_origin: Optional[Tuple[float, float]] = None
        self._drag_pos: Optional[Tuple[float, float]] = None

        for key in self._TAB_KEYS:
            tab = _PlotTab()
            self._tabs[key] = tab
            self.addTab(tab, self._TAB_LABELS[key])

        # Wire the geometry tab's matplotlib canvas to our mouse handlers
        geom_canvas = self._tabs["geometry"].canvas
        geom_canvas.mpl_connect("button_press_event", self._on_canvas_click)
        geom_canvas.mpl_connect("motion_notify_event", self._on_canvas_motion)
        geom_canvas.mpl_connect("button_release_event", self._on_canvas_release)

        self.currentChanged.connect(self._on_tab_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_model(self, model: "Model") -> None:
        self._model = model
        self._pending_start = None
        self._clear_drag_state()

    def set_results(self, results: Optional[dict]) -> None:
        self._results = results

    def set_mode(self, mode: str) -> None:
        """Switch editing mode. Clears any pending element start node
        and any in-progress drag."""
        self._mode = mode
        self._pending_start = None
        self._clear_drag_state()
        # Redraw the geometry tab immediately so the title/cursor updates
        self._draw_tab("geometry")
        self._tabs["geometry"].redraw()

    def get_mode(self) -> str:
        return self._mode

    def set_snap_config(self, config: GridConfig) -> None:
        """Install the shared GridConfig used to snap new-node
        placement and node dragging. Called by MainWindow whenever
        the snap toggle or spacing changes."""
        self._snap_config = config

    def refresh(self) -> None:
        """Repaint whichever tab is currently visible."""
        key = self._TAB_KEYS[self.currentIndex()]
        self._draw_tab(key)

    def show_tab(self, name: str) -> None:
        """Switch to the named tab and repaint it."""
        if name not in self._tabs:
            return
        idx = self._TAB_KEYS.index(name)
        self.setCurrentIndex(idx)
        self._draw_tab(name)

    # ------------------------------------------------------------------
    # Internal – tab rendering
    # ------------------------------------------------------------------

    def _on_tab_changed(self, index: int) -> None:
        key = self._TAB_KEYS[index]
        # Switching away from geometry clears the pending element start
        if key != "geometry":
            self._pending_start = None
        self._draw_tab(key)

    def _draw_tab(self, key: str) -> None:
        tab = self._tabs[key]
        m = self._model
        r = self._results

        if key == "geometry":
            draw_undeformed(
                tab.ax, m,
                highlight_node_id=self._pending_start,
                drag_pos=self._current_drag_preview(),
                grid_config=self._snap_config,
            )
        elif key == "deformation":
            draw_deformed(tab.ax, m, r or {})
        elif key == "stress":
            draw_stress_contours(tab.ax, m, r or {})
        elif key == "force":
            draw_axial_forces(tab.ax, m, r or {})
        elif key == "matrix":
            draw_global_stiffness_matrix(tab.ax, m, r or {})

        tab.redraw()

    # ------------------------------------------------------------------
    # Internal – geometry tab mouse interaction
    # ------------------------------------------------------------------

    def _pick_radius(self) -> float:
        """Adaptive hit-test radius: a fraction of the bounding-box
        span so it works for both metre-scale and kilometre-scale
        models, with a minimum to handle the single-node edge case."""
        if not self._model.nodes:
            return self._PICK_MIN
        _, coords = node_xy(self._model)
        s = span(coords)
        return max(s * self._PICK_FRACTION, self._PICK_MIN)

    def _nearest_node(self, x: float, y: float) -> Optional[int]:
        """Return the id of the node closest to (x, y) within the
        pick radius, or None if no node is close enough."""
        radius = self._pick_radius()
        best_id, best_dist = None, radius
        for node in self._model.nodes.values():
            dist = ((node.x - x) ** 2 + (node.y - y) ** 2) ** 0.5
            if dist < best_dist:
                best_id, best_dist = node.id, dist
        return best_id

    def _clear_drag_state(self) -> None:
        self._dragging_node_id = None
        self._drag_origin = None
        self._drag_pos = None

    def _current_drag_preview(self) -> Optional[Tuple[int, float, float]]:
        """(node_id, x, y) for the in-progress drag, or None – used by
        draw_undeformed() to render the live preview."""
        if self._dragging_node_id is None or self._drag_pos is None:
            return None
        return (self._dragging_node_id, self._drag_pos[0], self._drag_pos[1])

    def _on_canvas_click(self, event) -> None:
        """Matplotlib button_press_event handler – only active on the
        geometry tab.  Routes the click to the appropriate mode handler
        and triggers a redraw so visual feedback is immediate."""
        # Ignore clicks outside axes or on other tabs
        geom_tab = self._tabs["geometry"]
        if event.inaxes != geom_tab.ax or event.xdata is None:
            return
        # Only respond on the geometry tab
        if self._TAB_KEYS[self.currentIndex()] != "geometry":
            return
        # Only left-button clicks
        if event.button != 1:
            return

        x, y = event.xdata, event.ydata

        if self._mode == "add_node":
            self._handle_add_node(x, y)

        elif self._mode == "add_element":
            self._handle_add_element(x, y)

        elif self._mode == "select":
            self._handle_select(x, y)

    def _handle_add_node(self, x: float, y: float) -> None:
        """Place a new node at the clicked coordinates, snapped to the
        grid when snap-to-grid is enabled (see gui/snap.py)."""
        sx, sy = snap_point(x, y, self._snap_config)
        self.node_requested.emit(sx, sy)
        # Redraw is triggered by the model-changed signal in MainWindow
        # after the command executes, so no explicit redraw needed here.

    def _handle_add_element(self, x: float, y: float) -> None:
        """Two-click workflow: first click picks the start node (shown
        highlighted in red), second click picks the end node and emits
        element_requested.  Clicking the same node twice cancels."""
        picked = self._nearest_node(x, y)
        if picked is None:
            # No node nearby – redraw to show the current state
            self._draw_tab("geometry")
            return

        if self._pending_start is None:
            # First click – store the start node and redraw to highlight it
            self._pending_start = picked
            self._draw_tab("geometry")
        else:
            start = self._pending_start
            self._pending_start = None

            if picked == start:
                # Same node clicked twice – cancel silently and redraw
                self._draw_tab("geometry")
                return

            self.element_requested.emit(start, picked)
            # Model change will trigger a full refresh via MainWindow

    def _handle_select(self, x: float, y: float) -> None:
        """Select the nearest node, emit node_selected, and arm drag
        state so a subsequent mouse-move begins dragging it."""
        picked = self._nearest_node(x, y)
        if picked is not None:
            origin = snap_point(x, y, self._snap_config)
            self._dragging_node_id = picked
            self._drag_origin = origin
            self._drag_pos = origin
            self.node_selected.emit(picked)

    def _on_canvas_motion(self, event) -> None:
        """Matplotlib motion_notify_event handler. Only does anything
        while a drag is in progress (select mode, left button held on
        a node). Snaps the live position and redraws for preview
        only – no command is emitted until the mouse is released, so
        the undo stack stays clean for the whole drag."""
        if self._dragging_node_id is None:
            return
        geom_tab = self._tabs["geometry"]
        if event.inaxes != geom_tab.ax or event.xdata is None:
            return
        if self._TAB_KEYS[self.currentIndex()] != "geometry":
            return

        sx, sy = snap_point(event.xdata, event.ydata, self._snap_config)
        self._drag_pos = (sx, sy)
        self._draw_tab("geometry")

    def _on_canvas_release(self, event) -> None:
        """Matplotlib button_release_event handler. Commits an
        in-progress drag as a single node_move_requested emission
        (→ one MoveNodeCommand, one undo step), provided the node
        actually moved."""
        if self._dragging_node_id is None:
            return

        nid = self._dragging_node_id
        origin = self._drag_origin
        pos = self._drag_pos
        self._clear_drag_state()

        if pos is not None and origin is not None and pos != origin:
            self.node_move_requested.emit(nid, pos[0], pos[1])
        else:
            # No net movement (a plain click) – just redraw to clear
            # the live preview state.
            self._draw_tab("geometry")
