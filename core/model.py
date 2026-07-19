"""
=====================================================================
  core/model.py

  The structural data model: Node, TrussElement2D, BoundaryCondition,
  NodalLoad, and the Model container that owns them.

  Ported from fea_gui.py's in-GUI data classes. The one deliberate
  change: Model no longer inherits QObject / emits a Qt Signal. Core
  must not depend on any GUI toolkit -- it needs to be importable and
  unit-testable with no PySide6 installed at all, and reusable from a
  future non-Qt front end (CLI, web, whatever) without modification.

  Instead, Model exposes a plain-Python observer list: call
  `model.add_listener(fn)` to register a zero-argument callable that
  gets invoked after every mutation. In gui/, wrap this in a QObject
  adapter (or just call `model.add_listener(self.changed.emit)` on a
  thin Qt wrapper) rather than resurrecting the Qt dependency here.

  Depends on: core.materials, core.sections
=====================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from core.materials import Material, DEFAULT_MATERIAL
from core.sections import Section, DEFAULT_SECTION


@dataclass
class Node:
    id: int
    x: float
    y: float


@dataclass
class TrussElement2D:
    """
    A two-force (axial-only) truss member connecting node_i to
    node_j. Material and section are now first-class objects (see
    core.materials / core.sections) rather than bare E/A floats --
    `E` and `A` remain available as read-only convenience properties
    so existing code that expects `element.E` / `element.A` keeps
    working unchanged.
    """

    id: int
    node_i: int
    node_j: int
    material: Material = field(default_factory=lambda: DEFAULT_MATERIAL)
    section: Section = field(default_factory=lambda: DEFAULT_SECTION)
    type_name: str = "Truss2D"

    @property
    def E(self) -> float:
        return self.material.E

    @property
    def A(self) -> float:
        return self.section.area


@dataclass
class BoundaryCondition:
    """A support at a node: which global DOFs (Ux, Uy) are fixed to
    zero displacement. At most one BoundaryCondition exists per node
    -- it is keyed by node_id in Model.boundary_conditions."""
    node_id: int
    fix_x: bool = True
    fix_y: bool = True


@dataclass
class NodalLoad:
    """An externally applied point load at a node, in the global X/Y
    directions (N). At most one NodalLoad exists per node -- it is
    keyed by node_id in Model.loads."""
    node_id: int
    fx: float = 0.0
    fy: float = 0.0


class Model:
    """
    Holds the structural model (nodes + elements + supports + loads)
    and notifies registered listeners whenever it changes. Framework-
    agnostic: register any zero-argument callable via add_listener();
    the GUI layer is responsible for bridging that to Qt signals.
    """

    def __init__(self):
        self.nodes: Dict[int, Node] = {}
        self.elements: Dict[int, TrussElement2D] = {}
        # Keyed by node_id -- at most one support and one load per node.
        self.boundary_conditions: Dict[int, BoundaryCondition] = {}
        self.loads: Dict[int, NodalLoad] = {}
        self._next_node_id = 1
        self._next_elem_id = 1
        self._listeners: List[Callable[[], None]] = []

    # -----------------------------------------------------------------
    # Change notification
    # -----------------------------------------------------------------
    def add_listener(self, callback: Callable[[], None]) -> None:
        """Register a zero-argument callable to be invoked after every
        mutation. (GUI code: pass a Qt signal's `.emit`, e.g.
        `model.add_listener(self.changed.emit)`.)"""
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self) -> None:
        for callback in self._listeners:
            callback()

    # -----------------------------------------------------------------
    # Nodes / elements
    # -----------------------------------------------------------------
    def add_node(self, x: float, y: float) -> Node:
        node = Node(id=self._next_node_id, x=x, y=y)
        self.nodes[node.id] = node
        self._next_node_id += 1
        self._notify()
        return node

    def add_element(
        self,
        node_i: int,
        node_j: int,
        material: Optional[Material] = None,
        section: Optional[Section] = None,
    ) -> Optional[TrussElement2D]:
        if node_i == node_j:
            return None
        elem = TrussElement2D(
            id=self._next_elem_id,
            node_i=node_i,
            node_j=node_j,
            material=material or DEFAULT_MATERIAL,
            section=section or DEFAULT_SECTION,
        )
        self.elements[elem.id] = elem
        self._next_elem_id += 1
        self._notify()
        return elem

    def remove_node(self, node_id: int):
        self.nodes.pop(node_id, None)
        dead = [eid for eid, e in self.elements.items()
                if node_id in (e.node_i, e.node_j)]
        for eid in dead:
            self.elements.pop(eid, None)
        # A node's support and load are meaningless once the node is
        # gone, so cascade-delete them the same way attached elements
        # are cascade-deleted above.
        self.boundary_conditions.pop(node_id, None)
        self.loads.pop(node_id, None)
        self._notify()

    def remove_element(self, elem_id: int):
        self.elements.pop(elem_id, None)
        self._notify()

    # -----------------------------------------------------------------
    # Supports / loads
    # -----------------------------------------------------------------
    def add_support(self, node_id: int, fix_x: bool = True,
                     fix_y: bool = True) -> Optional[BoundaryCondition]:
        """Create or replace the support at node_id. Returns None (and
        does nothing) if node_id does not exist."""
        if node_id not in self.nodes:
            return None
        bc = BoundaryCondition(node_id=node_id, fix_x=fix_x, fix_y=fix_y)
        self.boundary_conditions[node_id] = bc
        self._notify()
        return bc

    def remove_support(self, node_id: int):
        if node_id in self.boundary_conditions:
            del self.boundary_conditions[node_id]
            self._notify()

    def add_load(self, node_id: int, fx: float = 0.0,
                 fy: float = 0.0) -> Optional[NodalLoad]:
        """Create or replace the point load at node_id. Returns None
        (and does nothing) if node_id does not exist."""
        if node_id not in self.nodes:
            return None
        load = NodalLoad(node_id=node_id, fx=fx, fy=fy)
        self.loads[node_id] = load
        self._notify()
        return load

    def remove_load(self, node_id: int):
        if node_id in self.loads:
            del self.loads[node_id]
            self._notify()

    # -----------------------------------------------------------------
    # Bulk operations
    # -----------------------------------------------------------------
    def clear(self):
        self.nodes.clear()
        self.elements.clear()
        self.boundary_conditions.clear()
        self.loads.clear()
        self._next_node_id = 1
        self._next_elem_id = 1
        self._notify()

    def load_example_truss(self):
        """Seed the model with the same triangular truss used as the
        worked example in the original solver script: pin at N1,
        roller at N2, -10,000 N point load at N3."""
        self.clear()
        n1 = self.add_node(0.0, 0.0)
        n2 = self.add_node(4.0, 0.0)
        n3 = self.add_node(2.0, 3.0)
        self.add_element(n1.id, n2.id)
        self.add_element(n2.id, n3.id)
        self.add_element(n1.id, n3.id)
        self.add_support(n1.id, fix_x=True, fix_y=True)
        self.add_support(n2.id, fix_x=False, fix_y=True)
        self.add_load(n3.id, fx=0.0, fy=-10000.0)
