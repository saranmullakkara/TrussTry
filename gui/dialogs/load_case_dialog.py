"""
=====================================================================
  gui/dialogs/load_case_dialog.py

  Dialog for managing named load cases (LoadCase / LoadCaseSet).
  Lets the user define multiple named cases, run them all at once
  via LoadCaseSet.run_all(), and inspect per-case results.

  Depends on: PySide6, analysis.load_cases, core.model
=====================================================================
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QSpinBox, QSplitter,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from analysis.load_cases import LoadCase, LoadCaseSet

if TYPE_CHECKING:
    from core.model import Model


class LoadCaseDialog(QDialog):
    """
    A dialog to:
    1. View the current model's stored loads as a base case.
    2. Add / remove named LoadCases.
    3. Run all cases and display a compact text summary.
    """

    def __init__(self, model: "Model", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model = model
        self._cases: List[LoadCase] = []
        self._last_results: List[dict] = []

        self.setWindowTitle("Load Case Manager")
        self.resize(640, 500)

        splitter = QSplitter(Qt.Horizontal)

        # --- Left: case list + add/remove ---
        left = QWidget()
        lv = QVBoxLayout(left)

        self._case_list = QListWidget()
        self._case_list.currentRowChanged.connect(self._on_case_selected)

        btn_add = QPushButton("Add Case")
        btn_add.clicked.connect(self._add_case)
        btn_rem = QPushButton("Remove Selected")
        btn_rem.clicked.connect(self._remove_case)

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_rem)

        lv.addWidget(QLabel("Named Load Cases:"))
        lv.addWidget(self._case_list)
        lv.addLayout(btn_row)
        splitter.addWidget(left)

        # --- Right: case editor ---
        right = QWidget()
        rv = QVBoxLayout(right)

        grp_case = QGroupBox("Case Definition")
        cf = QFormLayout(grp_case)
        self._case_name = QLineEdit("Case 1")
        self._case_node = QSpinBox()
        self._case_node.setRange(1, 99999)
        self._case_fx = QDoubleSpinBox()
        self._case_fx.setRange(-1e12, 1e12)
        self._case_fx.setDecimals(2)
        self._case_fx.setSuffix(" N")
        self._case_fy = QDoubleSpinBox()
        self._case_fy.setRange(-1e12, 1e12)
        self._case_fy.setDecimals(2)
        self._case_fy.setSuffix(" N")
        btn_apply = QPushButton("Save / Update Case")
        btn_apply.clicked.connect(self._save_current_case)

        cf.addRow("Case name:", self._case_name)
        cf.addRow("Node:", self._case_node)
        cf.addRow("Fx:", self._case_fx)
        cf.addRow("Fy:", self._case_fy)
        cf.addRow(btn_apply)

        self._results_view = QTextEdit()
        self._results_view.setReadOnly(True)
        self._results_view.setPlaceholderText("Click 'Run All Cases' to see results here…")

        rv.addWidget(grp_case)
        rv.addWidget(QLabel("Results:"))
        rv.addWidget(self._results_view)
        splitter.addWidget(right)

        splitter.setSizes([220, 420])

        btn_box = QDialogButtonBox()
        self._btn_run = btn_box.addButton("Run All Cases", QDialogButtonBox.ActionRole)
        btn_box.addButton(QDialogButtonBox.Close)
        self._btn_run.clicked.connect(self._run_all)
        btn_box.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(splitter)
        root.addWidget(btn_box)

    # ------------------------------------------------------------------

    def _add_case(self) -> None:
        case = LoadCase(name=f"Case {len(self._cases) + 1}")
        self._cases.append(case)
        self._case_list.addItem(case.name)
        self._case_list.setCurrentRow(len(self._cases) - 1)

    def _remove_case(self) -> None:
        row = self._case_list.currentRow()
        if row < 0:
            return
        self._cases.pop(row)
        self._case_list.takeItem(row)

    def _on_case_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._cases):
            return
        case = self._cases[row]
        self._case_name.setText(case.name)
        # Show first load if any
        if case.loads:
            nid, (fx, fy) = next(iter(case.loads.items()))
            self._case_node.setValue(nid)
            self._case_fx.setValue(fx)
            self._case_fy.setValue(fy)

    def _save_current_case(self) -> None:
        row = self._case_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "No case selected", "Add a case first.")
            return
        case = self._cases[row]
        case.name = self._case_name.text() or case.name
        case.add_load(self._case_node.value(),
                      self._case_fx.value(), self._case_fy.value())
        self._case_list.currentItem().setText(case.name)

    def _run_all(self) -> None:
        if not self._cases:
            QMessageBox.information(self, "No cases", "Add at least one load case.")
            return
        lcs = LoadCaseSet(self._model)
        for c in self._cases:
            lcs.add(c)
        try:
            self._last_results = lcs.run_all()
        except Exception as exc:
            QMessageBox.critical(self, "Solver error", str(exc))
            return

        lines = []
        for res in self._last_results:
            name = res.get("load_case_name", "?")
            disps = res.get("displacements", {})
            max_d = max((abs(ux) ** 2 + abs(uy) ** 2) ** 0.5
                        for ux, uy in disps.values()) if disps else 0.0
            lines.append(f"── {name} ──")
            lines.append(f"  Max |u| = {max_d:.4e} m")
            for eid, f in res.get("element_axial_force", {}).items():
                state = "T" if f > 0 else ("C" if f < 0 else "Z")
                lines.append(f"  E{eid}: {f:+.2f} N ({state})")
            lines.append("")

        self._results_view.setPlainText("\n".join(lines))
