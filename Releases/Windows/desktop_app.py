from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QPoint, Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QPainterPath, QRegion
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QMainWindow, QWidget

from audio_core import (
    BIT_DEPTHS,
    CHANNEL_OPTIONS,
    FFMPEG_PATH,
    FORMAT_PROFILES,
    SAMPLE_RATES,
    SUPPORTED_EXTENSIONS,
    SUPPORTED_FORMATS,
    AudioParameterSettings,
    ConversionJob,
    ExportJob,
    analyze_bpm,
    analyze_audio_file,
    convert_ncm_to_wav,
    ensure_unique_path,
    execute_conversion_job,
    execute_export_job,
    open_folder,
    sanitize_filename,
)

PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
UI_ROOT = PROJECT_ROOT / "ui"
WINDOWS_TITLEBAR_HEIGHT = 54
WINDOWS_TITLEBAR_CENTER_HALF_WIDTH = 150
WINDOWS_TITLEBAR_ACTION_WIDTH = 196
WINDOWS_CORNER_RADIUS = 10
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2
LOGGER = logging.getLogger("xmaomusic")
if getattr(sys, "frozen", False):
    OUTPUT_ROOT = (
        Path.home() / "Music" / "XMaoMusic Output"
        if sys.platform == "darwin"
        else Path(sys.executable).resolve().parent / "Output"
    )
else:
    OUTPUT_ROOT = Path(__file__).resolve().parent / "Output"


def platform_name() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


def windows_titlebar_drag_regions(width: int) -> tuple[tuple[int, int], tuple[int, int]]:
    center = width // 2
    left_end = max(0, center - WINDOWS_TITLEBAR_CENTER_HALF_WIDTH)
    right_start = min(width, center + WINDOWS_TITLEBAR_CENTER_HALF_WIDTH)
    right_end = max(right_start, width - WINDOWS_TITLEBAR_ACTION_WIDTH)
    return (0, left_end), (right_start, right_end - right_start)


def set_windows_corner_preference(window_id: int, rounded: bool) -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes

        preference = ctypes.c_int(DWMWCP_ROUND if rounded else DWMWCP_DONOTROUND)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(window_id),
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(preference),
            ctypes.sizeof(preference),
        )
        return result == 0
    except (AttributeError, OSError):
        return False


def json_result(**values) -> str:
    return json.dumps(values, ensure_ascii=False)


class LoadWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(analyze_audio_file(self.path))
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Audio import failed: %s", self.path)
            self.failed.emit(str(exc))


class ExportWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, job: ExportJob) -> None:
        super().__init__()
        self.job = job

    @Slot()
    def run(self) -> None:
        try:
            output = execute_export_job(self.job, self.progress.emit)
            self.finished.emit(str(output))
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Audio export failed: %s", self.job.input_path)
            self.failed.emit(str(exc))


class ConversionWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, job: ConversionJob) -> None:
        super().__init__()
        self.job = job

    @Slot()
    def run(self) -> None:
        try:
            output = execute_conversion_job(self.job, self.progress.emit)
            self.finished.emit(str(output))
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Audio conversion failed: %s", self.job.input_path)
            self.failed.emit(str(exc))


class BpmWorker(QObject):
    finished = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(str(self.path), analyze_bpm(self.path))
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("BPM analysis failed: %s", self.path)
            self.failed.emit(str(self.path), str(exc))


class NcmWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(str, object)
    failed = Signal(str)

    def __init__(self, source_path: Path, output_path: Path) -> None:
        super().__init__()
        self.source_path = source_path
        self.output_path = output_path

    @Slot()
    def run(self) -> None:
        try:
            output, metadata = convert_ncm_to_wav(self.source_path, self.output_path, self.progress.emit)
            self.finished.emit(str(output), metadata)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("NCM conversion failed: %s", self.source_path)
            self.failed.emit(str(exc))


class WebBridge(QObject):
    audioLoaded = Signal(str)
    audioLoadFailed = Signal(str)
    exportProgress = Signal(int, str)
    exportFinished = Signal(str)
    exportFailed = Signal(str)
    conversionProgress = Signal(int, str)
    conversionFinished = Signal(str)
    conversionFailed = Signal(str)
    bpmAnalysisStarted = Signal(str)
    bpmDetected = Signal(str)
    bpmAnalysisFailed = Signal(str)
    ncmConfirmationRequested = Signal(str, str)
    ncmProgress = Signal(int, str)
    ncmConverted = Signal(str)
    ncmConversionFailed = Signal(str)
    windowStateChanged = Signal(bool)
    playbackChanged = Signal(str)
    playbackPositionChanged = Signal(int, int)
    playbackFailed = Signal(str)
    notice = Signal(str, str)

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.window = window
        self.audio_path: Optional[Path] = None
        self.audio_data: Optional[dict] = None
        self.pending_audio_path: Optional[Path] = None
        self.load_thread: Optional[QThread] = None
        self.load_worker: Optional[LoadWorker] = None
        self.export_thread: Optional[QThread] = None
        self.export_worker: Optional[ExportWorker] = None
        self.conversion_thread: Optional[QThread] = None
        self.conversion_worker: Optional[ConversionWorker] = None
        self.bpm_thread: Optional[QThread] = None
        self.bpm_worker: Optional[BpmWorker] = None
        self.queued_bpm_path: Optional[Path] = None
        self.ncm_thread: Optional[QThread] = None
        self.ncm_worker: Optional[NcmWorker] = None
        self.pending_ncm_output: Optional[Path] = None
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.9)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.positionChanged.connect(self._on_playback_position_changed)
        self.player.durationChanged.connect(self._on_playback_duration_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.errorOccurred.connect(self._on_playback_error)
        self.pending_play_position: Optional[int] = None
        self.pending_seek_position: Optional[int] = None

    @Slot(result=str)
    def getInitialState(self) -> str:  # noqa: N802
        return json_result(
            ok=True,
            ffmpegPath=str(FFMPEG_PATH),
            outputDirectory=str(OUTPUT_ROOT),
            formats=[
                {
                    "value": fmt,
                    "label": FORMAT_PROFILES[fmt]["label"],
                    "bitrates": FORMAT_PROFILES[fmt]["bitrates"],
                    "defaultBitrate": FORMAT_PROFILES[fmt]["default"],
                    "lossless": not bool(FORMAT_PROFILES[fmt]["bitrates"]),
                }
                for fmt in SUPPORTED_FORMATS
            ],
            sampleRates=SAMPLE_RATES,
            channels=CHANNEL_OPTIONS,
            bitDepths=BIT_DEPTHS,
            maximized=self.window.isMaximized(),
            platform=platform_name(),
        )

    @Slot(result=str)
    def browseAudio(self) -> str:  # noqa: N802
        start = str(self.audio_path.parent if self.audio_path else Path.home())
        patterns = " ".join(f"*{extension}" for extension in sorted(SUPPORTED_EXTENSIONS | {".ncm"}))
        path_text, _ = QFileDialog.getOpenFileName(
            self.window,
            "选择音频文件",
            start,
            f"音频文件 ({patterns});;所有文件 (*)",
        )
        if not path_text:
            return json_result(ok=False, cancelled=True)
        return self.handle_import(Path(path_text))

    @Slot(str, result=str)
    def loadAudio(self, path_text: str) -> str:  # noqa: N802
        return self.handle_import(Path(path_text))

    def handle_import(self, path: Path) -> str:
        if path.suffix.lower() == ".ncm":
            if not path.exists():
                return json_result(ok=False, error="NCM 文件不存在。")
            self.ncmConfirmationRequested.emit(str(path), path.name)
            return json_result(ok=True, pendingConfirmation=True, name=path.name)
        return self.start_load(path)

    def start_load(self, path: Path) -> str:
        if self._audio_task_in_progress():
            return json_result(ok=False, error="请等待当前音频任务完成。")
        if not path.exists() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return json_result(ok=False, error="请选择支持的音频文件。")

        self.stopPlayback()
        thread = QThread(self)
        worker = LoadWorker(path)
        self.pending_audio_path = path
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_audio_loaded)
        worker.failed.connect(self._on_audio_load_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_load_runtime)
        self.load_thread = thread
        self.load_worker = worker
        thread.start()
        return json_result(ok=True, pending=True, name=path.name)

    @Slot(object)
    def _on_audio_loaded(self, data: dict) -> None:
        if self.pending_audio_path is None:
            self.audioLoadFailed.emit("音频载入状态已失效，请重新导入。")
            return
        self.audio_path = self.pending_audio_path
        self.audio_data = data
        self.pending_play_position = None
        self.pending_seek_position = None
        self.player.setSource(QUrl.fromLocalFile(str(self.audio_path)))
        self.playbackPositionChanged.emit(0, int(data.get("durationMs", 0)))
        self.audioLoaded.emit(json.dumps(data, ensure_ascii=False))
        self.queued_bpm_path = self.audio_path

    @Slot(str)
    def _on_audio_load_failed(self, message: str) -> None:
        self.audioLoadFailed.emit(message)

    @Slot()
    def _clear_load_runtime(self) -> None:
        self.load_thread = None
        self.load_worker = None
        self.pending_audio_path = None
        queued = self.queued_bpm_path
        self.queued_bpm_path = None
        if queued and self.audio_path == queued:
            QTimer.singleShot(0, lambda: self._queue_bpm_analysis(queued))

    def _queue_bpm_analysis(self, path: Path) -> None:
        if self.bpm_thread and self.bpm_thread.isRunning():
            self.queued_bpm_path = path
            return
        self._start_bpm_analysis(path)

    def _start_bpm_analysis(self, path: Path) -> None:
        thread = QThread(self)
        worker = BpmWorker(path)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_bpm_detected)
        worker.failed.connect(self._on_bpm_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_bpm_runtime)
        self.bpm_thread = thread
        self.bpm_worker = worker
        self.bpmAnalysisStarted.emit(path.name)
        thread.start()

    @Slot(str, object)
    def _on_bpm_detected(self, path_text: str, data: dict) -> None:
        if self.audio_path and self.audio_path == Path(path_text):
            self.bpmDetected.emit(json.dumps(data, ensure_ascii=False))

    @Slot(str, str)
    def _on_bpm_failed(self, path_text: str, message: str) -> None:
        if self.audio_path and self.audio_path == Path(path_text):
            self.bpmAnalysisFailed.emit(message)

    @Slot()
    def _clear_bpm_runtime(self) -> None:
        self.bpm_thread = None
        self.bpm_worker = None
        queued = self.queued_bpm_path
        self.queued_bpm_path = None
        if queued and self.audio_path == queued:
            QTimer.singleShot(0, lambda: self._start_bpm_analysis(queued))

    @Slot(str, result=str)
    def convertNcm(self, path_text: str) -> str:  # noqa: N802
        path = Path(path_text)
        if not path.exists() or path.suffix.lower() != ".ncm":
            return json_result(ok=False, error="请选择有效的 NCM 文件。")
        if self.ncm_thread and self.ncm_thread.isRunning():
            return json_result(ok=False, error="已有 NCM 正在转换。")
        if self._audio_task_in_progress():
            return json_result(ok=False, error="请等待当前音频任务完成。")

        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        clean_stem = sanitize_filename(path.stem) or "ncm_audio"
        output_path = ensure_unique_path(OUTPUT_ROOT / f"{clean_stem}.wav")
        thread = QThread(self)
        worker = NcmWorker(path, output_path)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_ncm_progress)
        worker.finished.connect(self._on_ncm_converted)
        worker.failed.connect(self._on_ncm_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_ncm_runtime)
        self.ncm_thread = thread
        self.ncm_worker = worker
        thread.start()
        return json_result(ok=True, pending=True, outputPath=str(output_path))

    @Slot(int, str)
    def _on_ncm_progress(self, progress: int, message: str) -> None:
        self.ncmProgress.emit(progress, message)

    @Slot(str, object)
    def _on_ncm_converted(self, output_path: str, _metadata) -> None:
        self.ncmConverted.emit(output_path)
        self.pending_ncm_output = Path(output_path)

    @Slot(str)
    def _on_ncm_failed(self, message: str) -> None:
        self.ncmConversionFailed.emit(message)

    @Slot()
    def _clear_ncm_runtime(self) -> None:
        self.ncm_thread = None
        self.ncm_worker = None
        output_path = self.pending_ncm_output
        self.pending_ncm_output = None
        if output_path:
            QTimer.singleShot(0, lambda: self._load_converted_ncm(output_path))

    def _load_converted_ncm(self, output_path: Path) -> None:
        result = json.loads(self.start_load(output_path))
        if not result.get("ok"):
            self.ncmConversionFailed.emit(result.get("error", "无法载入转换后的 WAV。"))

    @Slot(str, result=str)
    def exportAudio(self, payload_text: str) -> str:  # noqa: N802
        if not self.audio_path or not self.audio_data:
            return json_result(ok=False, error="请先导入音频文件。")
        if self._audio_task_in_progress():
            return json_result(ok=False, error="请等待当前音频分析或处理任务完成。")

        try:
            payload = json.loads(payload_text)
            target_fmt = str(payload.get("format", "")).lower()
            raw_name = str(payload.get("filename", "")).strip()
            clean_name = sanitize_filename(Path(raw_name).stem)
            if not clean_name:
                raise ValueError("请输入有效的输出文件名。")
            params = AudioParameterSettings(
                sample_rate=int(payload["sampleRate"]),
                channels=int(payload["channels"]),
                bit_depth=int(payload["bitDepth"]),
                bitrate_kbps=int(payload.get("bitrateKbps") or 0),
            )
            OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
            output_path = ensure_unique_path(OUTPUT_ROOT / f"{clean_name}.{target_fmt}")
            job = ExportJob(
                input_path=self.audio_path,
                output_path=output_path,
                target_fmt=target_fmt,
                action=str(payload["action"]),
                action_seconds=float(payload["seconds"]),
                params=params,
                fade_ms=int(payload.get("fadeMs", 0)) if payload.get("antiClick", True) else 0,
                normalize=bool(payload.get("normalize", False)),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return json_result(ok=False, error=str(exc))

        thread = QThread(self)
        worker = ExportWorker(job)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_export_progress)
        worker.finished.connect(self._on_export_finished)
        worker.failed.connect(self._on_export_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_export_runtime)
        self.export_thread = thread
        self.export_worker = worker
        thread.start()
        return json_result(ok=True, pending=True, outputPath=str(output_path))

    @Slot(str, result=str)
    def convertAudio(self, payload_text: str) -> str:  # noqa: N802
        if not self.audio_path or not self.audio_data:
            return json_result(ok=False, error="请先导入音频文件。")
        if self._audio_task_in_progress():
            return json_result(ok=False, error="请等待当前音频分析或处理任务完成。")
        try:
            payload = json.loads(payload_text)
            target_fmt = str(payload.get("format", "")).lower()
            clean_name = sanitize_filename(Path(str(payload.get("filename", "")).strip()).stem)
            if not clean_name:
                raise ValueError("请输入有效的输出文件名。")
            params = AudioParameterSettings(
                sample_rate=int(payload["sampleRate"]),
                channels=int(payload["channels"]),
                bit_depth=int(payload["bitDepth"]),
                bitrate_kbps=int(payload.get("bitrateKbps") or 0),
            )
            OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
            output_path = ensure_unique_path(OUTPUT_ROOT / f"{clean_name}.{target_fmt}")
            job = ConversionJob(
                input_path=self.audio_path,
                output_path=output_path,
                target_fmt=target_fmt,
                params=params,
                normalize=bool(payload.get("normalize", False)),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return json_result(ok=False, error=str(exc))

        thread = QThread(self)
        worker = ConversionWorker(job)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_conversion_progress)
        worker.finished.connect(self._on_conversion_finished)
        worker.failed.connect(self._on_conversion_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_conversion_runtime)
        self.conversion_thread = thread
        self.conversion_worker = worker
        thread.start()
        return json_result(ok=True, pending=True, outputPath=str(output_path))

    def _audio_task_in_progress(self) -> bool:
        return bool(
            (self.export_thread and self.export_thread.isRunning())
            or (self.conversion_thread and self.conversion_thread.isRunning())
            or (self.ncm_thread and self.ncm_thread.isRunning())
            or (self.load_thread and self.load_thread.isRunning())
            or (self.bpm_thread and self.bpm_thread.isRunning())
        )

    def _encoding_in_progress(self) -> bool:
        return self._audio_task_in_progress()

    @Slot(int, result=str)
    def playFrom(self, position_ms: int) -> str:  # noqa: N802
        if not self.audio_path or not self.audio_data:
            return json_result(ok=False, error="请先导入音频文件。")
        duration = int(self.audio_data.get("durationMs", 0))
        position = max(0, min(int(position_ms), max(0, duration - 1)))
        self.pending_seek_position = None
        ready_statuses = {
            QMediaPlayer.LoadedMedia,
            QMediaPlayer.BufferingMedia,
            QMediaPlayer.BufferedMedia,
            QMediaPlayer.StalledMedia,
            QMediaPlayer.EndOfMedia,
        }
        if self.player.mediaStatus() in ready_statuses:
            self.player.setPosition(position)
            self.player.play()
        else:
            self.pending_play_position = position
        return json_result(ok=True, positionMs=position)

    @Slot(result=str)
    def pausePlayback(self) -> str:  # noqa: N802
        self.pending_play_position = None
        self.pending_seek_position = None
        self.player.pause()
        return json_result(ok=True)

    @Slot(result=str)
    def stopPlayback(self) -> str:  # noqa: N802
        self.pending_play_position = None
        self.pending_seek_position = None
        self.player.stop()
        return json_result(ok=True)

    @Slot(int, result=str)
    def seekPlayback(self, position_ms: int) -> str:  # noqa: N802
        if not self.audio_data:
            return json_result(ok=False, error="请先导入音频文件。")
        duration = int(self.audio_data.get("durationMs", 0))
        position = max(0, min(int(position_ms), max(0, duration)))
        ready_statuses = {
            QMediaPlayer.LoadedMedia,
            QMediaPlayer.BufferingMedia,
            QMediaPlayer.BufferedMedia,
            QMediaPlayer.StalledMedia,
            QMediaPlayer.EndOfMedia,
        }
        if self.player.mediaStatus() in ready_statuses:
            self.player.setPosition(position)
        else:
            self.pending_seek_position = position
        return json_result(ok=True, positionMs=position)

    @Slot(object)
    def _on_playback_state_changed(self, playback_state) -> None:
        names = {
            QMediaPlayer.PlayingState: "playing",
            QMediaPlayer.PausedState: "paused",
            QMediaPlayer.StoppedState: "stopped",
        }
        self.playbackChanged.emit(names.get(playback_state, "stopped"))

    @Slot(int)
    def _on_playback_position_changed(self, position_ms: int) -> None:
        duration = int(self.audio_data.get("durationMs", 0)) if self.audio_data else self.player.duration()
        self.playbackPositionChanged.emit(int(position_ms), max(0, int(duration)))

    @Slot(int)
    def _on_playback_duration_changed(self, duration_ms: int) -> None:
        position = max(0, int(self.player.position()))
        duration = int(self.audio_data.get("durationMs", duration_ms)) if self.audio_data else int(duration_ms)
        self.playbackPositionChanged.emit(position, max(0, duration))

    @Slot(object)
    def _on_media_status_changed(self, media_status) -> None:
        ready_statuses = {
            QMediaPlayer.LoadedMedia,
            QMediaPlayer.BufferingMedia,
            QMediaPlayer.BufferedMedia,
            QMediaPlayer.StalledMedia,
        }
        if self.pending_play_position is not None and media_status in ready_statuses:
            position = self.pending_play_position
            self.pending_play_position = None
            self.player.setPosition(position)
            self.player.play()
        elif self.pending_seek_position is not None and media_status in ready_statuses:
            position = self.pending_seek_position
            self.pending_seek_position = None
            self.player.setPosition(position)

    @Slot(object, str)
    def _on_playback_error(self, _error, error_message: str) -> None:
        message = error_message or self.player.errorString() or "系统无法播放此音频格式。"
        self.playbackFailed.emit(message)

    def shutdown(self) -> None:
        self.pending_play_position = None
        self.pending_seek_position = None
        self.player.stop()
        self.player.setSource(QUrl())
        active_threads = (
            self.export_thread,
            self.conversion_thread,
            self.ncm_thread,
            self.load_thread,
            self.bpm_thread,
        )
        running_threads = [thread for thread in active_threads if thread and thread.isRunning()]
        for thread in running_threads:
            thread.requestInterruption()
            thread.quit()
        for thread in running_threads:
            if not thread.wait(30_000):
                LOGGER.error("Audio worker did not stop before shutdown: %r", thread)

    @Slot(int, str)
    def _on_export_progress(self, progress: int, message: str) -> None:
        self.exportProgress.emit(progress, message)

    @Slot(str)
    def _on_export_finished(self, output_path: str) -> None:
        self.exportFinished.emit(output_path)
        open_folder(Path(output_path).parent)

    @Slot(str)
    def _on_export_failed(self, message: str) -> None:
        self.exportFailed.emit(message)

    @Slot()
    def _clear_export_runtime(self) -> None:
        self.export_thread = None
        self.export_worker = None

    @Slot(int, str)
    def _on_conversion_progress(self, progress: int, message: str) -> None:
        self.conversionProgress.emit(progress, message)

    @Slot(str)
    def _on_conversion_finished(self, output_path: str) -> None:
        self.conversionFinished.emit(output_path)
        open_folder(Path(output_path).parent)

    @Slot(str)
    def _on_conversion_failed(self, message: str) -> None:
        self.conversionFailed.emit(message)

    @Slot()
    def _clear_conversion_runtime(self) -> None:
        self.conversion_thread = None
        self.conversion_worker = None

    @Slot(result=str)
    def revealOutput(self) -> str:  # noqa: N802
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        open_folder(OUTPUT_ROOT)
        return json_result(ok=True)

    @Slot(str)
    def setWindowTheme(self, theme: str) -> None:  # noqa: N802
        color = "#dce8eb" if theme == "light" else "#071014"
        self.window.web_view.page().setBackgroundColor(QColor(color))

    @Slot()
    def minimizeWindow(self) -> None:  # noqa: N802
        self.window.showMinimized()

    @Slot()
    def toggleMaximize(self) -> None:  # noqa: N802
        self.window.toggle_maximize()

    @Slot()
    def closeWindow(self) -> None:  # noqa: N802
        self.window.close()


class AudioWebView(QWebEngineView):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.main_window = window
        self.setAcceptDrops(True)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        event.ignore()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        accepted = SUPPORTED_EXTENSIONS | {".ncm"}
        if any(url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in accepted for url in urls):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.suffix.lower() in SUPPORTED_EXTENSIONS | {".ncm"}:
                result = json.loads(self.main_window.bridge.handle_import(path))
                if not result.get("ok"):
                    self.main_window.bridge.audioLoadFailed.emit(result.get("error", "无法读取音频。"))
                event.acceptProposedAction()
                return
        super().dropEvent(event)


class AppWebPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message: str, line_number: int, source_id: str) -> None:  # noqa: N802
        log_method = LOGGER.error if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel else LOGGER.info
        log_method("Web UI: %s (%s:%s)", message, source_id, line_number)


class WindowDragHandle(QWidget):
    def __init__(self, parent: QWidget, window: "MainWindow") -> None:
        super().__init__(parent)
        self.main_window = window
        self._drag_global: Optional[QPoint] = None
        self._window_origin: Optional[QPoint] = None
        self.setAttribute(Qt.WA_TranslucentBackground)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        if not self.main_window.isMaximized():
            self._drag_global = event.globalPosition().toPoint()
            self._window_origin = self.main_window.frameGeometry().topLeft()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_global and self._window_origin and event.buttons() & Qt.LeftButton:
            self.main_window.move(self._window_origin + event.globalPosition().toPoint() - self._drag_global)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_global = None
        self._window_origin = None
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.main_window.toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("XMaoMusic OffsetEditor")
        if sys.platform == "darwin":
            self.setWindowFlags(Qt.Window)
        else:
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.resize(1180, 760)
        self.setMinimumSize(900, 620)

        self.web_view = AudioWebView(self)
        self.web_view.setPage(AppWebPage(self.web_view))
        self.setCentralWidget(self.web_view)
        self.drag_handles: list[WindowDragHandle] = []
        if sys.platform.startswith("win"):
            self.drag_handles = [
                WindowDragHandle(self.web_view, self),
                WindowDragHandle(self.web_view, self),
            ]
            self.web_view.loadFinished.connect(lambda _ok: QTimer.singleShot(0, self._layout_drag_handles))
            self._layout_drag_handles()
        self.web_view.page().setBackgroundColor(QColor("#071014"))
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)

        self.bridge = WebBridge(self)
        self.channel = QWebChannel(self.web_view.page())
        self.channel.registerObject("backend", self.bridge)
        self.web_view.page().setWebChannel(self.channel)

        html_path = UI_ROOT / "index.html"
        if not html_path.exists():
            raise FileNotFoundError(f"界面文件不存在：{html_path}")
        self.web_view.setUrl(QUrl.fromLocalFile(str(html_path)))

    def _apply_windows_window_shape(self) -> None:
        if not sys.platform.startswith("win"):
            return
        maximized = self.isMaximized() or self.isFullScreen()
        dwm_applied = set_windows_corner_preference(int(self.winId()), not maximized)
        if maximized:
            self.clearMask()
            return

        windows_build = getattr(sys.getwindowsversion(), "build", 0)
        if dwm_applied and windows_build >= 22000:
            self.clearMask()
            return

        path = QPainterPath()
        path.addRoundedRect(
            0,
            0,
            self.width(),
            self.height(),
            WINDOWS_CORNER_RADIUS,
            WINDOWS_CORNER_RADIUS,
        )
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def _layout_drag_handles(self) -> None:
        if not self.drag_handles:
            return
        for drag_handle, (x, width) in zip(
            self.drag_handles,
            windows_titlebar_drag_regions(self.web_view.width()),
        ):
            drag_handle.setGeometry(x, 0, width, WINDOWS_TITLEBAR_HEIGHT)
            drag_handle.show()
            drag_handle.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "drag_handles"):
            self._layout_drag_handles()
            self._apply_windows_window_shape()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._apply_windows_window_shape)

    def toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self.bridge.windowStateChanged.emit(self.isMaximized())

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if hasattr(self, "bridge"):
            self.bridge.windowStateChanged.emit(self.isMaximized())
            QTimer.singleShot(0, self._apply_windows_window_shape)

    def closeEvent(self, event) -> None:  # noqa: N802
        active_threads = (
            self.bridge.export_thread,
            self.bridge.conversion_thread,
            self.bridge.ncm_thread,
            self.bridge.load_thread,
            self.bridge.bpm_thread,
        )
        if any(thread and thread.isRunning() for thread in active_threads):
            self.bridge.notice.emit("任务进行中", "请等待当前转换完成后再关闭。")
            event.ignore()
            return
        self.bridge.shutdown()
        super().closeEvent(event)
