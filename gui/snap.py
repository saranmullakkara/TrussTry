"""
=====================================================================
  gui/snap.py

  Centralized snapping engine for canvas editing.

  This module is intentionally standalone: no imports from the rest
  of TrussTry, no Qt, no matplotlib. That means it can be unit-tested
  with zero imports, reused by a future 3D editor or CLI, and is the
  single place snap logic lives -- no tool in gui/ should ever
  duplicate this math.

  Usage
  -----
      from gui.snap import GridConfig, snap_point

      config = GridConfig(enabled=True, spacing=0.5)
      sx, sy = snap_point(x, y, config)

  Phase A (implemented now)
  --------------------------
  Grid snapping only: round (x, y) to the nearest multiple of
  ``config.spacing`` on each axis, when ``config.enabled`` is True.

  Phase B (future extension points -- fields exist, branches do not
  yet)
  --------------------------------------------------------------------
  ``visible``, ``snap_to_node``, ``snap_to_midpoint``,
  ``snap_to_intersection`` are reserved fields on GridConfig for
  future snap modes (node snap, midpoint snap, intersection snap,
  drawing a visible grid). Each is implemented as an additional
  branch inside snap_point() -- no other file needs to change to add
  them. The optional ``model`` parameter on snap_point() is reserved
  for those future modes (e.g. nearest-node lookup); it is unused in
  Phase A.

  Depends on: nothing (stdlib only)
=====================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple

__all__ = ["GridConfig", "snap_point"]


@dataclass
class GridConfig:
    """
    Snap configuration.

    Attributes
    ----------
    enabled : bool
        Master ON/OFF switch for all snapping. Default False so
        existing projects/behaviour are unaffected until the user
        opts in.
    spacing : float
        Grid spacing (model units, e.g. metres). Must be > 0 for
        snapping to have any effect. Default 1.0.
    visible : bool
        Phase B. Whether the grid should be drawn on the canvas.
        Inactive in Phase A (draw_grid() early-returns).
    snap_to_node : bool
        Phase B. Snap to the nearest existing node instead of/before
        the grid. Inactive in Phase A.
    snap_to_midpoint : bool
        Phase B. Snap to element midpoints. Inactive in Phase A.
    snap_to_intersection : bool
        Phase B. Snap to element/element intersections. Inactive in
        Phase A.
    """

    enabled: bool = False
    spacing: float = 1.0
    visible: bool = False
    snap_to_node: bool = False
    snap_to_midpoint: bool = False
    snap_to_intersection: bool = False


def snap_point(
    x: float, y: float, config: GridConfig, model: Optional[Any] = None
) -> Tuple[float, float]:
    """
    Apply snapping to a raw (x, y) coordinate pair.

    Pure function: no model mutation, no side effects. Returns
    ``(x, y)`` unchanged when ``config.enabled`` is False or
    ``config.spacing`` is not positive.

    Parameters
    ----------
    x, y : float
        Raw coordinates (e.g. straight from a matplotlib click
        event).
    config : GridConfig
        The active snap configuration.
    model : optional
        Reserved for Phase B snap modes (snap-to-node, snap-to-
        midpoint, snap-to-intersection) that need to inspect model
        geometry. Unused in Phase A.

    Returns
    -------
    (float, float)
        The snapped coordinate pair.
    """
    if not config.enabled or config.spacing <= 0:
        return x, y

    # Phase B branches (snap_to_node / snap_to_midpoint /
    # snap_to_intersection) would be inserted here, ahead of the
    # plain grid snap, so a more specific snap target wins when
    # active. None are active in Phase A.

    spacing = config.spacing
    sx = round(x / spacing) * spacing
    sy = round(y / spacing) * spacing

    # Kill floating-point noise (e.g. non-grid-multiple spacings like
    # 0.333 can otherwise yield 0.9999999999 instead of 1.0).
    sx = round(sx, 10)
    sy = round(sy, 10)

    return sx, sy
