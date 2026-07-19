"""
=====================================================================
  core/commands/element_commands.py

  Undoable commands for element operations:

    AddElementCommand     – add a new truss element between two nodes
    DeleteElementCommand  – remove an element (nodes / BCs / loads are
                            NOT touched – only the element itself goes)

  Note: elements don't own supports or loads; those live on nodes.
  DeleteElementCommand therefore only needs to snapshot the element
  itself, not any BCs or loads.

  Redo-correctness guarantee
  --------------------------
  Both commands must produce the *same element id* on every execute()
  call, whether it is the first run or a redo.  The naive approach of
  calling model.add_element() and storing whatever id the model assigns
  breaks on redo because the id counter has advanced since the undo.

  Fix: on the first execute() we let the model assign the id freely and
  record it.  On every subsequent execute() (redo) we pin
  model._next_elem_id = self._elem_id before the insertion and restore
  the counter immediately after, so the element always lands at the same
  id regardless of the current counter value.

  Depends on: core.model, core.commands.command
=====================================================================
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from core.commands.command import Command
from core.materials import Material, DEFAULT_MATERIAL
from core.sections import Section, DEFAULT_SECTION

if TYPE_CHECKING:
    from core.model import Model


# ── AddElementCommand ─────────────────────────────────────────────────

class AddElementCommand(Command):
    """
    Add a truss element connecting node_i to node_j.

    First execute()  → model.add_element() assigns a new id; we record it.
    unexecute()      → model.remove_element(recorded_id)
    Subsequent redo  → pin _next_elem_id = recorded_id, insert, restore counter.
                       The element always gets the same id as on the first run.
    """

    def __init__(
        self,
        model: "Model",
        node_i: int,
        node_j: int,
        material: Optional[Material] = None,
        section: Optional[Section] = None,
    ) -> None:
        self._model = model
        self._node_i = node_i
        self._node_j = node_j
        self._material = material or DEFAULT_MATERIAL
        self._section = section or DEFAULT_SECTION
        self._elem_id: Optional[int] = None   # set on first execute()
        self._first_run: bool = True           # distinguishes first run from redo
        self.description = f"Add Element N{node_i}→N{node_j}"

    def execute(self) -> None:
        m = self._model

        if self._first_run:
            # ── First run: let the model assign the id freely ────────
            elem = m.add_element(
                self._node_i, self._node_j, self._material, self._section
            )
            if elem is not None:
                self._elem_id = elem.id
                self.description = f"Add Element E{elem.id}"
            self._first_run = False

        else:
            # ── Redo: pin the counter so we get the *same* id ────────
            if self._elem_id is None:
                return                          # first run produced no element; skip
            saved = m._next_elem_id
            m._next_elem_id = self._elem_id
            m.add_element(
                self._node_i, self._node_j, self._material, self._section
            )
            # Restore so the model's free-id sequence is undisturbed.
            # If _elem_id was *below* saved (typical), restore saved.
            # If somehow saved < _elem_id + 1, advance to avoid re-use.
            m._next_elem_id = max(saved, self._elem_id + 1)

    def unexecute(self) -> None:
        if self._elem_id is not None:
            self._model.remove_element(self._elem_id)


# ── DeleteElementCommand ──────────────────────────────────────────────

class DeleteElementCommand(Command):
    """
    Delete a single truss element.  The two endpoint nodes (and any
    supports / loads attached to them) are left intact.

    All element properties are snapshotted at construction time so
    unexecute() can restore an identical element with the same id.

    On redo (execute() called a second time), the element id is pinned
    using the same counter-manipulation technique as AddElementCommand
    so the deletion always operates on the correct id.
    """

    def __init__(self, model: "Model", elem_id: int) -> None:
        self._model = model
        self._elem_id = elem_id
        self.description = f"Delete Element E{elem_id}"

        # Snapshot BEFORE execute()
        elem = model.elements.get(elem_id)
        if elem is not None:
            self._node_i: int = elem.node_i
            self._node_j: int = elem.node_j
            self._material: Material = elem.material
            self._section: Section = elem.section
            self._type_name: str = elem.type_name
        else:
            # Element doesn't exist – execute/unexecute will be no-ops
            self._node_i = 0
            self._node_j = 0
            self._material = DEFAULT_MATERIAL
            self._section = DEFAULT_SECTION
            self._type_name = "Truss2D"

        self._saved_next_elem_id: int = model._next_elem_id

    def execute(self) -> None:
        # Straightforward: remove the element by its snapshotted id.
        # Works identically on first run and on redo because the id
        # never changes – unexecute() always restores the same id.
        self._model.remove_element(self._elem_id)

    def unexecute(self) -> None:
        m = self._model
        # Pin the counter so the re-inserted element reclaims its original id.
        m._next_elem_id = self._elem_id
        elem = m.add_element(
            self._node_i, self._node_j, self._material, self._section
        )
        if elem is not None:
            elem.type_name = self._type_name
        # Restore the counter to exactly where it was before the delete.
        m._next_elem_id = max(self._saved_next_elem_id, self._elem_id + 1)
