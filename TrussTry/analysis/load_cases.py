"""
=====================================================================
  analysis/load_cases.py

  Named load cases and load-case sets for parametric analysis.

  A ``LoadCase`` is a named, standalone set of nodal loads that can
  be applied to a ``core.model.Model`` *in place of* (or in addition
  to) its permanently stored loads. This lets users define
  Dead + Live + Wind cases without duplicating the model.

  A ``LoadCaseSet`` groups related cases and drives the analysis
  runner to solve each one and collect results side by side.

  Depends on: core.model, analysis.truss2d
=====================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.model import Model, NodalLoad
from analysis.truss2d import TrussSolver2D


@dataclass
class LoadCase:
    """
    A named set of nodal point loads.

    Attributes
    ----------
    name : str
        Short label, e.g. ``"Dead"`` or ``"Wind +X"``.
    loads : dict[int, (fx, fy)]
        Mapping of node id to (fx, fy) in Newtons. Node ids that are
        absent from this dict carry zero load for this case.
    description : str, optional
        Longer human-readable description for reports.
    """

    name: str
    loads: Dict[int, Tuple[float, float]] = field(default_factory=dict)
    description: str = ""

    @classmethod
    def from_model_loads(cls, model: Model, name: str = "Base") -> "LoadCase":
        """
        Snapshot the loads currently stored in a Model into a
        LoadCase.  Useful for converting an existing model's loads
        into a named case without changing the model.
        """
        return cls(
            name=name,
            loads={
                ld.node_id: (ld.fx, ld.fy)
                for ld in model.loads.values()
            },
        )

    def add_load(self, node_id: int, fx: float = 0.0, fy: float = 0.0) -> None:
        """Add or replace the point load for ``node_id`` in this case."""
        self.loads[node_id] = (fx, fy)

    def remove_load(self, node_id: int) -> None:
        """Remove the point load for ``node_id``, if present."""
        self.loads.pop(node_id, None)

    def scale(self, factor: float) -> "LoadCase":
        """
        Return a new LoadCase with all load magnitudes multiplied by
        ``factor``.  Useful for limit-state combinations.
        """
        return LoadCase(
            name=f"{self.name} ×{factor}",
            loads={nid: (fx * factor, fy * factor) for nid, (fx, fy) in self.loads.items()},
            description=self.description,
        )

    def __add__(self, other: "LoadCase") -> "LoadCase":
        """
        Combine two load cases by superposition.  Loads at the same
        node are summed component-wise.
        """
        combined: Dict[int, Tuple[float, float]] = dict(self.loads)
        for nid, (fx, fy) in other.loads.items():
            if nid in combined:
                ex, ey = combined[nid]
                combined[nid] = (ex + fx, ey + fy)
            else:
                combined[nid] = (fx, fy)
        return LoadCase(
            name=f"{self.name} + {other.name}",
            loads=combined,
        )


class LoadCaseSet:
    """
    A collection of ``LoadCase`` objects to be analysed against the
    same structural model.

    Usage
    -----
    ::

        lcs = LoadCaseSet(model)
        lcs.add(dead_case)
        lcs.add(live_case)
        lcs.add(dead_case + live_case)
        all_results = lcs.run_all(deformation_scale=200)

    The model's own permanently stored loads are left untouched; each
    case substitutes its own load dict into the solver.
    """

    def __init__(self, model: Model) -> None:
        self._model = model
        self._cases: List[LoadCase] = []

    # ------------------------------------------------------------------
    # Case management
    # ------------------------------------------------------------------

    def add(self, case: LoadCase) -> None:
        """Append a LoadCase to the set."""
        self._cases.append(case)

    def remove(self, name: str) -> None:
        """Remove the first case whose name matches ``name``."""
        self._cases = [c for c in self._cases if c.name != name]

    def clear(self) -> None:
        """Remove all cases."""
        self._cases.clear()

    @property
    def cases(self) -> List[LoadCase]:
        """Read-only list of cases in insertion order."""
        return list(self._cases)

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def run(
        self,
        case: LoadCase,
        deformation_scale: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Solve the model for a single LoadCase.

        Parameters
        ----------
        case : LoadCase
            The load case to analyse.  Its loads override (not
            supplement) the model's own loads.
        deformation_scale : float
            Passed straight through to ``TrussSolver2D.solve()``.

        Returns
        -------
        dict
            Results dictionary as returned by ``TrussSolver2D.solve()``,
            plus an extra ``"load_case_name"`` key.
        """
        m = self._model
        nodes = {n.id: (n.x, n.y) for n in m.nodes.values()}
        elements = [
            {"id": e.id, "node_i": e.node_i, "node_j": e.node_j,
             "E": e.E, "A": e.A}
            for e in m.elements.values()
        ]
        bcs = {
            bc.node_id: (bc.fix_x, bc.fix_y)
            for bc in m.boundary_conditions.values()
        }

        solver = TrussSolver2D(
            nodes=nodes,
            elements=elements,
            loads=case.loads,
            boundary_conditions=bcs,
        )
        results = solver.solve(deformation_scale=deformation_scale)
        results["load_case_name"] = case.name
        return results

    def run_all(
        self,
        deformation_scale: float = 1.0,
    ) -> List[Dict[str, Any]]:
        """
        Solve the model for every case in the set and return a list
        of result dicts in the same order.

        Returns
        -------
        list[dict]
            One entry per case; each dict is as returned by
            ``run()``.
        """
        return [self.run(c, deformation_scale) for c in self._cases]
