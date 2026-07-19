"""
=====================================================================
  core/commands/command.py

  Abstract base class for the Command Pattern used by TrussTry's
  undo/redo system.

  Every concrete command:
    1. Captures ALL state it needs to fully reverse its action at
       construction time (before execute() is called).
    2. Implements execute()  – applies the change to the Model.
    3. Implements unexecute() – reverses it completely.

  The Model is the single source of truth.  Commands never cache a
  parallel copy of the model; they store only the minimal delta
  (the before/after values for the specific thing they changed).

  Depends on: nothing (stdlib only)
=====================================================================
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Command(ABC):
    """
    Abstract base for all undoable/redoable operations on a Model.

    Subclasses MUST implement:
        execute()   – apply the change
        unexecute() – reverse the change exactly

    Subclasses SHOULD set:
        description – a short human-readable label shown in menus
                      e.g. "Add Node N3" or "Delete Element E2"
    """

    #: Short label shown in Undo/Redo menu items.
    description: str = "Command"

    @abstractmethod
    def execute(self) -> None:
        """Apply this command's change to the model."""
        raise NotImplementedError

    @abstractmethod
    def unexecute(self) -> None:
        """Reverse this command's change, restoring prior model state."""
        raise NotImplementedError