"""
=====================================================================
  gui/results_panel.py

  Bottom-panel tabbed widget that displays analysis results in four
  sub-tabs:

    1. Summary   – AnalysisSummary headline figures + equilibrium check
    2. Nodes     – per-node displacement table (ux, uy, |u|)
    3. Elements  – per-element stress / strain / force / state table
    4. Reactions – per-support reaction (Rx, Ry, resultant)

  Data comes from PostProcessor and is rendered in QTableWidgets.
  This widget has NO matplotlib dependency – it is purely Qt.

  Depends on: PySide6, analysis.postprocessing, analysis.reactions,
              core.model (type hints only)
=====================================================================
"""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from analysis.postprocessing import PostProcessor
from analysis.reactions import reaction_summary

if TYPE_CHECKING:
    from core.model import Model


def _ro(text: str) -> QTableWidgetItem:
    """Create a read-only, non-editable table cell."""
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    return item


def _fill_table(table: QTableWidget, headers: List[str], rows: List[List[str]]) -> None:
    table.clear()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            table.setItem(r, c, _ro(val))
    table.resizeColumnsToContents()
    table.horizontalHeader().setStretchLastSection(True)


class ResultsPanelWidget(QWidget):
    """
    Tabbed results viewer placed in a bottom dock.

    Usage (called by MainWindow after a successful solve)
    ──────────────────────────────────────────────────────
        pp = PostProcessor(model, results)
        panel.display(model, results, pp)

    Call panel.clear() to reset all tabs to their empty state.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumHeight(160)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        # --- Summary tab ---
        self._summary_widget = QWidget()
        sv = QVBoxLayout(self._summary_widget)
        self._summary_label = QLabel("Run analysis to see results.")
        self._summary_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._summary_label.setWordWrap(True)
        self._summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        sv.addWidget(self._summary_label)
        sv.addStretch()
        self._tabs.addTab(self._summary_widget, "Summary")

        # --- Nodes tab ---
        self._node_table = QTableWidget()
        self._node_table.setAlternatingRowColors(True)
        self._node_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._node_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabs.addTab(self._node_table, "Nodes")

        # --- Elements tab ---
        self._elem_table = QTableWidget()
        self._elem_table.setAlternatingRowColors(True)
        self._elem_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._elem_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabs.addTab(self._elem_table, "Elements")

        # --- Reactions tab ---
        self._react_table = QTableWidget()
        self._react_table.setAlternatingRowColors(True)
        self._react_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._react_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabs.addTab(self._react_table, "Reactions")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._tabs)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def display(self, model: "Model", results: dict, pp: PostProcessor) -> None:
        """Populate all tabs from a completed analysis."""
        self._fill_summary(model, results, pp)
        self._fill_nodes(pp)
        self._fill_elements(pp)
        self._fill_reactions(model, results)

    def clear(self) -> None:
        """Reset all tabs to their empty / placeholder state."""
        self._summary_label.setText("Run analysis to see results.")
        for tbl in (self._node_table, self._elem_table, self._react_table):
            tbl.clear()
            tbl.setRowCount(0)
            tbl.setColumnCount(0)

    # ------------------------------------------------------------------
    # Internal fill helpers
    # ------------------------------------------------------------------

    def _fill_summary(self, model: "Model", results: dict, pp: PostProcessor) -> None:
        s = pp.summary()
        ok, rfx, rfy = pp.equilibrium_check()
        eq_str = "✓ Equilibrium OK" if ok else f"✗ Residual: Fx={rfx:.3e} N, Fy={rfy:.3e} N"

        text = (
            f"<b>Nodes:</b> {s.num_nodes}   "
            f"<b>Elements:</b> {s.num_elements}<br><br>"
            f"<b>Max displacement:</b> {s.max_displacement:.6e} m<br>"
            f"<b>Max axial stress:</b> {s.max_stress / 1e6:.4f} MPa<br>"
            f"<b>Max axial strain:</b> {s.max_strain:.4e}<br>"
            f"<b>Max axial force:</b> {s.max_axial_force:.2f} N<br>"
            f"<b>Total reaction force:</b> {s.total_reaction_force:.2f} N<br><br>"
            f"<b>Global equilibrium:</b> {eq_str}"
        )
        self._summary_label.setText(text)

    def _fill_nodes(self, pp: PostProcessor) -> None:
        headers = ["Node", "X (m)", "Y (m)", "Ux (m)", "Uy (m)", "|u| (m)"]
        rows = []
        for r in pp.node_table():
            rows.append([
                f"N{r['node_id']}",
                f"{r['x']:.4f}",
                f"{r['y']:.4f}",
                f"{r['ux']:.6e}",
                f"{r['uy']:.6e}",
                f"{r['magnitude']:.6e}",
            ])
        _fill_table(self._node_table, headers, rows)

    def _fill_elements(self, pp: PostProcessor) -> None:
        headers = ["Elem", "Ni", "Nj", "Stress (MPa)", "Strain", "Force (N)", "State"]
        rows = []
        for r in pp.element_table():
            rows.append([
                f"E{r['element_id']}",
                f"N{r['node_i']}",
                f"N{r['node_j']}",
                f"{r['stress'] / 1e6:.4f}",
                f"{r['strain']:.6e}",
                f"{r['axial_force']:.2f}",
                r["state"],
            ])
        _fill_table(self._elem_table, headers, rows)

    def _fill_reactions(self, model: "Model", results: dict) -> None:
        reactions = reaction_summary(results, model)
        headers = ["Node", "Rx (N)", "Ry (N)", "|R| (N)", "θ (°)"]
        rows = []
        for rxn in reactions:
            rows.append([
                f"N{rxn.node_id}",
                f"{rxn.rx:+.2f}",
                f"{rxn.ry:+.2f}",
                f"{rxn.resultant:.2f}",
                f"{rxn.angle_deg:.1f}",
            ])
        _fill_table(self._react_table, headers, rows)
