"""
=====================================================================
  core/commands/support_load_commands.py

  Undoable commands for support and load operations:

    AddSupportCommand    – add / replace a boundary condition at a node
    RemoveSupportCommand – remove a boundary condition from a node
    AddLoadCommand       – add / replace a nodal load at a node
    RemoveLoadCommand    – remove a nodal load from a node

  Supports and loads have an "at most one per node" constraint that
  the Model enforces, so "add" here means "create or replace".
  unexecute() restores whatever was there before (including nothing).

  Depends on: core.model, core.commands.command
=====================================================================
"""

from __future__ import annotations

from typing import Optional, Tuple, TYPE_CHECKING

from core.commands.command import Command

if TYPE_CHECKING:
    from core.model import Model


# ── AddSupportCommand ─────────────────────────────────────────────────

class AddSupportCommand(Command):
    """
    Add (or replace) a boundary condition at node_id.

    Snapshots the previous BC (if any) so unexecute() can restore it.
    """

    def __init__(
        self, model: "Model", node_id: int, fix_x: bool, fix_y: bool
    ) -> None:
        self._model = model
        self._node_id = node_id
        self._new_fix_x = fix_x
        self._new_fix_y = fix_y
        self.description = f"Add Support on N{node_id}"

        # Snapshot the PREVIOUS support (may be None)
        bc = model.boundary_conditions.get(node_id)
        self._old_bc: Optional[Tuple[bool, bool]] = (
            (bc.fix_x, bc.fix_y) if bc else None
        )

    def execute(self) -> None:
        self._model.add_support(self._node_id, self._new_fix_x, self._new_fix_y)

    def unexecute(self) -> None:
        if self._old_bc is None:
            # There was no support before — remove the one we added
            self._model.remove_support(self._node_id)
        else:
            # Restore the previous support
            self._model.add_support(self._node_id, *self._old_bc)


# ── RemoveSupportCommand ──────────────────────────────────────────────

class RemoveSupportCommand(Command):
    """
    Remove the boundary condition at node_id.

    Snapshots it so unexecute() can restore it.
    """

    def __init__(self, model: "Model", node_id: int) -> None:
        self._model = model
        self._node_id = node_id
        self.description = f"Remove Support on N{node_id}"

        # Snapshot the existing BC (must exist for this command to make sense)
        bc = model.boundary_conditions.get(node_id)
        self._old_fix_x: bool = bc.fix_x if bc else True
        self._old_fix_y: bool = bc.fix_y if bc else True
        self._had_bc: bool = bc is not None

    def execute(self) -> None:
        self._model.remove_support(self._node_id)

    def unexecute(self) -> None:
        if self._had_bc:
            self._model.add_support(self._node_id, self._old_fix_x, self._old_fix_y)


# ── AddLoadCommand ────────────────────────────────────────────────────

class AddLoadCommand(Command):
    """
    Add (or replace) a nodal point load at node_id.

    Snapshots the previous load (if any) so unexecute() can restore it.
    """

    def __init__(
        self, model: "Model", node_id: int, fx: float, fy: float
    ) -> None:
        self._model = model
        self._node_id = node_id
        self._new_fx = fx
        self._new_fy = fy
        self.description = f"Add Load on N{node_id}"

        # Snapshot the PREVIOUS load (may be None)
        ld = model.loads.get(node_id)
        self._old_load: Optional[Tuple[float, float]] = (
            (ld.fx, ld.fy) if ld else None
        )

    def execute(self) -> None:
        self._model.add_load(self._node_id, self._new_fx, self._new_fy)

    def unexecute(self) -> None:
        if self._old_load is None:
            # There was no load before — remove the one we added
            self._model.remove_load(self._node_id)
        else:
            # Restore the previous load
            self._model.add_load(self._node_id, *self._old_load)


# ── RemoveLoadCommand ─────────────────────────────────────────────────

class RemoveLoadCommand(Command):
    """
    Remove the nodal load at node_id.

    Snapshots it so unexecute() can restore it.
    """

    def __init__(self, model: "Model", node_id: int) -> None:
        self._model = model
        self._node_id = node_id
        self.description = f"Remove Load on N{node_id}"

        # Snapshot the existing load
        ld = model.loads.get(node_id)
        self._old_fx: float = ld.fx if ld else 0.0
        self._old_fy: float = ld.fy if ld else 0.0
        self._had_load: bool = ld is not None

    def execute(self) -> None:
        self._model.remove_load(self._node_id)

    def unexecute(self) -> None:
        if self._had_load:
            self._model.add_load(self._node_id, self._old_fx, self._old_fy)