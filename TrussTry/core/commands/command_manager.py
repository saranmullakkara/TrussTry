"""
=====================================================================
  core/commands/command_manager.py

  The undo/redo stack.

  Design
  ------
  CommandManager is deliberately Qt-free so it can be unit-tested
  without PySide6.  It exposes plain-Python observer callbacks
  (the same pattern Model uses) that the GUI layer wires to Qt
  signals/menu-item state updates.

  Stack behaviour
  ---------------
  • execute(cmd)  – calls cmd.execute(), pushes onto undo stack,
                    clears redo stack.
  • undo()        – pops from undo stack, calls cmd.unexecute(),
                    pushes onto redo stack.
  • redo()        – pops from redo stack, calls cmd.execute(),
                    pushes onto undo stack.
  • clear()       – empties both stacks (called on New/Open).

  The stack is bounded by `max_history` (default 100) to cap memory.

  Depends on: core.commands.command
=====================================================================
"""

from __future__ import annotations

from collections import deque
from typing import Callable, Deque, List, Optional

from core.commands.command import Command


class CommandManager:
    """
    Undo / redo stack for Command objects.

    Parameters
    ----------
    max_history : int
        Maximum number of commands kept on the undo stack.
        Oldest commands are silently discarded when the limit is
        reached.  Default: 100.

    Usage
    -----
    ::

        manager = CommandManager()
        manager.add_listener(update_ui)   # called after every stack change

        cmd = AddNodeCommand(model, x=1.0, y=2.0)
        manager.execute(cmd)              # runs and pushes

        manager.undo()                    # reverses last command
        manager.redo()                    # re-applies it
    """

    def __init__(self, max_history: int = 100) -> None:
        self._max_history = max_history
        self._undo_stack: Deque[Command] = deque()
        self._redo_stack: Deque[Command] = deque()
        self._listeners: List[Callable[[], None]] = []

    # ------------------------------------------------------------------
    # Observer registration (Qt-free, same pattern as Model)
    # ------------------------------------------------------------------

    def add_listener(self, callback: Callable[[], None]) -> None:
        """Register a zero-arg callable invoked after every stack change."""
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self) -> None:
        for cb in self._listeners:
            cb()

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def execute(self, cmd: Command) -> None:
        """
        Execute *cmd*, push it onto the undo stack, and clear the redo
        stack (a new action always invalidates any previously undone
        operations).
        """
        cmd.execute()
        self._undo_stack.append(cmd)
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.popleft()   # drop oldest, cap memory
        self._redo_stack.clear()
        self._notify()

    def undo(self) -> Optional[str]:
        """
        Undo the most recent command.

        Returns the command's description (useful for status-bar
        messages) or None if the stack is empty.
        """
        if not self._undo_stack:
            return None
        cmd = self._undo_stack.pop()
        cmd.unexecute()
        self._redo_stack.append(cmd)
        self._notify()
        return cmd.description

    def redo(self) -> Optional[str]:
        """
        Redo the most recently undone command.

        Returns the command's description or None if nothing to redo.
        """
        if not self._redo_stack:
            return None
        cmd = self._redo_stack.pop()
        cmd.execute()
        self._undo_stack.append(cmd)
        self._notify()
        return cmd.description

    def clear(self) -> None:
        """Empty both stacks (call on New / Open project)."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._notify()

    # ------------------------------------------------------------------
    # State queries (used to enable/disable Undo / Redo menu items)
    # ------------------------------------------------------------------

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    @property
    def undo_description(self) -> Optional[str]:
        """Description of the command that would be undone next, or None."""
        return self._undo_stack[-1].description if self._undo_stack else None

    @property
    def redo_description(self) -> Optional[str]:
        """Description of the command that would be redone next, or None."""
        return self._redo_stack[-1].description if self._redo_stack else None