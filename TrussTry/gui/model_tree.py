"""
=====================================================================
  gui/model_tree.py

  Left-side tree widget showing the structural model hierarchy:

    Model
    ├── Nodes
    │   ├── N1  (0.0, 0.0)
    │   └── N2  ...
    ├── Elements
    │   └── E1  N1-N2
    ├── Supports
    │   └── N1  pin
    └── Loads
        └── N3  Fx=0  Fy=-10000

  Clicking any leaf emits item_selected(type, id) so the Properties
  Panel can display detail and the Delete button can act on it.

  Depends on: PySide6, core.model (type hints only)
=====================================================================
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from core.model import Model

# Role used to store (item_type, item_id) in the UserRole of leaf nodes
_TYPE_ROLE = Qt.UserRole
_ID_ROLE = Qt.UserRole + 1


def _leaf(parent: QTreeWidgetItem, label: str,
          item_type: str, item_id: int) -> QTreeWidgetItem:
    item = QTreeWidgetItem(parent, [label])
    item.setData(0, _TYPE_ROLE, item_type)
    item.setData(0, _ID_ROLE, item_id)
    return item


class ModelTreeWidget(QWidget):
    """
    A QTreeWidget that mirrors the Model hierarchy.

    Signals
    -------
    item_selected(type: str, id: int)
        Emitted when the user clicks a leaf node in the tree.
        `type` is one of "node", "element", "support", "load".
    """

    item_selected = Signal(str, int)

    def __init__(self, model: "Model", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model = model

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setSelectionMode(QTreeWidget.SingleSelection)
        self._tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._tree.itemClicked.connect(self._on_item_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tree)

        self.setMinimumWidth(180)
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_model(self, model: "Model") -> None:
        self._model = model
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the entire tree from the current model state."""
        m = self._model
        self._tree.clear()

        # Root
        root = QTreeWidgetItem(self._tree, ["Model"])
        root.setExpanded(True)

        # Nodes
        nodes_item = QTreeWidgetItem(root, [f"Nodes ({len(m.nodes)})"])
        nodes_item.setExpanded(True)
        for nid, node in sorted(m.nodes.items()):
            _leaf(nodes_item, f"N{nid}  ({node.x:.3g}, {node.y:.3g})", "node", nid)

        # Elements
        elems_item = QTreeWidgetItem(root, [f"Elements ({len(m.elements)})"])
        elems_item.setExpanded(True)
        for eid, elem in sorted(m.elements.items()):
            _leaf(elems_item,
                  f"E{eid}  N{elem.node_i}→N{elem.node_j}  [{elem.material.name}]",
                  "element", eid)

        # Supports
        bcs = m.boundary_conditions
        sups_item = QTreeWidgetItem(root, [f"Supports ({len(bcs)})"])
        sups_item.setExpanded(True)
        for nid, bc in sorted(bcs.items()):
            kind = ("Pin" if bc.fix_x and bc.fix_y
                    else "Roller-X" if not bc.fix_x
                    else "Roller-Y")
            _leaf(sups_item, f"N{nid}  {kind}", "support", nid)

        # Loads
        loads = m.loads
        loads_item = QTreeWidgetItem(root, [f"Loads ({len(loads)})"])
        loads_item.setExpanded(True)
        for nid, ld in sorted(loads.items()):
            _leaf(loads_item,
                  f"N{nid}  Fx={ld.fx:.3g} N  Fy={ld.fy:.3g} N",
                  "load", nid)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        item_type = item.data(0, _TYPE_ROLE)
        item_id = item.data(0, _ID_ROLE)
        if item_type is not None and item_id is not None:
            self.item_selected.emit(item_type, item_id)
