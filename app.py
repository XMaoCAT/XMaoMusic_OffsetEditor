from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

LOCAL_DEPS_DIR = Path(__file__).resolve().parent / "_deps"
if LOCAL_DEPS_DIR.exists():
    sys.path.insert(0, str(LOCAL_DEPS_DIR))


def _bootstrap_ffmpeg_path() -> Optional[str]:
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
    except Exception:  # noqa: BLE001
        return None

    ffmpeg_exe = get_ffmpeg_exe()
    ffmpeg_dir = str(Path(ffmpeg_exe).parent)
    existing_path = os.environ.get("PATH", "")
    path_parts = existing_path.split(os.pathsep) if existing_path else []
    if ffmpeg_dir not in path_parts:
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + existing_path
    os.environ.setdefault("FFMPEG_BINARY", ffmpeg_exe)
    return ffmpeg_exe


_BUNDLED_FFMPEG_EXE = _bootstrap_ffmpeg_path()
warnings.filterwarnings(
    "ignore",
    message="Couldn't find ffmpeg or avconv - defaulting to ffmpeg, but may not work",
    category=RuntimeWarning,
    module="pydub.utils",
)
warnings.filterwarnings(
    "ignore",
    message="Couldn't find ffprobe or avprobe - defaulting to ffprobe, but may not work",
    category=RuntimeWarning,
    module="pydub.utils",
)

from pydub import AudioSegment
import pydub.audio_segment as pydub_audio_segment
from PySide6.QtCore import QObject, QEvent, QPoint, Qt, QThread, Signal
from PySide6.QtGui import QColor, QDoubleValidator, QFont, QFontDatabase, QIntValidator
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsBlurEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

SUPPORTED_FORMATS = ["mp3", "wav", "flac", "ogg", "m4a", "aac", "wma", "aiff", "opus"]
SUPPORTED_EXTENSIONS = {f".{item}" for item in SUPPORTED_FORMATS}
INVALID_FILENAME_CHARS = r'[<>:"/\\|?*]'
_FFMPEG_READY: Optional[bool] = None


@dataclass
class ExportOptions:
    name: str
    convert: bool
    fmt: str


@dataclass
class AudioParameterSettings:
    sample_rate: int
    channels: int
    bit_depth: int
    bitrate_kbps: int


@dataclass
class AudioFileDetails:
    source_format: str
    duration_sec: float
    sample_rate: int
    channels: int
    bit_depth: int
    bitrate_kbps: int


@dataclass
class ExportJob:
    input_path: Path
    output_path: Path
    target_fmt: str
    action: str
    action_seconds: float
    params: AudioParameterSettings


def _safe_mediainfo_json(filepath, read_ahead_limit=-1):
    original = _safe_mediainfo_json._original  # type: ignore[attr-defined]
    try:
        return original(filepath, read_ahead_limit=read_ahead_limit)
    except (FileNotFoundError, OSError) as exc:
        winerror = getattr(exc, "winerror", None)
        if isinstance(exc, FileNotFoundError) or winerror == 2:
            return {}
        raise


_safe_mediainfo_json._original = pydub_audio_segment.mediainfo_json  # type: ignore[attr-defined]
pydub_audio_segment.mediainfo_json = _safe_mediainfo_json


class IOSDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None, title: str = "") -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)

        self.card = QFrame()
        self.card.setObjectName("dialogCard")
        root.addWidget(self.card)

        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(24, 20, 24, 20)
        self.card_layout.setSpacing(14)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("dialogTitle")
        self.card_layout.addWidget(self.title_label)


class MessageDialog(IOSDialog):
    def __init__(
        self,
        parent: Optional[QWidget],
        title: str,
        message: str,
        ok_text: str = "确定",
        cancel_text: Optional[str] = None,
    ) -> None:
        super().__init__(parent, title)
        self.result_value = False

        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setObjectName("dialogMessage")
        self.card_layout.addWidget(self.message_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.card_layout.addLayout(btn_row)

        if cancel_text:
            cancel_btn = QPushButton(cancel_text)
            cancel_btn.setObjectName("secondaryButton")
            cancel_btn.clicked.connect(self.reject)
            btn_row.addWidget(cancel_btn)

        ok_btn = QPushButton(ok_text)
        ok_btn.setObjectName("primaryButton")
        ok_btn.clicked.connect(self._accept_value)
        btn_row.addWidget(ok_btn)

    def _accept_value(self) -> None:
        self.result_value = True
        self.accept()


class FileBrowserDialog(IOSDialog):
    def __init__(self, parent: Optional[QWidget], start_dir: Path) -> None:
        super().__init__(parent, "选择音频文件")
        self.current_dir = start_dir if start_dir.exists() else Path.home()
        self.selected_file: Optional[Path] = None

        self.path_edit = QLineEdit(str(self.current_dir))
        self.path_edit.setObjectName("pathInput")
        self.path_edit.returnPressed.connect(self._jump_path)
        self.card_layout.addWidget(self.path_edit)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)

        self.up_btn = QPushButton("上一级")
        self.up_btn.setObjectName("secondaryButton")
        self.up_btn.clicked.connect(self._go_up)
        nav_row.addWidget(self.up_btn)

        self.home_btn = QPushButton("主目录")
        self.home_btn.setObjectName("secondaryButton")
        self.home_btn.clicked.connect(self._go_home)
        nav_row.addWidget(self.home_btn)

        self.enter_btn = QPushButton("进入路径")
        self.enter_btn.setObjectName("secondaryButton")
        self.enter_btn.clicked.connect(self._jump_path)
        nav_row.addWidget(self.enter_btn)

        self.card_layout.addLayout(nav_row)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("fileList")
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.card_layout.addWidget(self.list_widget)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self.reject)
        action_row.addWidget(cancel_btn)

        self.select_btn = QPushButton("选择")
        self.select_btn.setObjectName("primaryButton")
        self.select_btn.setEnabled(False)
        self.select_btn.clicked.connect(self._submit)
        action_row.addWidget(self.select_btn)

        self.card_layout.addLayout(action_row)

        self._load_entries()

    def _load_entries(self) -> None:
        self.selected_file = None
        self.select_btn.setEnabled(False)
        self.list_widget.clear()
        self.path_edit.setText(str(self.current_dir))

        try:
            entries = sorted(self.current_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            MessageDialog(self, "无法访问", "没有权限访问该目录。", ok_text="确定").exec()
            self._go_up()
            return

        for entry in entries:
            if entry.is_dir():
                item = QListWidgetItem(f"[目录] {entry.name}")
                item.setForeground(QColor("#0A84FF"))
                item.setData(Qt.UserRole, str(entry))
                item.setData(Qt.UserRole + 1, "dir")
                self.list_widget.addItem(item)
                continue

            if entry.suffix.lower() in SUPPORTED_EXTENSIONS:
                item = QListWidgetItem(entry.name)
                item.setData(Qt.UserRole, str(entry))
                item.setData(Qt.UserRole + 1, "file")
                self.list_widget.addItem(item)

    def _jump_path(self) -> None:
        target = Path(self.path_edit.text().strip())
        if target.exists() and target.is_dir():
            self.current_dir = target
            self._load_entries()
            return

        MessageDialog(self, "路径无效", "请输入可访问的目录路径。", ok_text="确定").exec()

    def _go_up(self) -> None:
        parent = self.current_dir.parent
        if parent == self.current_dir:
            return
        self.current_dir = parent
        self._load_entries()

    def _go_home(self) -> None:
        self.current_dir = Path.home()
        self._load_entries()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        item_type = item.data(Qt.UserRole + 1)
        item_path = Path(item.data(Qt.UserRole))
        if item_type == "file":
            self.selected_file = item_path
            self.select_btn.setEnabled(True)
        else:
            self.selected_file = None
            self.select_btn.setEnabled(False)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        item_type = item.data(Qt.UserRole + 1)
        item_path = Path(item.data(Qt.UserRole))
        if item_type == "dir":
            self.current_dir = item_path
            self._load_entries()
        else:
            self.selected_file = item_path
            self._submit()

    def _submit(self) -> None:
        if not self.selected_file:
            return
        self.accept()


class ExportDialog(IOSDialog):
    def __init__(self, parent: Optional[QWidget], default_name: str, source_fmt: str) -> None:
        super().__init__(parent, "导出设置")

        self.name_edit = QLineEdit(default_name)
        self.name_edit.setObjectName("pathInput")
        self.name_edit.setPlaceholderText("导出文件名（不含后缀）")
        self.card_layout.addWidget(QLabel("文件名"))
        self.card_layout.addWidget(self.name_edit)

        self.convert_check = QCheckBox("转换格式")
        self.convert_check.setObjectName("switch")
        self.convert_check.stateChanged.connect(self._toggle_convert)
        self.card_layout.addWidget(self.convert_check)

        self.format_combo = QComboBox()
        self.format_combo.addItems(SUPPORTED_FORMATS)
        source_index = max(0, self.format_combo.findText(source_fmt))
        self.format_combo.setCurrentIndex(source_index)
        self.format_combo.setEnabled(False)
        self.card_layout.addWidget(QLabel("目标格式"))
        self.card_layout.addWidget(self.format_combo)

        hint = QLabel(f"不转换时将保持原格式：{source_fmt}")
        hint.setObjectName("hintLabel")
        self.card_layout.addWidget(hint)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self.reject)
        action_row.addWidget(cancel_btn)

        export_btn = QPushButton("开始导出")
        export_btn.setObjectName("primaryButton")
        export_btn.clicked.connect(self.accept)
        action_row.addWidget(export_btn)

        self.card_layout.addLayout(action_row)

    def _toggle_convert(self) -> None:
        self.format_combo.setEnabled(self.convert_check.isChecked())

    def get_options(self) -> ExportOptions:
        raw_name = self.name_edit.text().strip()
        clean_name = sanitize_filename(raw_name)
        return ExportOptions(
            name=clean_name,
            convert=self.convert_check.isChecked(),
            fmt=self.format_combo.currentText().lower(),
        )


class ExportProgressDialog(IOSDialog):
    def __init__(self, parent: Optional[QWidget]) -> None:
        super().__init__(parent, "导出处理中")
        self._allow_close = False
        self.setMinimumWidth(520)

        self.status_label = QLabel("准备开始...")
        self.status_label.setObjectName("dialogMessage")
        self.card_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("exportProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.card_layout.addWidget(self.progress_bar)

        self.percent_label = QLabel("0%")
        self.percent_label.setObjectName("hintLabel")
        self.percent_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.card_layout.addWidget(self.percent_label)

    def reject(self) -> None:
        if self._allow_close:
            super().reject()

    def allow_close(self) -> None:
        self._allow_close = True

    def update_progress(self, value: int, message: str) -> None:
        clamped = max(0, min(100, value))
        self.progress_bar.setValue(clamped)
        self.status_label.setText(message)
        self.percent_label.setText(f"{clamped}%")


class ExportWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, job: ExportJob) -> None:
        super().__init__()
        self.job = job

    def run(self) -> None:
        try:
            output_path = execute_export_job(self.job, self.progress.emit)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.finished.emit(str(output_path))


class DropZone(QFrame):
    file_dropped = Signal(str)
    browse_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("dropZone")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        title = QLabel("拖拽音频到这里")
        title.setObjectName("dropTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("或点击这里浏览文件夹选择音频")
        subtitle.setObjectName("dropSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.browse_requested.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if has_supported_audio(event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                self.file_dropped.emit(str(path))
                event.acceptProposedAction()
                return
        event.ignore()


class SecondsInput(QWidget):
    def __init__(
        self,
        value: float = 0.50,
        min_value: float = 0.00,
        max_value: float = 9999.99,
        step: float = 0.01,
    ) -> None:
        super().__init__()
        self._min_value = min_value
        self._max_value = max_value
        self._step = step

        self.setObjectName("secondsInput")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        self.minus_btn = QPushButton("-")
        self.minus_btn.setObjectName("stepButton")
        self.minus_btn.setFixedWidth(30)
        self.minus_btn.clicked.connect(lambda: self._step_value(-1))
        layout.addWidget(self.minus_btn)

        self.line_edit = QLineEdit()
        self.line_edit.setObjectName("secondsField")
        self.line_edit.setAlignment(Qt.AlignCenter)
        self.line_edit.setPlaceholderText("0.00")
        validator = QDoubleValidator(self._min_value, self._max_value, 2, self)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.line_edit.setValidator(validator)
        self.line_edit.editingFinished.connect(self._normalize_text)
        layout.addWidget(self.line_edit)

        self.unit_label = QLabel("s")
        self.unit_label.setObjectName("secondsUnit")
        layout.addWidget(self.unit_label)

        self.plus_btn = QPushButton("+")
        self.plus_btn.setObjectName("stepButton")
        self.plus_btn.setFixedWidth(30)
        self.plus_btn.clicked.connect(lambda: self._step_value(1))
        layout.addWidget(self.plus_btn)

        self.setValue(value)

    def _clamp(self, value: float) -> float:
        return max(self._min_value, min(self._max_value, value))

    def _parse(self) -> float:
        text = self.line_edit.text().strip().replace(",", ".")
        if not text:
            return self._min_value
        try:
            value = float(text)
        except ValueError:
            return self._min_value
        return self._clamp(value)

    def _normalize_text(self) -> None:
        self.setValue(self._parse())

    def _step_value(self, direction: int) -> None:
        value = self.value() + direction * self._step
        self.setValue(value)

    def value(self) -> float:
        return round(self._parse(), 2)

    def setValue(self, value: float) -> None:  # noqa: N802
        clamped = round(self._clamp(value), 2)
        self.line_edit.setText(f"{clamped:.2f}")


class TitleBar(QFrame):
    minimize_requested = Signal()
    maximize_restore_requested = Signal()
    close_requested = Signal()

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("titleBar")
        self._drag_global_pos: Optional[QPoint] = None
        self._drag_window_pos: Optional[QPoint] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 10, 8)
        layout.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("titleBarLabel")
        layout.addWidget(self.title_label)
        layout.addStretch(1)

        self.min_btn = QPushButton("-")
        self.min_btn.setObjectName("windowControl")
        self.min_btn.setToolTip("最小化")
        self.min_btn.clicked.connect(self.minimize_requested.emit)
        layout.addWidget(self.min_btn)

        self.max_btn = QPushButton("□")
        self.max_btn.setObjectName("windowControl")
        self.max_btn.setToolTip("最大化/还原")
        self.max_btn.clicked.connect(self.maximize_restore_requested.emit)
        layout.addWidget(self.max_btn)

        self.close_btn = QPushButton("x")
        self.close_btn.setObjectName("windowClose")
        self.close_btn.setToolTip("关闭")
        self.close_btn.clicked.connect(self.close_requested.emit)
        layout.addWidget(self.close_btn)

    def set_maximized(self, maximized: bool) -> None:
        self.max_btn.setText("❐" if maximized else "□")

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.maximize_restore_requested.emit()
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            window = self.window()
            if isinstance(window, QMainWindow) and not window.isMaximized():
                self._drag_global_pos = event.globalPosition().toPoint()
                self._drag_window_pos = window.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if (
            self._drag_global_pos is not None
            and self._drag_window_pos is not None
            and event.buttons() & Qt.LeftButton
        ):
            window = self.window()
            if isinstance(window, QMainWindow) and not window.isMaximized():
                delta = event.globalPosition().toPoint() - self._drag_global_pos
                window.move(self._drag_window_pos + delta)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_global_pos = None
        self._drag_window_pos = None
        super().mouseReleaseEvent(event)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.audio_path: Optional[Path] = None
        self.audio_details: Optional[AudioFileDetails] = None
        self.selected_action: Optional[str] = None
        self.export_thread: Optional[QThread] = None
        self.export_worker: Optional[ExportWorker] = None
        self.progress_dialog: Optional[ExportProgressDialog] = None
        self._blur_effect = QGraphicsBlurEffect(self)
        self._blur_effect.setBlurRadius(16)

        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("音频起始编辑工具")
        self.resize(860, 620)

        shell = QWidget()
        shell.setObjectName("windowShell")
        self.setCentralWidget(shell)

        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(8, 8, 8, 8)
        shell_layout.setSpacing(0)

        window_card = QFrame()
        window_card.setObjectName("windowCard")
        shell_layout.addWidget(window_card)

        card_layout = QVBoxLayout(window_card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        self.title_bar = TitleBar("Debug By XMaoCAT")
        self.title_bar.minimize_requested.connect(self.showMinimized)
        self.title_bar.maximize_restore_requested.connect(self.toggle_max_restore)
        self.title_bar.close_requested.connect(self.close)
        card_layout.addWidget(self.title_bar)

        container = QWidget()
        container.setObjectName("appRoot")
        card_layout.addWidget(container, 1)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 22, 28, 28)
        layout.setSpacing(16)

        title = QLabel("音频起始音编辑工具")
        title.setObjectName("mainTitle")
        layout.addWidget(title)

        self.drop_zone = DropZone()
        self.drop_zone.file_dropped.connect(self.set_audio)
        self.drop_zone.browse_requested.connect(self.open_browser)
        layout.addWidget(self.drop_zone)

        self.file_label = QLabel("当前文件：未选择")
        self.file_label.setObjectName("fileLabel")
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        details_card = QFrame()
        details_card.setObjectName("card")
        details_layout = QGridLayout(details_card)
        details_layout.setContentsMargins(18, 18, 18, 18)
        details_layout.setHorizontalSpacing(12)
        details_layout.setVerticalSpacing(10)

        details_title = QLabel("详细参数（可修改）")
        details_title.setObjectName("sectionTitle")
        details_layout.addWidget(details_title, 0, 0, 1, 4)

        details_layout.addWidget(self._make_form_label("源格式"), 1, 0)
        self.format_value_label = QLabel("-")
        self.format_value_label.setObjectName("metaValue")
        details_layout.addWidget(self.format_value_label, 1, 1)

        details_layout.addWidget(self._make_form_label("总时长"), 1, 2)
        self.duration_value_label = QLabel("-")
        self.duration_value_label.setObjectName("metaValue")
        details_layout.addWidget(self.duration_value_label, 1, 3)

        details_layout.addWidget(self._make_form_label("采样率 (Hz)"), 2, 0)
        self.sample_rate_edit = QLineEdit("44100")
        self.sample_rate_edit.setObjectName("paramInput")
        self.sample_rate_edit.setValidator(QIntValidator(8000, 384000, self))
        details_layout.addWidget(self.sample_rate_edit, 2, 1)

        details_layout.addWidget(self._make_form_label("声道"), 2, 2)
        self.channels_combo = QComboBox()
        self.channels_combo.setObjectName("paramCombo")
        self.channels_combo.addItems(["1", "2", "6", "8"])
        details_layout.addWidget(self.channels_combo, 2, 3)

        details_layout.addWidget(self._make_form_label("位深 (bit)"), 3, 0)
        self.bit_depth_combo = QComboBox()
        self.bit_depth_combo.setObjectName("paramCombo")
        self.bit_depth_combo.addItems(["8", "16", "24", "32"])
        details_layout.addWidget(self.bit_depth_combo, 3, 1)

        details_layout.addWidget(self._make_form_label("比特率 (kbps)"), 3, 2)
        self.bitrate_edit = QLineEdit("320")
        self.bitrate_edit.setObjectName("paramInput")
        self.bitrate_edit.setValidator(QIntValidator(16, 5000, self))
        details_layout.addWidget(self.bitrate_edit, 3, 3)
        layout.addWidget(details_card)

        mode_card = QFrame()
        mode_card.setObjectName("card")
        mode_layout = QVBoxLayout(mode_card)
        mode_layout.setContentsMargins(18, 18, 18, 18)
        mode_layout.setSpacing(12)

        mode_layout.addWidget(QLabel("起始操作"))

        trim_row = QHBoxLayout()
        trim_row.setSpacing(10)

        trim_label = QLabel("删除开头秒数")
        trim_label.setObjectName("formLabel")
        trim_row.addWidget(trim_label)

        self.trim_duration_spin = SecondsInput(value=0.50)
        trim_row.addWidget(self.trim_duration_spin)

        self.trim_btn = QPushButton("删除开头")
        self.trim_btn.setObjectName("actionButton")
        self.trim_btn.setCheckable(True)
        self.trim_btn.clicked.connect(self._select_trim_action)
        trim_row.addWidget(self.trim_btn)
        mode_layout.addLayout(trim_row)

        prepend_row = QHBoxLayout()
        prepend_row.setSpacing(10)

        prepend_label = QLabel("添加开头秒数")
        prepend_label.setObjectName("formLabel")
        prepend_row.addWidget(prepend_label)

        self.prepend_duration_spin = SecondsInput(value=0.50)
        prepend_row.addWidget(self.prepend_duration_spin)

        self.prepend_btn = QPushButton("添加开头")
        self.prepend_btn.setObjectName("actionButton")
        self.prepend_btn.setCheckable(True)
        self.prepend_btn.clicked.connect(self._select_prepend_action)
        prepend_row.addWidget(self.prepend_btn)
        mode_layout.addLayout(prepend_row)
        layout.addWidget(mode_card)

        self.export_btn = QPushButton("导出")
        self.export_btn.setObjectName("primaryButton")
        self.export_btn.setMinimumHeight(52)
        self.export_btn.clicked.connect(self.export_audio)
        layout.addWidget(self.export_btn)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)

        self.credit_label = QLabel("OpenAI GPT-5 (Codex)  |  XMaoCAT")
        self.credit_label.setObjectName("creditLabel")
        self.credit_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.credit_label)

        if not has_ffmpeg():
            self.status_label.setText("提示：未检测到 ffmpeg，MP3/M4A/AAC 等格式可能无法正常读写。")

    def toggle_max_restore(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self.title_bar.set_maximized(self.isMaximized())

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and hasattr(self, "title_bar"):
            self.title_bar.set_maximized(self.isMaximized())

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.export_thread and self.export_thread.isRunning():
            MessageDialog(
                self,
                "导出进行中",
                "当前正在导出，请等待任务完成后再关闭程序。",
                ok_text="确定",
            ).exec()
            event.ignore()
            return
        super().closeEvent(event)

    def _make_form_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("formLabel")
        return label

    def _set_combo_value(self, combo: QComboBox, value: int) -> None:
        text = str(value)
        if combo.findText(text) < 0:
            combo.addItem(text)
        combo.setCurrentText(text)

    def _set_background_blur(self, enabled: bool) -> None:
        target = self.centralWidget()
        if target is None:
            return
        target.setGraphicsEffect(self._blur_effect if enabled else None)

    def _collect_parameter_settings(self) -> AudioParameterSettings:
        sample_rate_text = self.sample_rate_edit.text().strip()
        bitrate_text = self.bitrate_edit.text().strip()
        channels_text = self.channels_combo.currentText().strip()
        bit_depth_text = self.bit_depth_combo.currentText().strip()

        if not sample_rate_text or not bitrate_text or not channels_text or not bit_depth_text:
            raise ValueError("请先完善详细参数（采样率、声道、位深、比特率）。")

        sample_rate = int(sample_rate_text)
        channels = int(channels_text)
        bit_depth = int(bit_depth_text)
        bitrate_kbps = int(bitrate_text)

        if sample_rate < 8000 or sample_rate > 384000:
            raise ValueError("采样率必须在 8000 到 384000 之间。")
        if channels < 1 or channels > 8:
            raise ValueError("声道数必须在 1 到 8 之间。")
        if bit_depth not in {8, 16, 24, 32}:
            raise ValueError("位深只支持 8 / 16 / 24 / 32。")
        if bitrate_kbps < 16 or bitrate_kbps > 5000:
            raise ValueError("比特率必须在 16 到 5000 kbps 之间。")

        return AudioParameterSettings(
            sample_rate=sample_rate,
            channels=channels,
            bit_depth=bit_depth,
            bitrate_kbps=bitrate_kbps,
        )

    def _apply_audio_details_to_form(self, details: AudioFileDetails) -> None:
        self.format_value_label.setText(details.source_format.upper())
        self.duration_value_label.setText(f"{details.duration_sec:.2f} s")
        self.sample_rate_edit.setText(str(details.sample_rate))
        self._set_combo_value(self.channels_combo, details.channels)
        self._set_combo_value(self.bit_depth_combo, details.bit_depth)
        self.bitrate_edit.setText(str(details.bitrate_kbps))

    def open_browser(self) -> None:
        start_dir = self.audio_path.parent if self.audio_path else Path.home()
        dialog = FileBrowserDialog(self, start_dir)
        if dialog.exec() and dialog.selected_file:
            self.set_audio(str(dialog.selected_file))

    def set_audio(self, path_text: str) -> None:
        path = Path(path_text)
        if not path.exists() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            MessageDialog(self, "文件不支持", "请选择支持的音频文件。", ok_text="确定").exec()
            return

        try:
            details = extract_audio_file_details(path)
        except Exception as exc:  # noqa: BLE001
            MessageDialog(self, "读取失败", f"无法读取音频参数：{exc}", ok_text="确定").exec()
            return

        self.audio_path = path
        self.audio_details = details
        self.file_label.setText(f"当前文件：{path}")
        self._apply_audio_details_to_form(details)
        self.status_label.setText("音频已载入，详细参数已填充。")

    def _set_selected_action(self, action: str, seconds: float) -> None:
        self.selected_action = action
        self.trim_btn.setChecked(action == "trim")
        self.prepend_btn.setChecked(action == "prepend")
        action_text = "删除开头" if action == "trim" else "添加开头静音"
        self.status_label.setText(f"已选择：{action_text} {seconds:.2f} 秒。点击“导出”生效。")

    def _select_trim_action(self) -> None:
        seconds = self.trim_duration_spin.value()
        if seconds <= 0:
            MessageDialog(self, "参数错误", "删除秒数必须大于 0。", ok_text="确定").exec()
            self.trim_btn.setChecked(False)
            if self.selected_action == "trim":
                self.selected_action = None
            return
        self._set_selected_action("trim", seconds)

    def _select_prepend_action(self) -> None:
        seconds = self.prepend_duration_spin.value()
        if seconds <= 0:
            MessageDialog(self, "参数错误", "添加秒数必须大于 0。", ok_text="确定").exec()
            self.prepend_btn.setChecked(False)
            if self.selected_action == "prepend":
                self.selected_action = None
            return
        self._set_selected_action("prepend", seconds)

    def export_audio(self) -> None:
        if not self.audio_path:
            MessageDialog(self, "未选择文件", "请先拖拽或浏览选择音频文件。", ok_text="确定").exec()
            return
        if self.export_thread and self.export_thread.isRunning():
            return

        if self.selected_action is None:
            MessageDialog(
                self,
                "请选择操作",
                "请先点击“删除开头”或“添加开头”按钮，确认本次处理方式与秒数。",
                ok_text="确定",
            ).exec()
            return

        try:
            params = self._collect_parameter_settings()
        except ValueError as exc:
            MessageDialog(self, "参数错误", str(exc), ok_text="确定").exec()
            return

        source_fmt = self.audio_path.suffix.lower().lstrip(".")
        dialog = ExportDialog(self, f"{self.audio_path.stem}_edited", source_fmt)
        if not dialog.exec():
            return

        options = dialog.get_options()
        if not options.name:
            MessageDialog(self, "文件名无效", "请输入有效的导出文件名。", ok_text="确定").exec()
            return

        if options.convert:
            target_fmt = options.fmt
        else:
            target_fmt = self.audio_path.suffix.lower().lstrip(".")

        if target_fmt not in SUPPORTED_FORMATS:
            MessageDialog(self, "格式不支持", f"暂不支持导出格式：{target_fmt}", ok_text="确定").exec()
            return

        output_dir = Path.cwd() / "Output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = ensure_unique_path(output_dir / f"{options.name}.{target_fmt}")

        action_seconds = (
            self.trim_duration_spin.value()
            if self.selected_action == "trim"
            else self.prepend_duration_spin.value()
        )
        job = ExportJob(
            input_path=self.audio_path,
            output_path=output_path,
            target_fmt=target_fmt,
            action=self.selected_action,
            action_seconds=action_seconds,
            params=params,
        )
        self._start_export(job)

    def _start_export(self, job: ExportJob) -> None:
        self.export_btn.setEnabled(False)
        self.export_btn.setText("导出中...")
        self.status_label.setText("正在处理，请稍候...")

        self._set_background_blur(True)
        self.progress_dialog = ExportProgressDialog(self)
        self.progress_dialog.update_progress(0, "准备导出任务...")
        self.progress_dialog.show()
        self.progress_dialog.raise_()

        dialog_size = self.progress_dialog.sizeHint()
        center_point = self.frameGeometry().center()
        self.progress_dialog.move(
            center_point.x() - dialog_size.width() // 2,
            center_point.y() - dialog_size.height() // 2,
        )

        self.export_thread = QThread(self)
        self.export_worker = ExportWorker(job)
        self.export_worker.moveToThread(self.export_thread)

        self.export_thread.started.connect(self.export_worker.run)
        self.export_worker.progress.connect(self._on_export_progress)
        self.export_worker.finished.connect(self._on_export_finished)
        self.export_worker.failed.connect(self._on_export_failed)

        self.export_worker.finished.connect(self.export_thread.quit)
        self.export_worker.failed.connect(self.export_thread.quit)
        self.export_thread.finished.connect(self.export_worker.deleteLater)
        self.export_thread.finished.connect(self.export_thread.deleteLater)

        self.export_thread.start()

    def _on_export_progress(self, value: int, message: str) -> None:
        if self.progress_dialog:
            self.progress_dialog.update_progress(value, message)

    def _reset_export_runtime(self) -> None:
        self.export_btn.setEnabled(True)
        self.export_btn.setText("导出")
        self._set_background_blur(False)

        if self.progress_dialog:
            self.progress_dialog.allow_close()
            self.progress_dialog.close()
            self.progress_dialog = None

        self.export_thread = None
        self.export_worker = None

    def _on_export_finished(self, output_path_text: str) -> None:
        output_path = Path(output_path_text)
        self.status_label.setText(f"导出完成：{output_path.name}")
        self._reset_export_runtime()
        open_folder(output_path.parent)
        MessageDialog(
            self,
            "导出成功",
            f"已保存到：\n{output_path}",
            ok_text="确定",
        ).exec()

    def _on_export_failed(self, error_message: str) -> None:
        self.status_label.setText("导出失败。")
        self._reset_export_runtime()
        MessageDialog(self, "导出失败", error_message, ok_text="确定").exec()


def load_audio_segment(path: Path) -> AudioSegment:
    source_fmt = path.suffix.lower().lstrip(".") or None
    try:
        return AudioSegment.from_file(str(path), format=source_fmt)
    except (FileNotFoundError, OSError) as exc:
        winerror = getattr(exc, "winerror", None)
        if not (isinstance(exc, FileNotFoundError) or winerror == 2):
            raise

    # Some environments only have ffmpeg without ffprobe.
    # This fallback path avoids probe calls and still decodes correctly.
    return AudioSegment.from_file_using_temporary_files(str(path), format=source_fmt)


def default_bitrate_for_format(fmt: str) -> int:
    mapping = {
        "mp3": 320,
        "m4a": 256,
        "aac": 256,
        "ogg": 256,
        "opus": 192,
        "wma": 192,
        "wav": 1411,
        "flac": 1000,
        "aiff": 1411,
    }
    return mapping.get(fmt.lower(), 320)


def _probe_bitrate_kbps(path: Path) -> Optional[int]:
    info = pydub_audio_segment.mediainfo_json(str(path))
    if not isinstance(info, dict) or not info:
        return None

    bit_rate_raw = None
    format_info = info.get("format")
    if isinstance(format_info, dict):
        bit_rate_raw = format_info.get("bit_rate")

    if not bit_rate_raw:
        streams = info.get("streams", [])
        if isinstance(streams, list):
            for stream in streams:
                if isinstance(stream, dict) and stream.get("codec_type") == "audio":
                    bit_rate_raw = stream.get("bit_rate")
                    if bit_rate_raw:
                        break

    if not bit_rate_raw:
        return None

    try:
        return max(1, int(int(bit_rate_raw) / 1000))
    except (TypeError, ValueError):
        return None


def extract_audio_file_details(path: Path) -> AudioFileDetails:
    audio = load_audio_segment(path)
    source_fmt = path.suffix.lower().lstrip(".")
    duration_sec = len(audio) / 1000
    bit_depth = max(8, int(audio.sample_width) * 8)

    bitrate = _probe_bitrate_kbps(path)
    if bitrate is None:
        bitrate = default_bitrate_for_format(source_fmt)

    return AudioFileDetails(
        source_format=source_fmt or "unknown",
        duration_sec=duration_sec,
        sample_rate=int(audio.frame_rate),
        channels=int(audio.channels),
        bit_depth=bit_depth,
        bitrate_kbps=bitrate,
    )


def execute_export_job(job: ExportJob, progress_callback) -> Path:
    if not has_ffmpeg():
        raise ValueError("未找到可用的 ffmpeg，无法处理音频。")

    progress_callback(5, "正在读取音频...")
    audio = load_audio_segment(job.input_path)
    progress_callback(20, "已读取音频，准备编辑起始位置...")

    offset_ms = int(round(job.action_seconds * 1000))
    if job.action == "trim":
        if offset_ms <= 0:
            raise ValueError("删除秒数必须大于 0。")
        if offset_ms >= len(audio):
            raise ValueError("删除时长不能大于或等于音频总长度。")
        edited = audio[offset_ms:]
    elif job.action == "prepend":
        if offset_ms <= 0:
            raise ValueError("添加秒数必须大于 0。")
        silence = AudioSegment.silent(duration=offset_ms, frame_rate=audio.frame_rate)
        edited = silence + audio
    else:
        raise ValueError("未选择有效的起始编辑操作。")
    progress_callback(40, "起始位置编辑完成，应用详细参数中...")

    target_sample_width = max(1, min(4, int(job.params.bit_depth / 8)))
    edited = edited.set_frame_rate(job.params.sample_rate)
    edited = edited.set_channels(job.params.channels)
    edited = edited.set_sample_width(target_sample_width)
    progress_callback(55, "详细参数应用完成，准备编码导出...")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
        temp_wav = Path(temp_file.name)

    try:
        edited.export(str(temp_wav), format="wav")
        progress_callback(68, "正在编码导出，请稍候...")
        encode_with_ffmpeg_progress(
            temp_input=temp_wav,
            output_path=job.output_path,
            target_fmt=job.target_fmt,
            bitrate_kbps=job.params.bitrate_kbps,
            total_ms=max(1, len(edited)),
            progress_callback=progress_callback,
        )
    finally:
        if temp_wav.exists():
            temp_wav.unlink(missing_ok=True)

    progress_callback(100, "导出完成")
    return job.output_path


def encode_with_ffmpeg_progress(
    temp_input: Path,
    output_path: Path,
    target_fmt: str,
    bitrate_kbps: int,
    total_ms: int,
    progress_callback,
) -> None:
    ffmpeg_bin = AudioSegment.converter or "ffmpeg"
    command = [str(ffmpeg_bin), "-y", "-i", str(temp_input), "-vn"]

    if target_fmt in {"mp3", "m4a", "aac", "ogg", "opus", "wma"} and bitrate_kbps > 0:
        command.extend(["-b:a", f"{bitrate_kbps}k"])

    command.extend(["-progress", "pipe:1", "-nostats", str(output_path)])

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        bufsize=1,
    )

    logs = []
    last_progress = 68

    if process.stdout:
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue

            logs.append(line)
            if len(logs) > 40:
                logs.pop(0)

            if line.startswith("out_time_ms="):
                try:
                    out_time_ms = int(line.split("=", 1)[1]) // 1000
                except ValueError:
                    continue
                ratio = max(0.0, min(1.0, out_time_ms / max(1, total_ms)))
                mapped = 68 + int(ratio * 30)
                if mapped > last_progress:
                    last_progress = mapped
                    progress_callback(last_progress, "正在编码导出...")
            elif line == "progress=end":
                progress_callback(99, "正在写入输出文件...")

    return_code = process.wait()
    if return_code != 0:
        recent_logs = "\n".join(logs[-15:])
        raise RuntimeError(f"导出失败（ffmpeg 错误码 {return_code}）\n{recent_logs}")


def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 1

    while True:
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(INVALID_FILENAME_CHARS, "_", name)
    cleaned = cleaned.strip().strip(".")
    return cleaned


def has_supported_audio(urls) -> bool:
    for url in urls:
        if not url.isLocalFile():
            continue
        suffix = Path(url.toLocalFile()).suffix.lower()
        if suffix in SUPPORTED_EXTENSIONS:
            return True
    return False


def has_ffmpeg() -> bool:
    global _FFMPEG_READY
    if _FFMPEG_READY is not None:
        return _FFMPEG_READY

    from shutil import which

    system_ffmpeg = which("ffmpeg")
    if system_ffmpeg:
        AudioSegment.converter = system_ffmpeg
        _FFMPEG_READY = True
        return True

    if _BUNDLED_FFMPEG_EXE and Path(_BUNDLED_FFMPEG_EXE).exists():
        AudioSegment.converter = _BUNDLED_FFMPEG_EXE
        _FFMPEG_READY = True
        return True

    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        bundled_ffmpeg = get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        _FFMPEG_READY = False
        return False

    if bundled_ffmpeg and Path(bundled_ffmpeg).exists():
        AudioSegment.converter = bundled_ffmpeg
        _FFMPEG_READY = True
        return True

    _FFMPEG_READY = False
    return False


def open_folder(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def apply_best_font(app: QApplication) -> None:
    preferred_fonts = [
        "SF Pro Display",
        "PingFang SC",
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "Segoe UI",
        "Noto Sans CJK SC",
    ]
    available_fonts = set(QFontDatabase.families())

    chosen_font = None
    for family in preferred_fonts:
        if family in available_fonts:
            chosen_font = family
            break

    if chosen_font:
        font = QFont(chosen_font, 10)
    else:
        font = QFont(app.font())
        font.setPointSize(10)

    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)


def apply_styles(app: QApplication) -> None:
    app.setStyleSheet(
        """
        QWidget {
            color: #1D1D1F;
            font-size: 14px;
            background: transparent;
        }
        QMainWindow, #windowShell {
            background: transparent;
        }
        #windowCard {
            background: #F3F6FB;
            border: 1px solid #D3DAE7;
            border-radius: 26px;
        }
        #titleBar {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #F8FBFF, stop:1 #EDF3FF);
            border-top-left-radius: 26px;
            border-top-right-radius: 26px;
            border-bottom: 1px solid #D7DFEC;
            min-height: 42px;
        }
        #titleBarLabel {
            color: #4A5670;
            font-size: 13px;
            font-weight: 600;
        }
        #windowControl {
            background: #EEF2FA;
            border: 1px solid #CFD7E6;
            border-radius: 10px;
            min-width: 34px;
            max-width: 34px;
            min-height: 28px;
            max-height: 28px;
            color: #2A3347;
            font-weight: 700;
            padding: 0;
        }
        #windowControl:hover {
            background: #E1E9F8;
        }
        #windowControl:pressed {
            background: #D2DDF3;
        }
        #windowClose {
            background: #FFE8E8;
            border: 1px solid #F5B9B9;
            border-radius: 10px;
            min-width: 34px;
            max-width: 34px;
            min-height: 28px;
            max-height: 28px;
            color: #9D1F1F;
            font-weight: 700;
            padding: 0;
        }
        #windowClose:hover {
            background: #FFD8D8;
        }
        #windowClose:pressed {
            background: #FFC5C5;
        }
        #appRoot {
            background: transparent;
        }
        QLabel {
            background: transparent;
        }
        #mainTitle {
            font-size: 30px;
            font-weight: 700;
            color: #111111;
            background: transparent;
        }
        #mainSubtitle {
            color: #5E6574;
            font-size: 14px;
            background: transparent;
        }
        #dropZone {
            border: 2px dashed #8EB8FF;
            border-radius: 24px;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #F8FBFF, stop:1 #EEF4FF);
            min-height: 200px;
        }
        #dropTitle {
            font-size: 26px;
            font-weight: 600;
            background: transparent;
        }
        #dropSubtitle {
            color: #4B5568;
            font-size: 14px;
            background: transparent;
        }
        #card {
            background: white;
            border-radius: 20px;
        }
        #actionButton {
            border-radius: 15px;
            border: 1px solid #D4DAE5;
            background: #F9FAFC;
            padding: 10px 14px;
            font-weight: 500;
            min-width: 115px;
        }
        #actionButton:checked {
            background: #0A84FF;
            color: white;
            border: none;
        }
        #formLabel {
            color: #3F4A5C;
            min-width: 110px;
        }
        #sectionTitle {
            color: #1E2A42;
            font-size: 15px;
            font-weight: 600;
        }
        #metaValue {
            color: #53627D;
            font-weight: 600;
        }
        #paramInput, #paramCombo {
            background: #F8FAFD;
            border: 1px solid #D7DEEB;
            border-radius: 10px;
            padding: 7px 10px;
            min-height: 34px;
        }
        #paramCombo {
            padding-right: 8px;
        }
        #secondsInput {
            background: white;
            border: 1px solid #D4DAE5;
            border-radius: 12px;
            min-width: 150px;
        }
        #secondsField {
            border: none;
            background: transparent;
            padding: 4px 2px;
            min-width: 76px;
            font-weight: 600;
        }
        #secondsUnit {
            color: #637089;
            min-width: 12px;
        }
        #stepButton {
            background: #EEF2FA;
            border: 1px solid #D4DAE5;
            border-radius: 9px;
            color: #27324A;
            font-weight: 700;
            min-height: 28px;
        }
        #stepButton:hover {
            background: #E3EAF8;
        }
        #stepButton:pressed {
            background: #D2DDF3;
        }
        #fileLabel {
            color: #364055;
            background: transparent;
        }
        #statusLabel {
            color: #0A84FF;
            background: transparent;
        }
        #creditLabel {
            color: #7A859A;
            font-size: 12px;
            font-weight: 500;
            padding-top: 2px;
            background: transparent;
        }
        #primaryButton {
            background: #007AFF;
            color: white;
            border: none;
            border-radius: 15px;
            padding: 10px 16px;
            font-weight: 600;
        }
        #primaryButton:hover {
            background: #0068D9;
        }
        #primaryButton:disabled {
            background: #95C6FF;
            color: #EFF6FF;
        }
        #secondaryButton {
            background: #EEF1F7;
            color: #1F2430;
            border: none;
            border-radius: 14px;
            padding: 10px 14px;
            font-weight: 500;
        }
        #secondaryButton:hover {
            background: #DEE4EF;
        }
        #dialogCard {
            background: white;
            border-radius: 20px;
        }
        #dialogTitle {
            font-size: 22px;
            font-weight: 700;
            background: transparent;
        }
        #dialogMessage {
            color: #4E5666;
            background: transparent;
        }
        #pathInput {
            background: #F8FAFD;
            border: 1px solid #DCE3EF;
            border-radius: 12px;
            padding: 9px;
        }
        #fileList {
            border: 1px solid #DCE3EF;
            border-radius: 12px;
            background: #FAFCFF;
            min-height: 260px;
            padding: 4px;
        }
        #fileList::item {
            height: 30px;
            border-radius: 8px;
            padding-left: 8px;
        }
        #fileList::item:selected {
            background: #DDEBFF;
            color: #123A8F;
        }
        #hintLabel {
            color: #697285;
            font-size: 12px;
            background: transparent;
        }
        #switch {
            spacing: 8px;
        }
        #switch::indicator {
            width: 42px;
            height: 24px;
            border-radius: 12px;
            background: #CDD5E3;
        }
        #switch::indicator:checked {
            background: #34C759;
        }
        #exportProgressBar {
            background: #EEF2FA;
            border: 1px solid #D5DCEA;
            border-radius: 10px;
            min-height: 18px;
            text-align: center;
        }
        #exportProgressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #5FA7FF, stop:1 #007AFF);
            border-radius: 9px;
        }
        """
    )


def main() -> int:
    app = QApplication(sys.argv)
    apply_best_font(app)
    apply_styles(app)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
