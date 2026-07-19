"""
=====================================================================
  gui/properties_panel.py

  Right-side properties / input panel.

  Contains four collapsible sections (QGroupBox) for adding:
    • Nodes          (x, y)
    • Elements       (node_i, node_j, material, section)
    • Supports       (node_id, fix_x, fix_y)
    • Loads          (node_id, fx, fy)

  Also shows an "Item Properties" view when something is selected in
  the Model Tree.

  Signals emitted (connected in MainWindow)
  -----------------------------------------
  node_add_requested(x, y)
  element_add_requested(node_i, node_j)
  support_add_requested(node_id, fix_x, fix_y)
  load_add_requested(node_id, fx, fy)
  delete_requested(item_type, item_id)

  Depends on: PySide6, core.model, core.materials, core.sections
=====================================================================
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.materials import MATERIAL_LIBRARY
from core.sections import SECTION_LIBRARY

if TYPE_CHECKING:
    from core.model import Model


# ── Panel stylesheet ──────────────────────────────────────────────────
# Applied once in __init__; affects only this widget and its children.
# Zero logic changes – purely visual.  Uses dynamic properties
# (setProperty) on buttons so primary vs danger vs neutral are styled
# distinctly without subclassing QPushButton.
_PANEL_QSS = """
/* ── scroll area / background ── */
QScrollArea { border: none; background: transparent; }
QWidget#PanelInner { background: transparent; }

/* ── section cards ── */
QGroupBox {
    background: #1a1a28;
    border: 1px solid #2e2e46;
    border-radius: 8px;
    margin-top: 10px;
    padding: 8px 6px 6px 6px;
    font-size: 11px;
    font-weight: 500;
    color: #9090b8;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    left: 8px;
    color: #9090b8;
}

/* ── form labels ── */
QLabel {
    color: #c8c8d8;
    font-size: 11px;
}

/* ── input widgets ── */
QDoubleSpinBox, QSpinBox, QComboBox {
    background: #12121e;
    border: 1px solid #2e2e46;
    border-radius: 5px;
    color: #e0e0f0;
    padding: 2px 4px;
    font-size: 11px;
    min-height: 24px;
}
QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #4f9eff;
}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {
    width: 14px;
    border: none;
    background: #2a2a3e;
}
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: #1a1a28;
    color: #e0e0f0;
    selection-background-color: #2e3f6e;
}

/* ── checkboxes ── */
QCheckBox { color: #c8c8d8; font-size: 11px; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #3e3e5e;
    border-radius: 3px;
    background: #12121e;
}
QCheckBox::indicator:checked {
    background: #4f9eff;
    border-color: #4f9eff;
}

/* ── read-only info box ── */
QTextEdit {
    background: #12121e;
    border: 1px solid #2e2e46;
    border-radius: 5px;
    color: #9090b8;
    font-size: 10px;
    font-family: monospace;
}

/* ── base button ── */
QPushButton {
    background: #24243a;
    color: #c8c8d8;
    border: 1px solid #3a3a58;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
    min-height: 26px;
}
QPushButton:hover { background: #2e2e48; border-color: #4f9eff; }
QPushButton:pressed { background: #1e1e32; }
QPushButton:disabled { color: #4a4a6a; border-color: #2a2a3a; }

/* ── primary action (Add / Set) ── */
QPushButton[btnrole="primary"] {
    background: #1e3a6e;
    color: #c8dcff;
    border-color: #3a5ea8;
}
QPushButton[btnrole="primary"]:hover  { background: #2a4a8a; border-color: #4f9eff; }
QPushButton[btnrole="primary"]:pressed { background: #162e56; }

/* ── danger action (Remove / Delete) ── */
QPushButton[btnrole="danger"] {
    background: #3e1a1a;
    color: #ffb0b0;
    border-color: #6e2e2e;
}
QPushButton[btnrole="danger"]:hover  { background: #4e2222; border-color: #e05555; }
QPushButton[btnrole="danger"]:pressed { background: #2e1212; }
"""


class PropertiesPanelWidget(QWidget):
    """Input forms for adding nodes, elements, supports, and loads."""

    node_add_requested = Signal(float, float)
    element_add_requested = Signal(int, int)
    support_add_requested = Signal(int, bool, bool)
    load_add_requested = Signal(int, float, float)
    delete_requested = Signal(str, int)

    def __init__(self, model: "Model", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model = model
        self._selected_type: Optional[str] = None
        self._selected_id: Optional[int] = None

        self.setMinimumWidth(240)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        # Apply panel stylesheet (visual only – no logic change)
        self.setStyleSheet(_PANEL_QSS)

        # Scrollable container
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setObjectName("PanelInner")
        self._inner_layout = QVBoxLayout(inner)
        self._inner_layout.setAlignment(Qt.AlignTop)
        self._inner_layout.setSpacing(8)
        self._inner_layout.setContentsMargins(4, 4, 4, 4)

        self._build_node_group()
        self._build_element_group()
        self._build_support_group()
        self._build_load_group()
        self._build_selection_group()

        self._inner_layout.addStretch()
        scroll.setWidget(inner)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _build_node_group(self) -> None:
        grp = QGroupBox("Add Node")
        form = QFormLayout(grp)

        self._node_x = QDoubleSpinBox()
        self._node_x.setRange(-1e6, 1e6)
        self._node_x.setDecimals(4)
        self._node_x.setSuffix(" m")
        self._node_y = QDoubleSpinBox()
        self._node_y.setRange(-1e6, 1e6)
        self._node_y.setDecimals(4)
        self._node_y.setSuffix(" m")

        btn = QPushButton("Add Node")
        btn.setProperty("btnrole", "primary")
        btn.clicked.connect(self._on_add_node)

        form.addRow("X:", self._node_x)
        form.addRow("Y:", self._node_y)
        form.addRow(btn)

        self._inner_layout.addWidget(grp)

    def _build_element_group(self) -> None:
        grp = QGroupBox("Add Element")
        form = QFormLayout(grp)

        self._elem_ni = QSpinBox()
        self._elem_ni.setRange(1, 99999)
        self._elem_nj = QSpinBox()
        self._elem_nj.setRange(1, 99999)

        self._elem_material = QComboBox()
        self._elem_material.addItems(list(MATERIAL_LIBRARY.keys()))

        self._elem_section = QComboBox()
        self._elem_section.addItems(list(SECTION_LIBRARY.keys()))

        btn = QPushButton("Add Element")
        btn.setProperty("btnrole", "primary")
        btn.clicked.connect(self._on_add_element)

        form.addRow("Node I:", self._elem_ni)
        form.addRow("Node J:", self._elem_nj)
        form.addRow("Material:", self._elem_material)
        form.addRow("Section:", self._elem_section)
        form.addRow(btn)

        self._inner_layout.addWidget(grp)

    def _build_support_group(self) -> None:
        grp = QGroupBox("Add Support")
        form = QFormLayout(grp)

        self._sup_node = QSpinBox()
        self._sup_node.setRange(1, 99999)
        self._sup_fix_x = QCheckBox("Fix X")
        self._sup_fix_x.setChecked(True)
        self._sup_fix_y = QCheckBox("Fix Y")
        self._sup_fix_y.setChecked(True)

        dof_row = QHBoxLayout()
        dof_row.addWidget(self._sup_fix_x)
        dof_row.addWidget(self._sup_fix_y)

        btn_add = QPushButton("Set Support")
        btn_add.setProperty("btnrole", "primary")
        btn_rem = QPushButton("Remove Support")
        btn_rem.setProperty("btnrole", "danger")
        btn_add.clicked.connect(self._on_add_support)
        btn_rem.clicked.connect(self._on_remove_support)

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_rem)

        form.addRow("Node:", self._sup_node)
        form.addRow("DOFs:", dof_row)
        form.addRow(btn_row)

        self._inner_layout.addWidget(grp)

    def _build_load_group(self) -> None:
        grp = QGroupBox("Add Load")
        form = QFormLayout(grp)

        self._load_node = QSpinBox()
        self._load_node.setRange(1, 99999)
        self._load_fx = QDoubleSpinBox()
        self._load_fx.setRange(-1e12, 1e12)
        self._load_fx.setDecimals(2)
        self._load_fx.setSuffix(" N")
        self._load_fy = QDoubleSpinBox()
        self._load_fy.setRange(-1e12, 1e12)
        self._load_fy.setDecimals(2)
        self._load_fy.setSuffix(" N")

        btn_add = QPushButton("Set Load")
        btn_add.setProperty("btnrole", "primary")
        btn_rem = QPushButton("Remove Load")
        btn_rem.setProperty("btnrole", "danger")
        btn_add.clicked.connect(self._on_add_load)
        btn_rem.clicked.connect(self._on_remove_load)

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_rem)

        form.addRow("Node:", self._load_node)
        form.addRow("Fx:", self._load_fx)
        form.addRow("Fy:", self._load_fy)
        form.addRow(btn_row)

        self._inner_layout.addWidget(grp)

    def _build_selection_group(self) -> None:
        grp = QGroupBox("Selected Item")
        layout = QVBoxLayout(grp)

        self._sel_label = QLabel("Nothing selected")
        self._sel_label.setWordWrap(True)
        self._sel_info = QTextEdit()
        self._sel_info.setReadOnly(True)
        self._sel_info.setMaximumHeight(120)
        self._sel_info.setPlaceholderText("Select an item in the Model Tree…")

        self._btn_delete = QPushButton("Delete Selected")
        self._btn_delete.setProperty("btnrole", "danger")
        self._btn_delete.setEnabled(False)
        self._btn_delete.clicked.connect(self._on_delete_selected)

        layout.addWidget(self._sel_label)
        layout.addWidget(self._sel_info)
        layout.addWidget(self._btn_delete)

        self._inner_layout.addWidget(grp)

    # ------------------------------------------------------------------
    # Slot handlers
    # ------------------------------------------------------------------

    def _on_add_node(self) -> None:
        x = self._node_x.value()
        y = self._node_y.value()
        self.node_add_requested.emit(x, y)

    def _on_add_element(self) -> None:
        ni = self._elem_ni.value()
        nj = self._elem_nj.value()
        if ni == nj:
            QMessageBox.warning(self, "Invalid element", "Node I and Node J must differ.")
            return
        self.element_add_requested.emit(ni, nj)

    def _on_add_support(self) -> None:
        nid = self._sup_node.value()
        self.support_add_requested.emit(nid, self._sup_fix_x.isChecked(),
                                        self._sup_fix_y.isChecked())

    def _on_remove_support(self) -> None:
        nid = self._sup_node.value()
        self.delete_requested.emit("support", nid)

    def _on_add_load(self) -> None:
        nid = self._load_node.value()
        self.load_add_requested.emit(nid, self._load_fx.value(), self._load_fy.value())

    def _on_remove_load(self) -> None:
        nid = self._load_node.value()
        self.delete_requested.emit("load", nid)

    def _on_delete_selected(self) -> None:
        if self._selected_type and self._selected_id is not None:
            self.delete_requested.emit(self._selected_type, self._selected_id)
            self._selected_type = None
            self._selected_id = None
            self._sel_label.setText("Nothing selected")
            self._sel_info.clear()
            self._btn_delete.setEnabled(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_model(self, model: "Model") -> None:
        self._model = model

    def set_selection(self, item_type: str, item_id: int) -> None:
        """Called by the Model Tree when the user clicks an item."""
        self._selected_type = item_type
        self._selected_id = item_id
        self._btn_delete.setEnabled(True)

        m = self._model
        lines = []

        if item_type == "node" and item_id in m.nodes:
            n = m.nodes[item_id]
            lines = [f"Node N{n.id}", f"X = {n.x} m", f"Y = {n.y} m"]
            if item_id in m.boundary_conditions:
                bc = m.boundary_conditions[item_id]
                lines.append(f"Support: fix_x={bc.fix_x}, fix_y={bc.fix_y}")
            if item_id in m.loads:
                ld = m.loads[item_id]
                lines.append(f"Load: Fx={ld.fx} N, Fy={ld.fy} N")

        elif item_type == "element" and item_id in m.elements:
            e = m.elements[item_id]
            lines = [
                f"Element E{e.id}",
                f"N{e.node_i} → N{e.node_j}",
                f"Material: {e.material.name}",
                f"E = {e.E:.3e} Pa",
                f"Section: {e.section.name}",
                f"A = {e.A:.4e} m²",
            ]

        elif item_type == "support" and item_id in m.boundary_conditions:
            bc = m.boundary_conditions[item_id]
            lines = [f"Support at N{bc.node_id}",
                     f"fix_x={bc.fix_x}", f"fix_y={bc.fix_y}"]

        elif item_type == "load" and item_id in m.loads:
            ld = m.loads[item_id]
            lines = [f"Load at N{ld.node_id}",
                     f"Fx = {ld.fx} N", f"Fy = {ld.fy} N"]

        self._sel_label.setText(f"{item_type.capitalize()} #{item_id}")
        self._sel_info.setPlainText("\n".join(lines))
