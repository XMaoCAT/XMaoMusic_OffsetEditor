from __future__ import annotations

import faulthandler
import logging
import sys
import traceback
from pathlib import Path

LOCAL_DEPS_DIR = Path(__file__).resolve().parent / "_deps"
if LOCAL_DEPS_DIR.exists():
    sys.path.insert(0, str(LOCAL_DEPS_DIR))


def diagnostics_root() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "XMaoMusic OffsetEditor"
    return Path.home() / "AppData" / "Local" / "XMaoMusic OffsetEditor" / "Logs"


def configure_diagnostics() -> tuple[logging.Logger, object]:
    log_root = diagnostics_root()
    log_root.mkdir(parents=True, exist_ok=True)
    log_path = log_root / "application.log"
    logger = logging.getLogger("xmaomusic")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    fault_stream = log_path.open("a", encoding="utf-8")
    faulthandler.enable(fault_stream, all_threads=True)

    def report_unhandled(exc_type, exc_value, exc_traceback) -> None:
        logger.critical(
            "Unhandled Python exception\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
        )

    sys.excepthook = report_unhandled
    logger.info("Application starting; frozen=%s platform=%s", getattr(sys, "frozen", False), sys.platform)
    return logger, fault_stream


def main() -> int:
    logger, fault_stream = configure_diagnostics()
    exit_code = 1
    q_install = None
    try:
        from PySide6.QtCore import Qt, qInstallMessageHandler
        from PySide6.QtGui import QFont, QFontDatabase
        from PySide6.QtWidgets import QApplication

        from desktop_app import MainWindow

        def qt_message_handler(_message_type, _context, message: str) -> None:
            logger.warning("Qt: %s", message)

        q_install = qInstallMessageHandler
        q_install(qt_message_handler)
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
        app.aboutToQuit.connect(window.bridge.shutdown)
        window.show()
        exit_code = app.exec()
        window.bridge.shutdown()
        logger.info("Application stopped with exit code %s", exit_code)
        return exit_code
    except BaseException:  # noqa: BLE001
        logger.critical("Fatal application error\n%s", traceback.format_exc())
        return exit_code
    finally:
        if q_install is not None:
            q_install(None)
        fault_stream.flush()
        fault_stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
