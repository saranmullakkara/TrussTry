"""
=====================================================================
  core/solver.py

  The solver *contract*, not a solver implementation.

  Why this file exists and is (almost) empty: `analysis/truss2d.py`
  will hold the actual finite-element math (this is where your
  existing truss_solver.py's TrussSolver2D class is headed). If that
  concrete solver lived in core/, then core would depend on numpy and
  on analysis-level concerns, and analysis/ would depend right back on
  core/ for Model/Node/Element -- a circular package dependency.

  Splitting it this way keeps the arrow one-directional:

      core  <---  analysis  <---  gui
      core  <---  visualization <---  gui

  `analysis.truss2d.TrussSolver2D` will subclass `Solver` below and
  implement `solve()`. Anything in gui/ or visualization/ that wants
  "a solver" can type-hint against `core.solver.Solver` without
  importing numpy or the analysis package at all.

  Depends on: nothing (stdlib only)
=====================================================================
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class SolverError(Exception):
    """Base class for all errors raised by any TrussTry solver."""


class SingularStiffnessMatrixError(SolverError):
    """
    Raised when the reduced stiffness matrix is singular (or
    numerically indistinguishable from singular). This means the
    structure -- given its current supports -- is a mechanism and
    cannot carry the applied loads (e.g. no boundary conditions were
    supplied, or the supports provided are insufficient to prevent
    rigid-body translation/rotation).
    """


class InvalidModelError(SolverError):
    """
    Raised for structurally invalid input models: elements referencing
    unknown nodes, zero-length elements, non-positive E or A, etc.
    """


class Solver(ABC):
    """
    Minimal interface every TrussTry solver must implement. Concrete
    solvers (analysis/truss2d.py's TrussSolver2D, and any future
    frame/beam solver) subclass this.
    """

    @abstractmethod
    def solve(self, **kwargs) -> Dict[str, Any]:
        """
        Run the analysis and return a results dictionary. Exact schema
        is defined by each concrete solver's docstring, but by
        convention should include at least "displacements" and
        "reactions" keyed by node id.
        """
        raise NotImplementedError
