"""
=====================================================================
  gui/main_window.py

  TrussTry main application window.

  Layout
  ------
  ┌─────────────────────────────────────────────────────────────────┐
  │ Menu bar                                                        │
  │ Tool bar  [File] [Edit] [Mode: Select|Add Node|Add Element]     │
  │            [Analysis]                                           │
  ├──────────────┬──────────────────────────────┬──────────────────┤
  │              │                              │                  │
  │  Model Tree  │     Canvas (geometry /       │  Properties      │
  │  (left)      │     results tabs)            │  Panel (right)   │
  │              │                              │                  │
  ├──────────────┴──────────────────────────────┴──────────────────┤
  │  Results Panel (bottom tabbed: nodes / elements / reactions /   │
  │  summary)                                                       │
  └─────────────────────────────────────────────────────────────────┘

  Canvas editing modes
  --------------------
  Three mutually-exclusive toolbar actions (a QActionGroup) control
  what a left-click on the geometry canvas does:

    Select      – click a node to select it in the tree / properties
    Add Node    – click anywhere to place a new node
    Add Element – click two existing nodes to connect them

  The canvas emits intent signals; MainWindow translates them into
  CommandManager.execute() calls so every canvas action is undoable.

  Snap to Grid
  ------------
  A checkable "Snap to Grid" toolbar action toggles gui.snap.GridConfig
  .enabled and pushes it to the canvas via set_snap_config(). New-node
  placement and node dragging on the canvas both honour it. Snap
  enabled/spacing are persisted via QSettings across sessions. Default
  is OFF, since a wrong default spacing is worse than no snapping.

  Undo/Redo
  ---------
  All structural mutations are routed through CommandManager.execute()
  so they are automatically undoable.  Direct model.add_node() /
  remove_node() calls are only used for bulk operations (New, Open,
  Load Example) that clear the command stack anyway.

  Depends on: core.model, core.project_io, core.commands.*,
              analysis.truss2d, analysis.postprocessing,
              gui.canvas, gui.model_tree, gui.properties_panel,
              gui.results_panel
=====================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSettings, Qt, Signal, QObject, QSize
from PySide6.QtGui import (
    QAction, QActionGroup, QKeySequence,
    QIcon, QPixmap, QPainter, QColor,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.model import Model
from core.project_io import save_project, load_project
from core.commands import (
    CommandManager,
    AddNodeCommand,
    DeleteNodeCommand,
    MoveNodeCommand,
    AddElementCommand,
    DeleteElementCommand,
    AddSupportCommand,
    RemoveSupportCommand,
    AddLoadCommand,
    RemoveLoadCommand,
)
from analysis.truss2d import TrussSolver2D
from analysis.postprocessing import PostProcessor
from core.solver import SolverError

from gui.canvas import CanvasWidget
from gui.model_tree import ModelTreeWidget
from gui.properties_panel import PropertiesPanelWidget
from gui.results_panel import ResultsPanelWidget
from gui.snap import GridConfig


# ── Toolbar icon helper ───────────────────────────────────────────────

def _make_icon(svg_source: str, size: int = 20) -> QIcon:
    """Render an SVG string into a QIcon at *size* × *size* pixels.

    Uses QSvgRenderer so no external asset files are needed – every icon
    is defined inline as a compact SVG string below.  The helper is
    intentionally simple: one colour, one size, no state variants.

    Future extension: pass a ``color`` argument to tint the icon for
    disabled / checked states without additional SVG variants.
    """
    renderer = QSvgRenderer()
    renderer.load(svg_source.encode())
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


# Inline SVG icon sources – 20×20 viewBox, single-colour strokes only.
# Stroke colour is chosen to be visible on both light and dark toolbars.
_ICON_COLOR = "#c8c8d8"

_SVG_NEW = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
  <rect x="4" y="2" width="9" height="3" rx="0.5" fill="none" stroke="{_ICON_COLOR}" stroke-width="1.4"/>
  <rect x="4" y="2" width="12" height="16" rx="1" fill="none" stroke="{_ICON_COLOR}" stroke-width="1.4"/>
  <line x1="7" y1="8"  x2="13" y2="8"  stroke="{_ICON_COLOR}" stroke-width="1.2"/>
  <line x1="7" y1="11" x2="13" y2="11" stroke="{_ICON_COLOR}" stroke-width="1.2"/>
  <line x1="7" y1="14" x2="11" y2="14" stroke="{_ICON_COLOR}" stroke-width="1.2"/>
</svg>"""

_SVG_OPEN = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
  <path d="M3 7h5l2-2h7v10H3z" fill="none" stroke="{_ICON_COLOR}" stroke-width="1.4" stroke-linejoin="round"/>
</svg>"""

_SVG_SAVE = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
  <rect x="3" y="3" width="14" height="14" rx="1" fill="none" stroke="{_ICON_COLOR}" stroke-width="1.4"/>
  <rect x="7" y="3" width="6" height="5" fill="none" stroke="{_ICON_COLOR}" stroke-width="1.2"/>
  <rect x="5" y="11" width="10" height="5" rx="0.5" fill="none" stroke="{_ICON_COLOR}" stroke-width="1.2"/>
</svg>"""

_SVG_UNDO = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
  <path d="M5 10 Q5 5 10 5 h4" fill="none" stroke="{_ICON_COLOR}" stroke-width="1.5" stroke-linecap="round"/>
  <polyline points="5,6 5,10 9,10" fill="none" stroke="{_ICON_COLOR}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
</svg>"""

_SVG_REDO = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
  <path d="M15 10 Q15 5 10 5 h-4" fill="none" stroke="{_ICON_COLOR}" stroke-width="1.5" stroke-linecap="round"/>
  <polyline points="15,6 15,10 11,10" fill="none" stroke="{_ICON_COLOR}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
</svg>"""

_SVG_RUN = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
  <polygon points="6,4 16,10 6,16" fill="{_ICON_COLOR}" stroke="{_ICON_COLOR}" stroke-width="0.5" stroke-linejoin="round"/>
</svg>"""

_SVG_SELECT = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
  <polyline points="5,3 5,17 9,13 12,18 14,17 11,12 16,12" fill="none"
    stroke="{_ICON_COLOR}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
</svg>"""

_SVG_ADD_NODE = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
  <circle cx="10" cy="10" r="3.5" fill="none" stroke="{_ICON_COLOR}" stroke-width="1.5"/>
  <line x1="10" y1="2" x2="10" y2="6"  stroke="{_ICON_COLOR}" stroke-width="1.5" stroke-linecap="round"/>
  <line x1="10" y1="14" x2="10" y2="18" stroke="{_ICON_COLOR}" stroke-width="1.5" stroke-linecap="round"/>
  <line x1="2"  y1="10" x2="6"  y2="10" stroke="{_ICON_COLOR}" stroke-width="1.5" stroke-linecap="round"/>
  <line x1="14" y1="10" x2="18" y2="10" stroke="{_ICON_COLOR}" stroke-width="1.5" stroke-linecap="round"/>
</svg>"""

_SVG_ADD_ELEMENT = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
  <circle cx="4"  cy="16" r="2.5" fill="{_ICON_COLOR}"/>
  <circle cx="16" cy="4"  r="2.5" fill="{_ICON_COLOR}"/>
  <line x1="6" y1="14" x2="14" y2="6" stroke="{_ICON_COLOR}" stroke-width="1.8" stroke-linecap="round"/>
</svg>"""

_SVG_SNAP = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
  <line x1="4" y1="4" x2="16" y2="4"  stroke="{_ICON_COLOR}" stroke-width="0.8" stroke-dasharray="2 2"/>
  <line x1="4" y1="10" x2="16" y2="10" stroke="{_ICON_COLOR}" stroke-width="0.8" stroke-dasharray="2 2"/>
  <line x1="4" y1="16" x2="16" y2="16" stroke="{_ICON_COLOR}" stroke-width="0.8" stroke-dasharray="2 2"/>
  <line x1="4"  y1="4" x2="4"  y2="16" stroke="{_ICON_COLOR}" stroke-width="0.8" stroke-dasharray="2 2"/>
  <line x1="10" y1="4" x2="10" y2="16" stroke="{_ICON_COLOR}" stroke-width="0.8" stroke-dasharray="2 2"/>
  <line x1="16" y1="4" x2="16" y2="16" stroke="{_ICON_COLOR}" stroke-width="0.8" stroke-dasharray="2 2"/>
  <circle cx="10" cy="10" r="2.5" fill="{_ICON_COLOR}"/>
</svg>"""

# QSS applied to the toolbar so the checked mode button is visually distinct.
# Only targets the three mode actions by object name (set in _build_toolbar).
# This does not affect any other toolbar button or any dock/panel styling.
_TOOLBAR_QSS = """
QToolBar {
    spacing: 2px;
    padding: 2px 4px;
}
QToolButton {
    border-radius: 4px;
    padding: 3px 5px;
    margin: 1px;
}
QToolButton:hover {
    background: rgba(79, 158, 255, 0.18);
}
QToolButton:checked {
    background: rgba(79, 158, 255, 0.32);
    border: 1px solid rgba(79, 158, 255, 0.6);
}
QToolButton:pressed {
    background: rgba(79, 158, 255, 0.45);
}
"""


# ── thin Qt-side change-notification bridges ──────────────────────────
class _ModelBridge(QObject):
    """Bridges Model's plain-Python listener into a Qt Signal."""
    changed = Signal()


class _CmdBridge(QObject):
    """Bridges CommandManager's plain-Python listener into a Qt Signal."""
    stack_changed = Signal()


class MainWindow(QMainWindow):
    """Top-level application window."""

    WINDOW_TITLE = "TrussTry – 2D Truss FEA"
    FILE_FILTER  = "TrussTry Project (*.json);;All Files (*)"

    def __init__(self) -> None:
        super().__init__()

        self._model   = Model()
        self._cmd_mgr = CommandManager()
        self._results: Optional[dict] = None
        self._current_file: Optional[Path] = None
        self._modified = False
        self._snap_config = GridConfig(enabled=False)

        # Bridge model mutations → Qt signal
        self._model_bridge = _ModelBridge()
        self._model.add_listener(self._model_bridge.changed.emit)
        self._model_bridge.changed.connect(self._on_model_changed)

        # Bridge command-stack changes → Qt signal (for menu state)
        self._cmd_bridge = _CmdBridge()
        self._cmd_mgr.add_listener(self._cmd_bridge.stack_changed.emit)
        self._cmd_bridge.stack_changed.connect(self._refresh_undo_redo)

        self._build_ui()
        self._build_menus()
        self._build_toolbar()
        self._connect_signals()
        self._restore_geometry()
        self._refresh_title()
        self._refresh_undo_redo()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setMinimumSize(1100, 700)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)

        v_split = QSplitter(Qt.Vertical)
        root_layout.addWidget(v_split)

        h_split = QSplitter(Qt.Horizontal)
        v_split.addWidget(h_split)

        # LEFT – model tree
        self._tree = ModelTreeWidget(self._model)
        tree_dock = QDockWidget("Model Tree", self)
        tree_dock.setObjectName("ModelTreeDock")
        tree_dock.setWidget(self._tree)
        tree_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, tree_dock)

        # CENTRE – canvas
        self._canvas = CanvasWidget(self._model)
        h_split.addWidget(self._canvas)

        # RIGHT – properties
        self._props = PropertiesPanelWidget(self._model)
        props_dock = QDockWidget("Properties", self)
        props_dock.setObjectName("PropertiesDock")
        props_dock.setWidget(self._props)
        props_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, props_dock)

        # BOTTOM – results
        self._results_panel = ResultsPanelWidget()
        results_dock = QDockWidget("Results", self)
        results_dock.setObjectName("ResultsDock")
        results_dock.setWidget(self._results_panel)
        results_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        self.addDockWidget(Qt.BottomDockWidgetArea, results_dock)

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._lbl_nodes = QLabel("Nodes: 0")
        self._lbl_elems = QLabel("Elements: 0")
        self._lbl_hint  = QLabel("Ready")
        self._status.addWidget(self._lbl_nodes)
        self._status.addWidget(QLabel(" | "))
        self._status.addWidget(self._lbl_elems)
        self._status.addPermanentWidget(self._lbl_hint)

    def _build_menus(self) -> None:
        mb = self.menuBar()

        # ── File ──
        file_menu = mb.addMenu("&File")
        self._act_new    = QAction("&New",      self, shortcut=QKeySequence.New)
        self._act_open   = QAction("&Open…",    self, shortcut=QKeySequence.Open)
        self._act_save   = QAction("&Save",     self, shortcut=QKeySequence.Save)
        self._act_saveas = QAction("Save &As…", self, shortcut=QKeySequence("Ctrl+Shift+S"))
        self._act_quit   = QAction("&Quit",     self, shortcut=QKeySequence.Quit)
        file_menu.addActions([self._act_new, self._act_open,
                               self._act_save, self._act_saveas])
        file_menu.addSeparator()
        file_menu.addAction(self._act_quit)

        # ── Edit ──
        edit_menu = mb.addMenu("&Edit")
        self._act_undo    = QAction("&Undo", self, shortcut=QKeySequence.Undo)
        self._act_redo    = QAction("&Redo", self, shortcut=QKeySequence.Redo)
        self._act_clear   = QAction("Clear Model",        self)
        self._act_example = QAction("Load Example Truss", self)
        edit_menu.addAction(self._act_undo)
        edit_menu.addAction(self._act_redo)
        edit_menu.addSeparator()
        edit_menu.addActions([self._act_clear, self._act_example])

        # ── Analysis ──
        analysis_menu = mb.addMenu("&Analysis")
        self._act_run = QAction("&Run Analysis", self, shortcut=QKeySequence("F5"))
        self._act_run.setToolTip("Solve the current truss model (F5)")
        analysis_menu.addAction(self._act_run)

        # ── View ──
        view_menu = mb.addMenu("&View")
        self._act_view_geom   = QAction("Geometry",         self, checkable=True, checked=True)
        self._act_view_deform = QAction("Deformed Shape",   self, checkable=True)
        self._act_view_stress = QAction("Stress",           self, checkable=True)
        self._act_view_force  = QAction("Axial Forces",     self, checkable=True)
        self._act_view_matrix = QAction("Stiffness Matrix", self, checkable=True)
        for act in [self._act_view_geom, self._act_view_deform,
                    self._act_view_stress, self._act_view_force,
                    self._act_view_matrix]:
            view_menu.addAction(act)

        # ── Help ──
        help_menu = mb.addMenu("&Help")
        self._act_about = QAction("&About TrussTry", self)
        help_menu.addAction(self._act_about)

    def _build_toolbar(self) -> None:
        tb: QToolBar = self.addToolBar("Main")
        tb.setObjectName("MainToolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        tb.setStyleSheet(_TOOLBAR_QSS)

        # ── File / Edit ────────────────────────────────────────────────
        self._act_new.setIcon(_make_icon(_SVG_NEW))
        self._act_open.setIcon(_make_icon(_SVG_OPEN))
        self._act_save.setIcon(_make_icon(_SVG_SAVE))
        self._act_undo.setIcon(_make_icon(_SVG_UNDO))
        self._act_redo.setIcon(_make_icon(_SVG_REDO))

        tb.addActions([self._act_new, self._act_open, self._act_save])
        tb.addSeparator()
        tb.addActions([self._act_undo, self._act_redo])
        tb.addSeparator()
        tb.addActions([self._act_example, self._act_clear])
        tb.addSeparator()

        # ── Canvas editing mode group ──────────────────────────────────
        # Three mutually-exclusive checkable actions.  Triggering any
        # one calls set_mode() on the canvas so clicks on the geometry
        # tab do the right thing.
        self._mode_group = QActionGroup(self)
        self._mode_group.setExclusive(True)

        self._act_mode_select = QAction(
            _make_icon(_SVG_SELECT), "Select", self
        )
        self._act_mode_select.setCheckable(True)
        self._act_mode_select.setChecked(True)
        self._act_mode_select.setToolTip(
            "Select (S): click a node to select and view its properties."
        )

        self._act_mode_add_node = QAction(
            _make_icon(_SVG_ADD_NODE), "Add Node", self
        )
        self._act_mode_add_node.setCheckable(True)
        self._act_mode_add_node.setToolTip(
            "Add Node (N): click anywhere on the canvas to place a new node."
        )

        self._act_mode_add_element = QAction(
            _make_icon(_SVG_ADD_ELEMENT), "Add Element", self
        )
        self._act_mode_add_element.setCheckable(True)
        self._act_mode_add_element.setToolTip(
            "Add Element (E): click two existing nodes to connect them."
        )

        for act in (self._act_mode_select,
                    self._act_mode_add_node,
                    self._act_mode_add_element):
            self._mode_group.addAction(act)
            tb.addAction(act)

        tb.addSeparator()

        # ── Snap to Grid toggle ────────────────────────────────────────
        self._act_snap_toggle = QAction(
            _make_icon(_SVG_SNAP), "Snap", self
        )
        self._act_snap_toggle.setCheckable(True)
        self._act_snap_toggle.setChecked(self._snap_config.enabled)
        self._act_snap_toggle.setToolTip(
            "Snap to Grid: snap new and dragged nodes to the nearest grid point."
        )
        tb.addAction(self._act_snap_toggle)

        tb.addSeparator()

        # ── Run Analysis ───────────────────────────────────────────────
        self._act_run.setIcon(_make_icon(_SVG_RUN))
        tb.addAction(self._act_run)

    def _connect_signals(self) -> None:
        # File
        self._act_new.triggered.connect(self._new_project)
        self._act_open.triggered.connect(self._open_project)
        self._act_save.triggered.connect(self._save_project)
        self._act_saveas.triggered.connect(self._save_project_as)
        self._act_quit.triggered.connect(self.close)

        # Edit
        self._act_undo.triggered.connect(self._undo)
        self._act_redo.triggered.connect(self._redo)
        self._act_clear.triggered.connect(self._clear_model)
        self._act_example.triggered.connect(self._load_example)

        # Analysis
        self._act_run.triggered.connect(self._run_analysis)

        # View switching
        self._act_view_geom.triggered.connect(
            lambda: self._canvas.show_tab("geometry"))
        self._act_view_deform.triggered.connect(
            lambda: self._canvas.show_tab("deformation"))
        self._act_view_stress.triggered.connect(
            lambda: self._canvas.show_tab("stress"))
        self._act_view_force.triggered.connect(
            lambda: self._canvas.show_tab("force"))
        self._act_view_matrix.triggered.connect(
            lambda: self._canvas.show_tab("matrix"))

        # ── Canvas editing mode actions → canvas.set_mode() ────────────
        self._act_mode_select.triggered.connect(
            lambda: self._set_canvas_mode("select"))
        self._act_mode_add_node.triggered.connect(
            lambda: self._set_canvas_mode("add_node"))
        self._act_mode_add_element.triggered.connect(
            lambda: self._set_canvas_mode("add_element"))

        # ── Snap to Grid toggle ─────────────────────────────────────────
        self._act_snap_toggle.toggled.connect(self._on_snap_toggled)

        # ── Canvas intent signals → command dispatch ───────────────────
        self._canvas.node_requested.connect(self._on_canvas_node)
        self._canvas.element_requested.connect(self._on_canvas_element)
        self._canvas.node_selected.connect(self._on_canvas_select)
        self._canvas.node_move_requested.connect(self._on_canvas_move_node)

        # Properties panel → command dispatch
        self._props.node_add_requested.connect(self._on_node_add)
        self._props.element_add_requested.connect(self._on_element_add)
        self._props.support_add_requested.connect(self._on_support_add)
        self._props.load_add_requested.connect(self._on_load_add)
        self._props.delete_requested.connect(self._on_delete)

        # Tree → properties panel selection sync
        self._tree.item_selected.connect(self._props.set_selection)

        # Help
        self._act_about.triggered.connect(self._show_about)

    # ------------------------------------------------------------------
    # Canvas mode
    # ------------------------------------------------------------------

    def _set_canvas_mode(self, mode: str) -> None:
        """Switch the canvas editing mode and update the status bar."""
        self._canvas.set_mode(mode)
        labels = {
            "select":      "Select – click a node to select it",
            "add_node":    "Add Node – click the canvas to place a node",
            "add_element": "Add Element – click two nodes to connect them",
        }
        self._status.showMessage(labels.get(mode, mode), 5000)

    # ------------------------------------------------------------------
    # Snap to Grid
    # ------------------------------------------------------------------

    def _on_snap_toggled(self, enabled: bool) -> None:
        """Snap toggle action → mutate the shared GridConfig and push
        it to the canvas."""
        self._snap_config.enabled = enabled
        self._canvas.set_snap_config(self._snap_config)
        state = "ON" if enabled else "OFF"
        self._status.showMessage(f"Snap to Grid: {state}", 3000)

    # ------------------------------------------------------------------
    # Canvas intent signal handlers
    # ------------------------------------------------------------------

    def _on_canvas_node(self, x: float, y: float) -> None:
        """User clicked the canvas in Add Node mode."""
        cmd = AddNodeCommand(self._model, x, y)
        self._cmd_mgr.execute(cmd)
        self._status.showMessage(f"Added node at ({x:.3f}, {y:.3f}).", 3000)

    def _on_canvas_element(self, ni: int, nj: int) -> None:
        """User completed a two-node pick in Add Element mode."""
        cmd = AddElementCommand(self._model, ni, nj)
        self._cmd_mgr.execute(cmd)
        self._status.showMessage(f"Added element N{ni} → N{nj}.", 3000)

    def _on_canvas_select(self, nid: int) -> None:
        """User clicked a node in Select mode – sync tree + properties."""
        # The tree drives the properties panel via its item_selected signal,
        # but there is no public "select by id" API on ModelTreeWidget.
        # Drive properties directly, which is consistent with how the tree
        # does it (tree.item_selected → props.set_selection).
        self._props.set_selection("node", nid)
        self._status.showMessage(f"Selected N{nid}.", 2000)

    def _on_canvas_move_node(self, nid: int, x: float, y: float) -> None:
        """User finished dragging a node on the canvas in Select mode.
        MoveNodeCommand was imported but previously never invoked –
        the drag workflow is its first caller."""
        cmd = MoveNodeCommand(self._model, nid, x, y)
        self._cmd_mgr.execute(cmd)
        self._status.showMessage(f"Moved N{nid} to ({x:.3f}, {y:.3f}).", 3000)

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------

    def _undo(self) -> None:
        desc = self._cmd_mgr.undo()
        if desc:
            self._status.showMessage(f"Undid: {desc}", 3000)

    def _redo(self) -> None:
        desc = self._cmd_mgr.redo()
        if desc:
            self._status.showMessage(f"Redid: {desc}", 3000)

    def _refresh_undo_redo(self) -> None:
        """Keep Undo/Redo actions enabled/disabled and labelled correctly."""
        mgr = self._cmd_mgr
        self._act_undo.setEnabled(mgr.can_undo)
        self._act_redo.setEnabled(mgr.can_redo)
        self._act_undo.setText(
            f"&Undo {mgr.undo_description}" if mgr.can_undo else "&Undo"
        )
        self._act_redo.setText(
            f"&Redo {mgr.redo_description}" if mgr.can_redo else "&Redo"
        )

    # ------------------------------------------------------------------
    # Model-change handler
    # ------------------------------------------------------------------

    def _on_model_changed(self) -> None:
        """Called (via the bridge) after every model mutation."""
        self._modified = True
        self._results  = None   # stale results after any geometry/BC/load change
        self._refresh_title()
        self._refresh_status()
        self._tree.refresh()
        self._canvas.refresh()
        self._results_panel.clear()

    def _refresh_title(self) -> None:
        name = self._current_file.name if self._current_file else "Untitled"
        mod  = " *" if self._modified else ""
        self.setWindowTitle(f"{name}{mod} – {self.WINDOW_TITLE}")

    def _refresh_status(self) -> None:
        m = self._model
        self._lbl_nodes.setText(f"Nodes: {len(m.nodes)}")
        self._lbl_elems.setText(f"Elements: {len(m.elements)}")

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def _maybe_save(self) -> bool:
        """Prompt to save if modified.  Returns False when user cancels."""
        if not self._modified:
            return True
        reply = QMessageBox.question(
            self, "Unsaved changes",
            "The current project has unsaved changes. Save before continuing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if reply == QMessageBox.Save:
            return self._save_project()
        return reply != QMessageBox.Cancel

    def _new_project(self) -> None:
        if not self._maybe_save():
            return
        self._model.clear()
        self._cmd_mgr.clear()
        self._current_file = None
        self._modified     = False
        self._results      = None
        self._results_panel.clear()
        self._refresh_title()
        self._refresh_undo_redo()
        self._status.showMessage("New project created.", 3000)

    def _open_project(self) -> None:
        if not self._maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", self.FILE_FILTER)
        if not path:
            return
        try:
            new_model = load_project(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return

        # Rewire the model bridge to the new model object
        self._model.remove_listener(self._model_bridge.changed.emit)
        self._model = new_model
        self._model.add_listener(self._model_bridge.changed.emit)

        self._canvas.set_model(self._model)
        self._tree.set_model(self._model)
        self._props.set_model(self._model)

        self._cmd_mgr.clear()          # history from old project is invalid
        self._current_file = Path(path)
        self._modified     = False
        self._results      = None

        self._refresh_title()
        self._refresh_status()
        self._refresh_undo_redo()
        self._tree.refresh()
        self._canvas.refresh()
        self._results_panel.clear()
        self._status.showMessage(f"Opened: {path}", 4000)

    def _save_project(self) -> bool:
        if self._current_file is None:
            return self._save_project_as()
        try:
            save_project(self._model, self._current_file)
            self._modified = False
            self._refresh_title()
            self._status.showMessage(f"Saved: {self._current_file}", 3000)
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return False

    def _save_project_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", "", self.FILE_FILTER)
        if not path:
            return False
        self._current_file = Path(path)
        return self._save_project()

    # ------------------------------------------------------------------
    # Edit actions
    # ------------------------------------------------------------------

    def _clear_model(self) -> None:
        if QMessageBox.question(
            self, "Clear model",
            "Remove all nodes, elements, and loads?",
            QMessageBox.Yes | QMessageBox.No,
        ) == QMessageBox.Yes:
            self._model.clear()
            self._cmd_mgr.clear()
            self._refresh_undo_redo()

    def _load_example(self) -> None:
        if self._model.nodes and not self._maybe_save():
            return
        self._model.load_example_truss()
        self._cmd_mgr.clear()          # example is the new baseline
        self._refresh_undo_redo()
        self._status.showMessage(
            "Example truss loaded. Press F5 to run analysis.", 5000)

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _run_analysis(self) -> None:
        m = self._model
        if not m.nodes or not m.elements:
            QMessageBox.warning(self, "Cannot solve",
                                "Add nodes and elements first.")
            return
        if not m.boundary_conditions:
            QMessageBox.warning(self, "Cannot solve",
                                "No boundary conditions defined. "
                                "The structure would be a mechanism.")
            return

        self._status.showMessage("Running analysis…")
        QApplication.processEvents()

        try:
            solver        = TrussSolver2D.from_model(m)
            self._results = solver.solve()
        except SolverError as exc:
            QMessageBox.critical(self, "Solver error", str(exc))
            self._status.showMessage("Analysis failed.", 4000)
            return
        except Exception as exc:
            QMessageBox.critical(self, "Unexpected error", str(exc))
            self._status.showMessage("Analysis failed.", 4000)
            return

        pp = PostProcessor(m, self._results)
        self._results_panel.display(m, self._results, pp)
        self._canvas.set_results(self._results)
        self._canvas.show_tab("deformation")
        self._status.showMessage("Analysis complete.", 5000)

    # ------------------------------------------------------------------
    # Properties-panel callbacks  →  command dispatch
    # ------------------------------------------------------------------

    def _on_node_add(self, x: float, y: float) -> None:
        cmd = AddNodeCommand(self._model, x, y)
        self._cmd_mgr.execute(cmd)
        self._status.showMessage(f"{cmd.description} added.", 3000)

    def _on_element_add(self, ni: int, nj: int) -> None:
        cmd = AddElementCommand(self._model, ni, nj)
        self._cmd_mgr.execute(cmd)
        self._status.showMessage(f"{cmd.description} added.", 3000)

    def _on_support_add(self, node_id: int, fix_x: bool, fix_y: bool) -> None:
        cmd = AddSupportCommand(self._model, node_id, fix_x, fix_y)
        self._cmd_mgr.execute(cmd)
        self._status.showMessage(f"Support set on N{node_id}.", 3000)

    def _on_load_add(self, node_id: int, fx: float, fy: float) -> None:
        cmd = AddLoadCommand(self._model, node_id, fx, fy)
        self._cmd_mgr.execute(cmd)
        self._status.showMessage(
            f"Load set on N{node_id}: Fx={fx} N, Fy={fy} N.", 3000)

    def _on_delete(self, item_type: str, item_id: int) -> None:
        if item_type == "node":
            cmd = DeleteNodeCommand(self._model, item_id)
            self._cmd_mgr.execute(cmd)
            self._status.showMessage(f"{cmd.description} deleted.", 3000)
        elif item_type == "element":
            cmd = DeleteElementCommand(self._model, item_id)
            self._cmd_mgr.execute(cmd)
            self._status.showMessage(f"{cmd.description} deleted.", 3000)
        elif item_type == "support":
            cmd = RemoveSupportCommand(self._model, item_id)
            self._cmd_mgr.execute(cmd)
            self._status.showMessage(f"Support on N{item_id} removed.", 3000)
        elif item_type == "load":
            cmd = RemoveLoadCommand(self._model, item_id)
            self._cmd_mgr.execute(cmd)
            self._status.showMessage(f"Load on N{item_id} removed.", 3000)

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "About TrussTry",
            "<h3>TrussTry</h3>"
            "<p>A 2D truss finite-element analysis desktop application.</p>"
            "<p>Built with Python, PySide6, NumPy and Matplotlib.</p>"
            "<p><b>Toolbar modes</b>: Select · Add Node · Add Element</p>"
            "<p><b>Snap to Grid</b>: toggle in the toolbar to snap new "
            "and dragged nodes to the nearest grid point.</p>"
            "<p><b>Ctrl+Z</b> Undo &nbsp; <b>Ctrl+Y</b> Redo &nbsp; "
            "<b>F5</b> Run Analysis</p>"
        )

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def _restore_geometry(self) -> None:
        settings = QSettings("TrussTry", "TrussTry")
        geom  = settings.value("geometry")
        state = settings.value("windowState")
        if geom:
            self.restoreGeometry(geom)
        else:
            self.resize(1280, 800)
        if state:
            self.restoreState(state)

        # Snap to Grid state
        snap_enabled = settings.value("snap_enabled", False, type=bool)
        snap_spacing = settings.value("snap_spacing", self._snap_config.spacing, type=float)
        self._snap_config.enabled = snap_enabled
        self._snap_config.spacing = snap_spacing
        self._act_snap_toggle.setChecked(snap_enabled)   # triggers _on_snap_toggled
        self._canvas.set_snap_config(self._snap_config)

    def closeEvent(self, event) -> None:
        if not self._maybe_save():
            event.ignore()
            return
        settings = QSettings("TrussTry", "TrussTry")
        settings.setValue("geometry",    self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("snap_enabled", self._snap_config.enabled)
        settings.setValue("snap_spacing", self._snap_config.spacing)
        super().closeEvent(event)
