"""
TrussTry / gui
==============
PySide6 front-end.

Dependency rule
---------------
    core  <---  analysis  <---  gui
    core  <---  visualization <---  gui

This package may import from core, analysis, and visualization.
It must NOT be imported by any of those packages.

Public surface
--------------
    from gui.main_window import MainWindow
"""

from gui.main_window import MainWindow  # noqa: F401
