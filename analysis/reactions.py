"""
=====================================================================
  analysis/reactions.py

  Utilities for interpreting and summarising support reactions from
  a solver results dict.

  This module is intentionally thin: the raw reaction data is already
  produced by ``TrussSolver2D.solve()`` (key ``"reactions"``). What
  this module adds is a structured ``Reaction`` dataclass, a
  ``reaction_summary()`` function that wraps the raw dict, equilibrium
  checks, and formatting helpers used by both the GUI results panel
  and any future report writer.

  Depends on: core.model (for Model type hints only), numpy
=====================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from core.model import Model


@dataclass
class Reaction:
    """
    Support reaction at a single node.

    Attributes
    ----------
    node_id : int
        ID of the supported node.
    rx : float
        Reaction force in the global X direction (N). Zero for a
        roller that only restrains Y.
    ry : float
        Reaction force in the global Y direction (N).
    resultant : float
        Magnitude ``sqrt(rx² + ry²)`` (N).
    angle_deg : float
        Direction of the resultant measured from the +X axis (°).
    """

    node_id: int
    rx: float
    ry: float

    @property
    def resultant(self) -> float:
        return float(np.hypot(self.rx, self.ry))

    @property
    def angle_deg(self) -> float:
        return float(np.degrees(np.arctan2(self.ry, self.rx)))

    def __str__(self) -> str:
        return (
            f"N{self.node_id}: Rx={self.rx:+.2f} N, "
            f"Ry={self.ry:+.2f} N  (|R|={self.resultant:.2f} N, "
            f"θ={self.angle_deg:.1f}°)"
        )


def reaction_summary(
    results: Dict[str, Any],
    model: Optional[Model] = None,
) -> List[Reaction]:
    """
    Build a list of ``Reaction`` objects from a solver results dict.

    Parameters
    ----------
    results : dict
        As returned by ``TrussSolver2D.solve()``.  Must contain
        the ``"reactions"`` key.
    model : Model, optional
        If supplied, only nodes that actually have a boundary
        condition in the model are included (filters out nodes whose
        reaction is numerically nonzero but below floating-point
        noise due to being unconstrained). If omitted, every entry
        in ``results["reactions"]`` is included.

    Returns
    -------
    list[Reaction]
        One entry per supported node, sorted by node id.
    """
    raw: Dict[int, Tuple[float, float]] = results.get("reactions", {})

    if model is not None:
        supported_ids = set(model.boundary_conditions.keys())
        raw = {nid: r for nid, r in raw.items() if nid in supported_ids}

    return sorted(
        [Reaction(node_id=nid, rx=rx, ry=ry) for nid, (rx, ry) in raw.items()],
        key=lambda r: r.node_id,
    )


def check_global_equilibrium(
    results: Dict[str, Any],
    applied_loads: Dict[int, Tuple[float, float]],
    tolerance: float = 1e-6,
) -> Tuple[bool, float, float]:
    """
    Verify that the sum of applied loads plus reactions is zero
    (Newton's 3rd law for the whole structure).

    Parameters
    ----------
    results : dict
        As returned by ``TrussSolver2D.solve()``.
    applied_loads : dict[node_id, (fx, fy)]
        The load dict that was passed to the solver.
    tolerance : float
        Absolute tolerance for the residual force (N).  Default is
        1 µN, appropriate for typical structural magnitudes (kN range).

    Returns
    -------
    (ok, sum_fx, sum_fy) : (bool, float, float)
        ``ok`` is True if both components are within tolerance.
        ``sum_fx`` and ``sum_fy`` are the residuals (should be ≈0).
    """
    sum_fx = sum(fx for fx, _ in applied_loads.values())
    sum_fy = sum(fy for _, fy in applied_loads.values())

    for rx, ry in results.get("reactions", {}).values():
        sum_fx += rx
        sum_fy += ry

    ok = abs(sum_fx) <= tolerance and abs(sum_fy) <= tolerance
    return ok, float(sum_fx), float(sum_fy)


def format_reaction_table(reactions: List[Reaction]) -> str:
    """
    Return a plain-text table of reactions, suitable for the console
    panel or a plain-text report.

    Example output::

        Node    Rx (N)        Ry (N)        |R| (N)       θ (°)
        ----    ----------    ----------    ----------    ------
        N1      +5000.00      +10000.00     11180.34      63.4
        N2      -5000.00      +0.00         5000.00       180.0
    """
    if not reactions:
        return "(no reactions)"

    header = f"{'Node':<8}{'Rx (N)':>14}{'Ry (N)':>14}{'|R| (N)':>14}{'θ (°)':>10}"
    sep = "-" * len(header)
    rows = [header, sep]
    for r in reactions:
        rows.append(
            f"N{r.node_id:<7}{r.rx:>+14.2f}{r.ry:>+14.2f}"
            f"{r.resultant:>14.2f}{r.angle_deg:>10.1f}"
        )
    return "\n".join(rows)
