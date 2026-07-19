"""
=====================================================================
  core/materials.py

  Material property definitions for truss elements.

  This module has NO dependencies on any other TrussTry package. It
  sits at the bottom of the dependency graph: model.py depends on it,
  everything else depends on model.py.
=====================================================================
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    """
    A linear-elastic material.

    Attributes
    ----------
    name : str
        Display name, e.g. "Steel A36".
    E : float
        Young's modulus (Pa).
    yield_stress : float, optional
        Yield stress (Pa). Used later for capacity checks; not
        required by the solver itself. 0.0 means "unspecified".
    density : float, optional
        Mass density (kg/m^3). Used later for self-weight loads.
        0.0 means "unspecified".
    """

    name: str
    E: float
    yield_stress: float = 0.0
    density: float = 0.0

    def __post_init__(self):
        if self.E <= 0.0:
            raise ValueError(
                f"Material {self.name!r} must have a positive Young's "
                f"modulus (got {self.E!r})."
            )


# A small built-in library of common engineering materials, keyed by
# name. The GUI's material picker (later phase) reads from this dict
# directly; users may also construct a custom Material on the fly.
MATERIAL_LIBRARY: dict[str, Material] = {
    "Steel A36": Material(name="Steel A36", E=200e9, yield_stress=250e6, density=7850.0),
    "Steel A992": Material(name="Steel A992", E=200e9, yield_stress=345e6, density=7850.0),
    "Aluminum 6061-T6": Material(name="Aluminum 6061-T6", E=68.9e9, yield_stress=276e6, density=2700.0),
    "Titanium Ti-6Al-4V": Material(name="Titanium Ti-6Al-4V", E=113.8e9, yield_stress=880e6, density=4430.0),
}

DEFAULT_MATERIAL = MATERIAL_LIBRARY["Steel A36"]


def get_material(name: str) -> Material:
    """Look up a built-in material by name.

    Raises KeyError with a helpful message if the name isn't found,
    rather than a bare KeyError.
    """
    try:
        return MATERIAL_LIBRARY[name]
    except KeyError:
        known = ", ".join(sorted(MATERIAL_LIBRARY))
        raise KeyError(
            f"Unknown material {name!r}. Known materials: {known}"
        ) from None
