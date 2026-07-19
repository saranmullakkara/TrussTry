"""
=====================================================================
  main.py  --  TrussTry application entry point
=====================================================================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PySide6.QtCore import Qt, QTimer

from gui.main_window import MainWindow


def _get_icon() -> QIcon:
    icon_path = Path(__file__).parent / "assets" / "icon.ico"
    if icon_path.exists():
        return QIcon(str(icon_path))
    return QIcon()


def _make_splash(icon: QIcon) -> QSplashScreen:
    W, H = 480, 280
    pix = QPixmap(W, H)
    pix.fill(QColor("#1a2e4a"))

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    if not icon.isNull():
        icon_pix = icon.pixmap(96, 96)
        painter.drawPixmap((W - 96) // 2, 40, icon_pix)

    font = QFont("Segoe UI", 28, QFont.Bold)
    painter.setFont(font)
    painter.setPen(QColor("#4FC3F7"))
    painter.drawText(0, 155, W, 40, Qt.AlignHCenter, "TrussTry")

    font2 = QFont("Segoe UI", 11)
    painter.setFont(font2)
    painter.setPen(QColor("#90CAF9"))
    painter.drawText(0, 200, W, 30, Qt.AlignHCenter, "2D Truss Finite-Element Analysis")

    font3 = QFont("Segoe UI", 9)
    painter.setFont(font3)
    painter.setPen(QColor("#546E7A"))
    painter.drawText(0, 250, W, 25, Qt.AlignHCenter, "Loading...")

    painter.end()
    return QSplashScreen(pix, Qt.WindowStaysOnTopHint)


def main() -> None:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("TrussTry")
    app.setApplicationDisplayName("TrussTry")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("TrussTry")
    app.setStyle("Fusion")

    icon = _get_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    splash = _make_splash(icon)
    splash.show()
    app.processEvents()

    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)

    if "--example" in sys.argv:
        window._model.load_example_truss()

    def _launch():
        window.show()
        splash.finish(window)

    QTimer.singleShot(1500, _launch)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
