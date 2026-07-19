"""
=====================================================================
  core/sections.py

  Cross-section property definitions for truss elements.

  Like materials.py, this module has NO dependencies on any other
  TrussTry package. model.py depends on it, not the other way round.
=====================================================================
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    """
    A cross-section, described by the properties a truss (axial-only)
    solver needs. `moment_of_inertia` is carried along for later
    (e.g. buckling checks, frame elements) but is not used by the
    axial truss solver.

    Attributes
    ----------
    name : str
        Display name, e.g. "W8x10" or "Custom 0.01 m^2".
    area : float
        Cross-sectional area (m^2). Must be positive.
    moment_of_inertia : float, optional
        Second moment of area (m^4). 0.0 means "unspecified".
    """

    name: str
    area: float
    moment_of_inertia: float = 0.0

    def __post_init__(self):
        if self.area <= 0.0:
            raise ValueError(
                f"Section {self.name!r} must have a positive area "
                f"(got {self.area!r})."
            )


# A small built-in library of common sections, keyed by name.
SECTION_LIBRARY: dict[str, Section] = {
    "Custom 0.01 m^2": Section(name="Custom 0.01 m^2", area=0.01),
    "W8x10": Section(name="W8x10", area=1.898e-3, moment_of_inertia=8.09e-6),
    "L3x3x1/4": Section(name="L3x3x1/4", area=9.03e-4, moment_of_inertia=7.36e-7),
    "HSS4x4x1/4": Section(name="HSS4x4x1/4", area=1.194e-3, moment_of_inertia=2.94e-6),
}

DEFAULT_SECTION = SECTION_LIBRARY["Custom 0.01 m^2"]


def get_section(name: str) -> Section:
    """Look up a built-in section by name.

    Raises KeyError with a helpful message if the name isn't found,
    rather than a bare KeyError.
    """
    try:
        return SECTION_LIBRARY[name]
    except KeyError:
        known = ", ".join(sorted(SECTION_LIBRARY))
        raise KeyError(
            f"Unknown section {name!r}. Known sections: {known}"
        ) from None
