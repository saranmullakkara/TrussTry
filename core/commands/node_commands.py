"""
=====================================================================
  core/commands/node_commands.py

  Undoable commands for node operations:

    AddNodeCommand     – add a new node (x, y)
    DeleteNodeCommand  – remove a node, preserving its attached
                         elements, support, and load so undo restores
                         the complete prior state
    MoveNodeCommand    – reposition an existing node

  Support / load preservation on DeleteNodeCommand
  -------------------------------------------------
  Model.remove_node() cascade-deletes both the attached elements and
  the node's BoundaryCondition / NodalLoad in one call. That's the
  right default for the live UI. But for undo to work correctly, we
  must snapshot every piece of state that would be lost *before*
  calling remove_node(), and restore it all in unexecute() in the
  correct order (node first, then elements, then BC/load).

  We store element data as plain dicts so this module has zero
  dependency on TrussElement2D's constructor signature.

  Depends on: core.model, core.commands.command
=====================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from core.commands.command import Command
from core.materials import Material
from core.sections import Section

if TYPE_CHECKING:
    from core.model import Model, BoundaryCondition, NodalLoad, TrussElement2D


# ── helpers ──────────────────────────────────────────────────────────

@dataclass
class _ElemSnapshot:
    """Minimal data needed to resurrect a TrussElement2D."""
    id: int
    node_i: int
    node_j: int
    material: Material
    section: Section
    type_name: str


def _snap_elem(e: "TrussElement2D") -> _ElemSnapshot:
    return _ElemSnapshot(
        id=e.id, node_i=e.node_i, node_j=e.node_j,
        material=e.material, section=e.section, type_name=e.type_name,
    )


# ── AddNodeCommand ────────────────────────────────────────────────────

class AddNodeCommand(Command):
    """
    Add a node at (x, y).

    execute()   → model.add_node(x, y)  [records the assigned id]
    unexecute() → model.remove_node(id) [no cascade – newly added
                  node has no elements/support/load yet]
    """

    def __init__(self, model: "Model", x: float, y: float) -> None:
        self._model = model
        self._x = x
        self._y = y
        self._node_id: Optional[int] = None   # set by execute()
        self.description = f"Add Node at ({x:.3g}, {y:.3g})"

    def execute(self) -> None:
        node = self._model.add_node(self._x, self._y)
        self._node_id = node.id
        self.description = f"Add Node N{node.id}"

    def unexecute(self) -> None:
        # A freshly added node cannot have elements/supports/loads yet,
        # so a plain remove_node is safe and complete.
        if self._node_id is not None:
            self._model.remove_node(self._node_id)


# ── DeleteNodeCommand ─────────────────────────────────────────────────

class DeleteNodeCommand(Command):
    """
    Delete a node (and cascade-delete its attached elements, support,
    and load).  All removed state is snapshotted before deletion so
    unexecute() can restore the model exactly.
    """

    def __init__(self, model: "Model", node_id: int) -> None:
        self._model = model
        self._node_id = node_id
        self.description = f"Delete Node N{node_id}"

        # ── Snapshot BEFORE execute() touches the model ──────────────
        node = model.nodes.get(node_id)
        self._x: float = node.x if node else 0.0
        self._y: float = node.y if node else 0.0

        # All elements that reference this node (will be cascade-deleted)
        self._elem_snapshots: List[_ElemSnapshot] = [
            _snap_elem(e) for e in model.elements.values()
            if node_id in (e.node_i, e.node_j)
        ]

        # Optional support and load at this node
        bc = model.boundary_conditions.get(node_id)
        self._bc: Optional[Tuple[bool, bool]] = (
            (bc.fix_x, bc.fix_y) if bc else None
        )
        ld = model.loads.get(node_id)
        self._load: Optional[Tuple[float, float]] = (
            (ld.fx, ld.fy) if ld else None
        )

        # Remember the id counter so re-insertion can reclaim the exact id
        self._saved_next_node_id: int = model._next_node_id
        self._saved_next_elem_id: int = model._next_elem_id

    def execute(self) -> None:
        # Model.remove_node cascade-deletes elements, BC, and load.
        self._model.remove_node(self._node_id)

    def unexecute(self) -> None:
        m = self._model

        # 1. Restore node-id counter so the re-inserted node gets its original id
        m._next_node_id = self._node_id

        # 2. Re-insert the node
        node = m.add_node(self._x, self._y)
        assert node.id == self._node_id, (
            f"Node id mismatch: expected {self._node_id}, got {node.id}"
        )

        # 3. Re-insert cascade-deleted elements, each reclaiming its original id
        for snap in self._elem_snapshots:
            m._next_elem_id = snap.id
            elem = m.add_element(snap.node_i, snap.node_j,
                                  snap.material, snap.section)
            if elem:
                elem.type_name = snap.type_name

        # 4. Restore id counters to what they were before the delete
        m._next_node_id = self._saved_next_node_id
        m._next_elem_id = self._saved_next_elem_id

        # 5. Re-apply support and load (must happen after node exists)
        if self._bc is not None:
            m.add_support(self._node_id, *self._bc)
        if self._load is not None:
            m.add_load(self._node_id, *self._load)

        # add_support / add_load each fire _notify; that is fine.
        # The extra notifications are harmless – the GUI just refreshes twice.


# ── MoveNodeCommand ───────────────────────────────────────────────────

class MoveNodeCommand(Command):
    """
    Reposition an existing node to (new_x, new_y).

    The node's id and all associated elements/support/load are
    unaffected – only the coordinate pair changes.
    """

    def __init__(
        self, model: "Model", node_id: int, new_x: float, new_y: float
    ) -> None:
        self._model = model
        self._node_id = node_id
        self._new_x = new_x
        self._new_y = new_y

        # Snapshot old position BEFORE execute()
        node = model.nodes.get(node_id)
        self._old_x: float = node.x if node else 0.0
        self._old_y: float = node.y if node else 0.0

        self.description = (
            f"Move Node N{node_id} to ({new_x:.3g}, {new_y:.3g})"
        )

    def execute(self) -> None:
        node = self._model.nodes.get(self._node_id)
        if node is None:
            return
        node.x = self._new_x
        node.y = self._new_y
        self._model._notify()

    def unexecute(self) -> None:
        node = self._model.nodes.get(self._node_id)
        if node is None:
            return
        node.x = self._old_x
        node.y = self._old_y
        self._model._notify()