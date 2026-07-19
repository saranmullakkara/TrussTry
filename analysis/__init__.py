"""
TrussTry / analysis
===================
Concrete finite-element analysis implementations.

Dependency rule
---------------
    core  <---  analysis  <---  gui / visualization

This package may import from `core` freely. It must NOT import from
`gui`, `visualization`, or any other package at the same level --
those layers sit above it in the dependency graph and will import
from here instead.

Public surface
--------------
    from analysis.truss2d import TrussSolver2D
    from analysis.load_cases import LoadCase, LoadCaseSet
    from analysis.reactions import reaction_summary
    from analysis.postprocessing import PostProcessor
"""

from analysis.truss2d import TrussSolver2D  # noqa: F401
