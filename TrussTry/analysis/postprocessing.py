"""
=====================================================================
  analysis/postprocessing.py

  Converts raw TrussSolver2D results into engineering-friendly data
  structures and summary objects.

  This module does NO plotting and has NO GUI dependencies.  It is
  the bridge between the raw solver output dict and anything that
  needs structured, typed access to results: the GUI results panels,
  report writers, graph builders, and tests.

  Dependency rule: analysis  <---  core only.
  Must NOT import from gui, visualization, or Qt.

  Depends on: core.model, numpy
=====================================================================
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from core.model import Model


# ======================================================================
# Summary DTO
# ======================================================================

@dataclass
class AnalysisSummary:
    """
    Headline figures from a completed analysis, ready to display in a
    summary panel or include in a report header.

    All stress / force / displacement values are the absolute maxima
    across the entire model.
    """

    num_nodes: int
    num_elements: int

    max_displacement: float   # m   -- maximum nodal displacement magnitude
    max_stress: float         # Pa  -- maximum absolute axial stress
    max_strain: float         # --  -- maximum absolute axial strain
    max_axial_force: float    # N   -- maximum absolute axial force

    total_reaction_force: float  # N  -- sum of |reaction| components


# ======================================================================
# Post-processor
# ======================================================================

class PostProcessor:
    """
    Converts a raw ``TrussSolver2D.solve()`` results dict and the
    originating ``Model`` into typed, indexable data.

    Parameters
    ----------
    model : core.model.Model
        The structural model that was analysed.  Used for node/element
        ordering and for decorating output rows with ids.
    results : dict
        The dict returned by ``TrussSolver2D.solve()``.  Expected keys:
        ``"displacements"``, ``"reactions"``, ``"element_stress"``,
        ``"element_strain"``, ``"element_axial_force"``, ``"K_global"``.

    Usage
    -----
    ::

        solver  = TrussSolver2D.from_model(model)
        results = solver.solve()
        pp      = PostProcessor(model, results)

        summary = pp.summary()
        for row in pp.node_table():
            print(row)
    """

    def __init__(self, model: Model, results: Dict[str, Any]) -> None:
        self.model = model
        self.results = results

        # Cache sorted id lists so every property uses the same order.
        self._node_ids: List[int] = sorted(model.nodes.keys())
        self._elem_ids: List[int] = sorted(model.elements.keys())

    # ------------------------------------------------------------------
    # Raw result accessors  (dicts keyed by node_id / element_id)
    # ------------------------------------------------------------------

    @property
    def displacements(self) -> Dict[int, Tuple[float, float]]:
        """
        Per-node displacement: ``{node_id: (ux_m, uy_m)}``.

        The solver returns node ids in its own internal order; we
        surface the raw dict unchanged -- callers should not assume
        insertion order matches node id order.
        """
        return self.results.get("displacements", {})

    @property
    def reactions(self) -> Dict[int, Tuple[float, float]]:
        """
        Per-node reaction force at constrained DOFs:
        ``{node_id: (rx_N, ry_N)}``.

        Only nodes that have at least one fixed DOF appear here.
        """
        return self.results.get("reactions", {})

    @property
    def element_stress(self) -> Dict[Any, float]:
        """Per-element axial stress (Pa): ``{elem_id: sigma}``."""
        return self.results.get("element_stress", {})

    @property
    def element_strain(self) -> Dict[Any, float]:
        """Per-element axial strain (dimensionless): ``{elem_id: epsilon}``."""
        return self.results.get("element_strain", {})

    @property
    def element_axial_force(self) -> Dict[Any, float]:
        """
        Per-element axial force (N): ``{elem_id: F}``.

        Sign convention (from the solver): positive = tension,
        negative = compression.
        """
        return self.results.get("element_axial_force", {})

    @property
    def K_global(self) -> Optional[np.ndarray]:
        """The assembled global stiffness matrix, or None if absent."""
        return self.results.get("K_global")

    # ------------------------------------------------------------------
    # Derived scalar quantities
    # ------------------------------------------------------------------

    def displacement_magnitude(self, node_id: int) -> float:
        """Return |u| in metres for the given node, or 0.0 if missing."""
        disp = self.displacements.get(node_id)
        if disp is None:
            return 0.0
        ux, uy = disp
        return math.hypot(ux, uy)

    def max_displacement_magnitude(self) -> Tuple[float, Optional[int]]:
        """
        Return ``(magnitude_m, node_id)`` for the node with the largest
        displacement.  Returns ``(0.0, None)`` if no displacements.
        """
        if not self.displacements:
            return 0.0, None
        best_nid, best_mag = max(
            self.displacements.items(),
            key=lambda kv: math.hypot(*kv[1]),
        )
        return math.hypot(*self.displacements[best_nid]), best_nid

    def max_abs_stress(self) -> Tuple[float, Optional[Any]]:
        """
        Return ``(|stress|_Pa, elem_id)`` for the most-stressed element.
        Returns ``(0.0, None)`` if no elements.
        """
        if not self.element_stress:
            return 0.0, None
        best_eid = max(self.element_stress, key=lambda eid: abs(self.element_stress[eid]))
        return abs(self.element_stress[best_eid]), best_eid

    def max_abs_axial_force(self) -> Tuple[float, Optional[Any]]:
        """
        Return ``(|F|_N, elem_id)`` for the element with the largest
        axial force magnitude.  Returns ``(0.0, None)`` if empty.
        """
        if not self.element_axial_force:
            return 0.0, None
        best_eid = max(
            self.element_axial_force,
            key=lambda eid: abs(self.element_axial_force[eid]),
        )
        return abs(self.element_axial_force[best_eid]), best_eid

    def equilibrium_check(self) -> Tuple[bool, float, float]:
        """
        Verify global equilibrium: sum(applied loads) + sum(reactions) ≈ 0.

        Returns
        -------
        (ok, residual_x, residual_y)
            ``ok`` is True when both components are < 1 µN.
        """
        sum_fx = sum(ld.fx for ld in self.model.loads.values())
        sum_fy = sum(ld.fy for ld in self.model.loads.values())
        for rx, ry in self.reactions.values():
            sum_fx += rx
            sum_fy += ry
        tol = 1e-6  # 1 µN
        ok = abs(sum_fx) < tol and abs(sum_fy) < tol
        return ok, float(sum_fx), float(sum_fy)

    # ------------------------------------------------------------------
    # Row-oriented tables (suitable for Qt table widgets)
    # ------------------------------------------------------------------

    def node_table(self) -> List[Dict[str, Any]]:
        """
        Return one dict per node, in ascending node-id order.

        Keys: ``node_id``, ``x``, ``y``, ``ux``, ``uy``, ``magnitude``.
        """
        rows = []
        for nid in self._node_ids:
            node = self.model.nodes[nid]
            ux, uy = self.displacements.get(nid, (0.0, 0.0))
            rows.append({
                "node_id":   nid,
                "x":         node.x,
                "y":         node.y,
                "ux":        float(ux),
                "uy":        float(uy),
                "magnitude": math.hypot(ux, uy),
            })
        return rows

    def element_table(self) -> List[Dict[str, Any]]:
        """
        Return one dict per element, in ascending element-id order.

        Keys: ``element_id``, ``node_i``, ``node_j``, ``stress``,
        ``strain``, ``axial_force``, ``state``.

        ``state`` is the string ``"Tension"``, ``"Compression"``, or
        ``"Zero"`` based on the sign of the axial force.
        """
        rows = []
        for eid in self._elem_ids:
            elem = self.model.elements[eid]
            stress = float(self.element_stress.get(eid, 0.0))
            strain = float(self.element_strain.get(eid, 0.0))
            force  = float(self.element_axial_force.get(eid, 0.0))
            if force > 1e-9:
                state = "Tension"
            elif force < -1e-9:
                state = "Compression"
            else:
                state = "Zero"
            rows.append({
                "element_id":  eid,
                "node_i":      elem.node_i,
                "node_j":      elem.node_j,
                "stress":      stress,
                "strain":      strain,
                "axial_force": force,
                "state":       state,
            })
        return rows

    def reaction_table(self) -> List[Dict[str, Any]]:
        """
        Return one dict per supported node (those with non-zero
        reactions), in ascending node-id order.

        Keys: ``node_id``, ``rx``, ``ry``, ``resultant``.

        Values smaller than 1 pN in absolute value are rounded to
        zero to suppress floating-point noise.
        """
        _tol = 1e-12  # 1 pN -- below this we call it zero
        rows = []
        for nid in sorted(self.reactions.keys()):
            rx, ry = self.reactions[nid]
            rx = float(rx) if abs(rx) > _tol else 0.0
            ry = float(ry) if abs(ry) > _tol else 0.0
            rows.append({
                "node_id":   nid,
                "rx":        rx,
                "ry":        ry,
                "resultant": math.hypot(rx, ry),
            })
        return rows

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> AnalysisSummary:
        """
        Build and return an :class:`AnalysisSummary` for the current
        results.
        """
        max_disp, _ = self.max_displacement_magnitude()
        max_stress, _ = self.max_abs_stress()

        max_strain = (
            max((abs(v) for v in self.element_strain.values()), default=0.0)
        )

        max_force, _ = self.max_abs_axial_force()

        total_reaction = sum(
            math.hypot(rx, ry) for rx, ry in self.reactions.values()
        )

        return AnalysisSummary(
            num_nodes=len(self.model.nodes),
            num_elements=len(self.model.elements),
            max_displacement=max_disp,
            max_stress=max_stress,
            max_strain=max_strain,
            max_axial_force=max_force,
            total_reaction_force=total_reaction,
        )
