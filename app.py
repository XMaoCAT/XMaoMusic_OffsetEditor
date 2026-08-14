from __future__ import annotations

import sys
from pathlib import Path

LOCAL_DEPS_DIR = Path(__file__).resolve().parent / "_deps"
if LOCAL_DEPS_DIR.exists():
    sys.path.insert(0, str(LOCAL_DEPS_DIR))


def main() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    from desktop_app import MainWindow

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("XMaoMusic OffsetEditor")
    app.setOrganizationName("XMaoCAT")

    preferred = [
        "PingFang SC",
        ".AppleSystemUIFont",
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "Segoe UI",
        "Noto Sans CJK SC",
    ]
    available = set(QFontDatabase.families())
    family = next((name for name in preferred if name in available), app.font().family())
    app.setFont(QFont(family, 10))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
