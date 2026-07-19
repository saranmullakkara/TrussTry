"""
=====================================================================
  gui/dialogs/element_dialog.py

  Modal dialog for creating or editing a truss element.
  Lets the user pick Node I, Node J, material, and section from
  the library dropdowns (plus custom E/A entry).
=====================================================================
"""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QLabel, QSpinBox, QVBoxLayout, QWidget,
)

from core.materials import MATERIAL_LIBRARY
from core.sections import SECTION_LIBRARY


class ElementDialog(QDialog):
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        node_i: int = 1,
        node_j: int = 2,
        material_name: str = "Steel A36",
        section_name: str = "Custom 0.01 m^2",
        title: str = "Element",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)

        self._ni = QSpinBox()
        self._ni.setRange(1, 99999)
        self._ni.setValue(node_i)

        self._nj = QSpinBox()
        self._nj.setRange(1, 99999)
        self._nj.setValue(node_j)

        self._material = QComboBox()
        self._material.addItems(list(MATERIAL_LIBRARY.keys()))
        if material_name in MATERIAL_LIBRARY:
            self._material.setCurrentText(material_name)

        self._section = QComboBox()
        self._section.addItems(list(SECTION_LIBRARY.keys()))
        if section_name in SECTION_LIBRARY:
            self._section.setCurrentText(section_name)

        form = QFormLayout(self)
        form.addRow("Node I:", self._ni)
        form.addRow("Node J:", self._nj)
        form.addRow("Material:", self._material)
        form.addRow("Section:", self._section)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> Tuple[int, int, str, str]:
        return (
            self._ni.value(),
            self._nj.value(),
            self._material.currentText(),
            self._section.currentText(),
        )

    @staticmethod
    def get_element(
        parent: Optional[QWidget] = None,
        **kwargs,
    ) -> Optional[Tuple[int, int, str, str]]:
        dlg = ElementDialog(parent, **kwargs)
        if dlg.exec() == QDialog.Accepted:
            return dlg.values()
        return None
