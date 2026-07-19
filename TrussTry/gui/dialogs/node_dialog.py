"""
=====================================================================
  gui/dialogs/node_dialog.py

  Modal dialog for creating or editing a single node.
  Returns (x, y) via static method NodeDialog.get_coords().
=====================================================================
"""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QWidget,
)


class NodeDialog(QDialog):
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        x: float = 0.0,
        y: float = 0.0,
        title: str = "Node",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)

        self._x = QDoubleSpinBox()
        self._x.setRange(-1e6, 1e6)
        self._x.setDecimals(4)
        self._x.setSuffix(" m")
        self._x.setValue(x)

        self._y = QDoubleSpinBox()
        self._y.setRange(-1e6, 1e6)
        self._y.setDecimals(4)
        self._y.setSuffix(" m")
        self._y.setValue(y)

        form = QFormLayout(self)
        form.addRow("X:", self._x)
        form.addRow("Y:", self._y)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> Tuple[float, float]:
        return self._x.value(), self._y.value()

    @staticmethod
    def get_coords(
        parent: Optional[QWidget] = None,
        x: float = 0.0,
        y: float = 0.0,
        title: str = "Add / Edit Node",
    ) -> Optional[Tuple[float, float]]:
        dlg = NodeDialog(parent, x, y, title)
        if dlg.exec() == QDialog.Accepted:
            return dlg.values()
        return None
