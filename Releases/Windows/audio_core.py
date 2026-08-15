from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
import json
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from imageio_ffmpeg import get_ffmpeg_exe

_BUNDLED_FFMPEG = Path(get_ffmpeg_exe())
if _BUNDLED_FFMPEG.is_file():
    _ffmpeg_dir = str(_BUNDLED_FFMPEG.parent)
    _path_parts = os.environ.get("PATH", "").split(os.pathsep)
    if _ffmpeg_dir not in _path_parts:
        os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

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

from pydub import AudioSegment, effects
import pydub.audio_segment as pydub_audio_segment

from ncm_core import NcmMetadata, decrypt_ncm

RUNTIME_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
CORE0_EXECUTABLE = RUNTIME_ROOT / "Core0" / ("ncm-core.exe" if sys.platform.startswith("win") else "ncm-core")

SUPPORTED_FORMATS = ["mp3", "wav", "flac", "ogg", "m4a", "aac", "wma", "aiff", "opus"]
SUPPORTED_EXTENSIONS = {f".{item}" for item in SUPPORTED_FORMATS}
LOSSLESS_FORMATS = {"wav", "flac", "aiff"}
INVALID_FILENAME_CHARS = r'[<>:"/\\|?*]'

FORMAT_PROFILES = {
    "mp3": {"label": "MP3", "bitrates": [128, 192, 256, 320], "default": 320},
    "wav": {"label": "WAV (PCM)", "bitrates": [], "default": 0},
    "flac": {"label": "FLAC", "bitrates": [], "default": 0},
    "ogg": {"label": "OGG Vorbis", "bitrates": [96, 128, 192, 256, 320, 500], "default": 256},
    "m4a": {"label": "M4A (AAC)", "bitrates": [96, 128, 192, 256, 320], "default": 256},
    "aac": {"label": "AAC", "bitrates": [96, 128, 192, 256, 320], "default": 256},
    "wma": {"label": "WMA", "bitrates": [96, 128, 192, 256, 320], "default": 192},
    "aiff": {"label": "AIFF (PCM)", "bitrates": [], "default": 0},
    "opus": {"label": "Opus", "bitrates": [64, 96, 128, 160, 192, 256, 320, 512], "default": 192},
}

SAMPLE_RATES = [22050, 32000, 44100, 48000, 88200, 96000, 192000]
CHANNEL_OPTIONS = [1, 2, 6, 8]
BIT_DEPTHS = [8, 16, 24, 32]


@dataclass
class AudioParameterSettings:
    sample_rate: int
    channels: int
    bit_depth: int
    bitrate_kbps: int


@dataclass
class AudioFileDetails:
    source_format: str
    duration_ms: int
    sample_rate: int
    channels: int
    bit_depth: int
    bitrate_kbps: int
    frame_count: int


@dataclass
class ExportJob:
    input_path: Path
    output_path: Path
    target_fmt: str
    action: str
    action_seconds: float
    params: AudioParameterSettings
    fade_ms: int = 8
    normalize: bool = False


@dataclass
class ConversionJob:
    input_path: Path
    output_path: Path
    target_fmt: str
    params: AudioParameterSettings
    normalize: bool = False


def _ffmpeg_is_healthy(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        result = subprocess.run(
            [str(path), "-hide_banner", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def resolve_ffmpeg() -> Path:
    candidates: list[Path] = []
    configured = os.environ.get("FFMPEG_BINARY", "").strip()
    system_ffmpeg = shutil.which("ffmpeg")
    if configured:
        candidates.append(Path(configured))
    if system_ffmpeg:
        candidates.append(Path(system_ffmpeg))
    candidates.append(Path(get_ffmpeg_exe()))

    ffmpeg_path = next((path for path in candidates if _ffmpeg_is_healthy(path)), None)
    if ffmpeg_path is None:
        raise FileNotFoundError("未找到可用的 FFmpeg。请重新运行 Start.bat 自动下载并修复环境。")

    AudioSegment.converter = str(ffmpeg_path)
    ffmpeg_dir = str(ffmpeg_path.parent)
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    if ffmpeg_dir not in path_parts:
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    os.environ.setdefault("FFMPEG_BINARY", str(ffmpeg_path))
    return ffmpeg_path


FFMPEG_PATH = resolve_ffmpeg()


def _safe_mediainfo_json(filepath, read_ahead_limit=-1):
    original = _safe_mediainfo_json._original  # type: ignore[attr-defined]
    try:
        return original(filepath, read_ahead_limit=read_ahead_limit)
    except (FileNotFoundError, OSError):
        return {}


_safe_mediainfo_json._original = pydub_audio_segment.mediainfo_json  # type: ignore[attr-defined]
pydub_audio_segment.mediainfo_json = _safe_mediainfo_json


def load_audio_segment(path: Path) -> AudioSegment:
    try:
        return AudioSegment.from_file(str(path))
    except (FileNotFoundError, OSError) as exc:
        winerror = getattr(exc, "winerror", None)
        if not (isinstance(exc, FileNotFoundError) or winerror == 2):
            raise
    return AudioSegment.from_file_using_temporary_files(str(path))


def default_bitrate_for_format(fmt: str) -> int:
    profile = FORMAT_PROFILES.get(fmt.lower())
    return int(profile["default"]) if profile else 320


def _probe_bitrate_kbps(path: Path) -> Optional[int]:
    info = pydub_audio_segment.mediainfo_json(str(path))
    if not isinstance(info, dict) or not info:
        return None

    bit_rate_raw = None
    format_info = info.get("format")
    if isinstance(format_info, dict):
        bit_rate_raw = format_info.get("bit_rate")
    if not bit_rate_raw:
        for stream in info.get("streams", []):
            if isinstance(stream, dict) and stream.get("codec_type") == "audio":
                bit_rate_raw = stream.get("bit_rate")
                if bit_rate_raw:
                    break
    try:
        return max(1, int(int(bit_rate_raw) / 1000)) if bit_rate_raw else None
    except (TypeError, ValueError):
        return None


def _probe_ffmpeg_audio_metadata(path: Path) -> tuple[Optional[int], Optional[int]]:
    try:
        result = subprocess.run(
            [str(FFMPEG_PATH), "-hide_banner", "-i", str(path), "-t", "0", "-f", "null", "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=15,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0,
        )
    except (OSError, subprocess.SubprocessError):
        return None, None

    input_log = result.stdout.split("Stream mapping:", 1)[0]
    bitrate_match = re.search(r"Duration:[^\r\n]*bitrate:\s*(\d+)\s*kb/s", input_log)
    bit_depth_match = re.search(r"\((\d+)\s+bit\)", input_log)
    if not bit_depth_match:
        bit_depth_match = re.search(r"Audio:\s*pcm_(?:[suf])(\d+)", input_log)

    bitrate = int(bitrate_match.group(1)) if bitrate_match else None
    bit_depth = int(bit_depth_match.group(1)) if bit_depth_match else None
    return bitrate, bit_depth


def _waveform_peaks(audio: AudioSegment, points: int = 520) -> list[list[float]]:
    samples: array = audio.get_array_of_samples()
    channels = max(1, int(audio.channels))
    frames = len(samples) // channels
    if frames <= 0:
        return [[0.0] * points for _ in range(min(channels, 2))]

    output_channels = min(channels, 2)
    bucket_frames = max(1, frames // points)
    sample_ceiling = float(1 << (audio.sample_width * 8 - 1))
    peaks = [[] for _ in range(output_channels)]

    for point in range(points):
        frame_start = point * bucket_frames
        frame_end = frames if point == points - 1 else min(frames, frame_start + bucket_frames)
        stride = max(1, (frame_end - frame_start) // 32)
        channel_max = [0] * output_channels
        for frame in range(frame_start, frame_end, stride):
            base = frame * channels
            for channel in range(output_channels):
                channel_max[channel] = max(channel_max[channel], abs(samples[base + channel]))
        for channel in range(output_channels):
            peaks[channel].append(round(min(1.0, channel_max[channel] / sample_ceiling), 4))

    if channels == 1:
        peaks.append(list(peaks[0]))
    return peaks


def analyze_audio_file(path: Path) -> dict:
    if not path.exists() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError("请选择支持的音频文件。")

    audio = load_audio_segment(path)
    source_fmt = path.suffix.lower().lstrip(".")
    ffmpeg_bitrate, ffmpeg_bit_depth = _probe_ffmpeg_audio_metadata(path)
    bitrate = _probe_bitrate_kbps(path) or ffmpeg_bitrate or default_bitrate_for_format(source_fmt)
    details = AudioFileDetails(
        source_format=source_fmt or "unknown",
        duration_ms=len(audio),
        sample_rate=int(audio.frame_rate),
        channels=int(audio.channels),
        bit_depth=ffmpeg_bit_depth or max(8, int(audio.sample_width) * 8),
        bitrate_kbps=bitrate,
        frame_count=int(audio.frame_count()),
    )
    return {
        "path": str(path),
        "name": path.name,
        "stem": path.stem,
        "sourceFormat": details.source_format,
        "durationMs": details.duration_ms,
        "sampleRate": details.sample_rate,
        "channels": details.channels,
        "bitDepth": details.bit_depth,
        "bitrateKbps": details.bitrate_kbps,
        "frameCount": details.frame_count,
        "waveform": _waveform_peaks(audio),
    }


def _validate_job(job: ExportJob) -> None:
    _validate_output_settings(job.target_fmt, job.params)
    if job.action not in {"trim", "prepend"}:
        raise ValueError("请选择删除开头或添加静音。")
    if job.action_seconds <= 0:
        raise ValueError("偏移时间必须大于 0。")
    if not (0 <= job.fade_ms <= 1000):
        raise ValueError("防爆音淡入时长必须在 0 到 1000 ms 之间。")


def _validate_output_settings(target_fmt: str, params: AudioParameterSettings) -> None:
    if target_fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"暂不支持导出格式：{target_fmt}")
    if params.sample_rate < 8000 or params.sample_rate > 384000:
        raise ValueError("采样率必须在 8000 到 384000 Hz 之间。")
    if params.channels not in CHANNEL_OPTIONS:
        raise ValueError("声道数只支持 1、2、6 或 8。")
    if params.bit_depth not in BIT_DEPTHS:
        raise ValueError("位深只支持 8、16、24 或 32 bit。")
    if target_fmt not in LOSSLESS_FORMATS and not (16 <= params.bitrate_kbps <= 5000):
        raise ValueError("有损格式的比特率必须在 16 到 5000 kbps 之间。")


def execute_export_job(job: ExportJob, progress_callback: Callable[[int, str], None]) -> Path:
    _validate_job(job)
    resolve_ffmpeg()
    progress_callback(5, "正在读取音频")
    audio = load_audio_segment(job.input_path)
    progress_callback(20, "正在编辑起始位置")

    offset_ms = int(round(job.action_seconds * 1000))
    fade_ms = min(job.fade_ms, max(0, len(audio) - 1))
    if job.action == "trim":
        if offset_ms >= len(audio):
            raise ValueError("删除时长不能大于或等于音频总长度。")
        edited = audio[offset_ms:]
        if fade_ms:
            edited = edited.fade_in(min(fade_ms, len(edited)))
    else:
        source = audio.fade_in(fade_ms) if fade_ms else audio
        silence = AudioSegment.silent(duration=offset_ms, frame_rate=audio.frame_rate)
        silence = silence.set_channels(audio.channels).set_sample_width(audio.sample_width)
        edited = silence + source

    progress_callback(38, "正在应用输出参数")
    edited = edited.set_frame_rate(job.params.sample_rate)
    edited = edited.set_channels(job.params.channels)
    edited = edited.set_sample_width(max(1, min(4, job.params.bit_depth // 8)))
    if job.normalize:
        edited = effects.normalize(edited, headroom=1.0)
    progress_callback(55, "正在准备编码")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
        temp_wav = Path(temp_file.name)

    try:
        edited.export(str(temp_wav), format="wav")
        progress_callback(66, "正在编码导出")
        encode_with_ffmpeg_progress(
            temp_input=temp_wav,
            output_path=job.output_path,
            target_fmt=job.target_fmt,
            bitrate_kbps=job.params.bitrate_kbps,
            bit_depth=job.params.bit_depth,
            total_ms=max(1, len(edited)),
            progress_callback=progress_callback,
        )
    except Exception:
        job.output_path.unlink(missing_ok=True)
        raise
    finally:
        temp_wav.unlink(missing_ok=True)

    progress_callback(100, "导出完成")
    return job.output_path


def execute_conversion_job(job: ConversionJob, progress_callback: Callable[[int, str], None]) -> Path:
    _validate_output_settings(job.target_fmt, job.params)
    resolve_ffmpeg()
    progress_callback(5, "正在读取音频")
    audio = load_audio_segment(job.input_path)
    progress_callback(30, "正在应用输出参数")
    audio = audio.set_frame_rate(job.params.sample_rate)
    audio = audio.set_channels(job.params.channels)
    audio = audio.set_sample_width(max(1, min(4, job.params.bit_depth // 8)))
    if job.normalize:
        audio = effects.normalize(audio, headroom=1.0)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
        temp_wav = Path(temp_file.name)
    try:
        progress_callback(55, "正在准备编码")
        audio.export(str(temp_wav), format="wav")
        encode_with_ffmpeg_progress(
            temp_input=temp_wav,
            output_path=job.output_path,
            target_fmt=job.target_fmt,
            bitrate_kbps=job.params.bitrate_kbps,
            bit_depth=job.params.bit_depth,
            total_ms=max(1, len(audio)),
            progress_callback=progress_callback,
        )
    except Exception:
        job.output_path.unlink(missing_ok=True)
        raise
    finally:
        temp_wav.unlink(missing_ok=True)

    progress_callback(100, "格式转换完成")
    return job.output_path


def convert_ncm_to_wav(
    source_path: Path,
    output_path: Path,
    progress_callback: Callable[[int, str], None],
) -> tuple[Path, NcmMetadata]:
    resolve_ffmpeg()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".decoded") as temp_file:
        decoded_path = Path(temp_file.name)
    try:
        if CORE0_EXECUTABLE.is_file():
            metadata = _decrypt_ncm_with_core(source_path, decoded_path, progress_callback)
        else:
            _, metadata, _source_format = decrypt_ncm(source_path, decoded_path, progress_callback)
        progress_callback(58, "正在转换为 WAV")
        command = [
            str(FFMPEG_PATH), "-y", "-i", str(decoded_path), "-vn", "-c:a", "pcm_s16le",
        ]
        if metadata.title:
            command.extend(["-metadata", f"title={metadata.title}"])
        if metadata.artists:
            command.extend(["-metadata", f"artist={', '.join(metadata.artists)}"])
        if metadata.album:
            command.extend(["-metadata", f"album={metadata.album}"])
        command.extend(["-progress", "pipe:1", "-nostats", str(output_path)])
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0,
        )
        logs: list[str] = []
        if process.stdout:
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                logs = (logs + [line])[-30:]
                if line.startswith(("out_time_ms=", "out_time_us=")) and metadata.duration_ms > 0:
                    try:
                        encoded_ms = int(line.split("=", 1)[1]) // 1000
                    except ValueError:
                        continue
                    ratio = max(0.0, min(1.0, encoded_ms / metadata.duration_ms))
                    progress_callback(58 + int(ratio * 40), "正在转换为 WAV")
                elif line == "progress=end":
                    progress_callback(99, "正在写入 WAV")
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError("NCM 转 WAV 失败。\n" + "\n".join(logs[-12:]))
        progress_callback(100, "NCM 已转换为 WAV")
        return output_path, metadata
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    finally:
        decoded_path.unlink(missing_ok=True)


def _decrypt_ncm_with_core(
    source_path: Path,
    decoded_path: Path,
    progress_callback: Callable[[int, str], None],
) -> NcmMetadata:
    command = [
        str(CORE0_EXECUTABLE),
        "--input",
        str(source_path),
        "--output",
        str(decoded_path),
        "--json-progress",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0,
    )
    result_payload: Optional[dict] = None
    error_message = ""
    try:
        if process.stdout:
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    error_message = line
                    continue
                if payload.get("type") == "progress":
                    progress_callback(int(payload.get("progress", 0)), str(payload.get("message", "正在解密 NCM 音频")))
                elif payload.get("type") == "result":
                    result_payload = payload
                elif payload.get("type") == "error":
                    error_message = str(payload.get("message", "NCM 核心执行失败。"))
        return_code = process.wait()
    except Exception:
        process.terminate()
        process.wait(timeout=5)
        raise
    if return_code != 0:
        raise RuntimeError(error_message or f"NCM 核心执行失败（退出码 {return_code}）。")
    if result_payload is None or not decoded_path.is_file():
        raise RuntimeError("NCM 核心未返回有效结果。")
    values = result_payload.get("metadata") or {}
    return NcmMetadata(
        title=str(values.get("title") or ""),
        artists=tuple(str(item) for item in values.get("artists") or []),
        album=str(values.get("album") or ""),
        source_format=str(values.get("source_format") or result_payload.get("format") or ""),
        bitrate=int(values.get("bitrate") or 0),
        duration_ms=int(values.get("duration_ms") or 0),
    )


BPM_ANALYSIS_SAMPLE_RATE = 22050
BPM_ANALYSIS_HOP_LENGTH = 512
BPM_MIN = 70.0
BPM_MAX = 200.0


def _bpm_progress(callback: Optional[Callable[[int, str], None]], value: int, message: str) -> None:
    if callback:
        callback(max(0, min(100, int(value))), message)


def _check_bpm_cancelled(cancel_callback: Optional[Callable[[], bool]]) -> None:
    if cancel_callback and cancel_callback():
        raise RuntimeError("BPM 分析已取消。")


def _normalize_bpm(value: float) -> float:
    """Keep the reported beat layer in a practical charting range."""
    bpm = float(value)
    while bpm > BPM_MAX:
        bpm /= 2.0
    while bpm < BPM_MIN:
        bpm *= 2.0
    return bpm


def _weighted_median(values, weights) -> float:
    import numpy as np

    ordered = np.argsort(values)
    sorted_values = np.asarray(values, dtype=float)[ordered]
    sorted_weights = np.asarray(weights, dtype=float)[ordered]
    cutoff = sorted_weights.sum() / 2.0
    return float(sorted_values[np.searchsorted(np.cumsum(sorted_weights), cutoff)])


def _robust_bpm_from_beats(beat_times) -> tuple[Optional[float], float, int]:
    """Estimate tempo from beat timestamps, rejecting implausible intervals."""
    import numpy as np

    if len(beat_times) < 6:
        return None, 0.0, 0
    times = np.asarray(beat_times, dtype=float)
    intervals = np.diff(times)
    median_interval = float(np.median(intervals))
    if not np.isfinite(median_interval) or median_interval <= 0:
        return None, 0.0, 0
    deviations = np.abs(intervals - median_interval)
    mad = float(np.median(deviations))
    tolerance = max(0.012, mad * 3.5, median_interval * 0.12)
    valid_intervals = deviations <= tolerance
    valid_beats = np.concatenate(([True], valid_intervals))
    beat_indexes = np.flatnonzero(valid_beats)
    if len(beat_indexes) < 6:
        return None, 0.0, 0
    slope, _intercept = np.polyfit(beat_indexes, times[valid_beats], 1)
    if not np.isfinite(slope) or slope <= 0:
        return None, 0.0, 0
    consistency = (len(beat_indexes) / len(times)) * max(0.0, 1.0 - mad / max(median_interval * 0.08, 1e-6))
    return _normalize_bpm(60.0 / float(slope)), min(1.0, consistency), int(len(beat_indexes))


def _consensus_bpm(values, weights) -> tuple[float, float, float]:
    """Pick the strongest tempo cluster and describe its agreement margin."""
    import numpy as np

    tempi = np.asarray([_normalize_bpm(value) for value in values], dtype=float)
    vote_weights = np.asarray(weights, dtype=float)
    scores = []
    for candidate in tempi:
        distance = np.abs(np.log2(tempi / candidate))
        scores.append(float(np.sum(vote_weights * np.exp(-0.5 * (distance / 0.028) ** 2))))
    order = np.argsort(scores)[::-1]
    best_index = int(order[0])
    best = tempi[best_index]
    within_cluster = np.abs(np.log2(tempi / best)) <= 0.028
    clustered = tempi[within_cluster]
    clustered_weights = vote_weights[within_cluster]
    bpm = _weighted_median(clustered, clustered_weights)
    agreement = float(clustered_weights.sum() / max(vote_weights.sum(), 1e-6))
    second_score = scores[int(order[1])] if len(order) > 1 else 0.0
    margin = float((scores[best_index] - second_score) / max(scores[best_index], 1e-6))
    return bpm, agreement, max(0.0, min(1.0, margin))


def _merge_tempo_segments(segments: list[dict]) -> list[dict]:
    import numpy as np

    if not segments:
        return []
    merged: list[dict] = []
    for segment in segments:
        if not merged:
            merged.append(dict(segment))
            continue
        previous = merged[-1]
        difference = abs(float(np.log2(segment["bpm"] / previous["bpm"])))
        if difference <= 0.028:
            previous["endMs"] = max(previous["endMs"], segment["endMs"])
            previous["bpm"] = round(
                _weighted_median(
                    [previous["bpm"], segment["bpm"]],
                    [previous["confidence"], segment["confidence"]],
                ),
                2,
            )
            previous["confidence"] = round((previous["confidence"] + segment["confidence"]) / 2)
        else:
            merged.append(dict(segment))
    return merged


def analyze_bpm_samples(
    samples,
    sample_rate: int,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_callback: Optional[Callable[[], bool]] = None,
) -> dict:
    """Estimate stable and local tempos from the decoded waveform.

    This intentionally combines independent local estimates with timestamp-based
    beat regression. It avoids treating one onset-envelope peak as ground truth.
    """
    import librosa
    import numpy as np
    from scipy.stats import uniform

    _check_bpm_cancelled(cancel_callback)
    waveform = np.asarray(samples, dtype=np.float32)
    if waveform.ndim > 1:
        waveform = librosa.to_mono(waveform)
    if waveform.size < sample_rate * 3:
        raise ValueError("音频过短，无法可靠分析 BPM。")

    _bpm_progress(progress_callback, 28, "移除静音并增强节奏瞬态")
    waveform, active_interval = librosa.effects.trim(waveform, top_db=35, hop_length=BPM_ANALYSIS_HOP_LENGTH)
    if waveform.size < sample_rate * 3:
        raise ValueError("有效音频过短，无法可靠分析 BPM。")
    active_start_seconds = active_interval[0] / sample_rate
    _check_bpm_cancelled(cancel_callback)

    harmonic, percussive = librosa.effects.hpss(waveform)
    percussive_onset = librosa.onset.onset_strength(
        y=percussive,
        sr=sample_rate,
        hop_length=BPM_ANALYSIS_HOP_LENGTH,
        lag=2,
        max_size=3,
    )
    full_onset = librosa.onset.onset_strength(
        y=waveform,
        sr=sample_rate,
        hop_length=BPM_ANALYSIS_HOP_LENGTH,
        lag=2,
        max_size=3,
    )
    del harmonic
    percussive_scale = max(float(np.std(percussive_onset)), 1e-6)
    full_scale = max(float(np.std(full_onset)), 1e-6)
    onset_envelope = 0.72 * (percussive_onset / percussive_scale) + 0.28 * (full_onset / full_scale)
    if float(np.max(onset_envelope)) <= 0:
        raise ValueError("音频中没有足够清晰的节奏瞬态。")

    duration_seconds = waveform.size / sample_rate
    window_seconds = min(28.0, max(16.0, duration_seconds))
    window_count = 1 if duration_seconds <= window_seconds + 2 else min(9, max(3, int(np.ceil(duration_seconds / 24.0))))
    starts = np.linspace(0.0, max(0.0, duration_seconds - window_seconds), window_count)
    local_results: list[dict] = []
    tempo_prior = uniform(loc=40.0, scale=260.0)

    for index, start_seconds in enumerate(starts, start=1):
        _check_bpm_cancelled(cancel_callback)
        progress = 40 + int(index / len(starts) * 40)
        _bpm_progress(progress_callback, progress, f"分析节奏片段 {index}/{len(starts)}")
        start_frame = int(round(start_seconds * sample_rate / BPM_ANALYSIS_HOP_LENGTH))
        end_frame = int(round((start_seconds + window_seconds) * sample_rate / BPM_ANALYSIS_HOP_LENGTH))
        segment_onset = onset_envelope[start_frame:max(start_frame + 1, end_frame)]
        if len(segment_onset) < 12:
            continue
        dynamic_tempi = librosa.feature.tempo(
            onset_envelope=segment_onset,
            sr=sample_rate,
            hop_length=BPM_ANALYSIS_HOP_LENGTH,
            aggregate=None,
            max_tempo=300.0,
            prior=tempo_prior,
        )
        dynamic_tempi = np.asarray(dynamic_tempi, dtype=float)
        dynamic_tempi = dynamic_tempi[np.isfinite(dynamic_tempi) & (dynamic_tempi > 20.0)]
        if len(dynamic_tempi) < 4:
            continue
        candidate = _weighted_median(
            np.asarray([_normalize_bpm(value) for value in dynamic_tempi]),
            np.ones(len(dynamic_tempi)),
        )
        tracked_tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=segment_onset,
            sr=sample_rate,
            hop_length=BPM_ANALYSIS_HOP_LENGTH,
            start_bpm=candidate,
            tightness=130,
            trim=False,
            prior=tempo_prior,
            units="frames",
        )
        beat_times = librosa.frames_to_time(beat_frames, sr=sample_rate, hop_length=BPM_ANALYSIS_HOP_LENGTH)
        regressed_bpm, consistency, beat_count = _robust_bpm_from_beats(beat_times)
        tempo_value = regressed_bpm or _normalize_bpm(float(np.asarray(tracked_tempo).reshape(-1)[0]))
        if not np.isfinite(tempo_value):
            continue
        local_results.append(
            {
                "startMs": int(round((active_start_seconds + start_seconds) * 1000)),
                "endMs": int(round((active_start_seconds + min(duration_seconds, start_seconds + window_seconds)) * 1000)),
                "bpm": float(tempo_value),
                "consistency": float(consistency),
                "beatCount": int(beat_count),
            }
        )

    if not local_results:
        raise ValueError("未能从音频中提取稳定的节拍。")
    _check_bpm_cancelled(cancel_callback)
    _bpm_progress(progress_callback, 84, "汇总候选 BPM 并校正拍层级")

    candidate_values = [item["bpm"] for item in local_results]
    candidate_weights = [max(0.2, item["consistency"]) for item in local_results]
    bpm, agreement, margin = _consensus_bpm(candidate_values, candidate_weights)
    result_segments = []
    for item in local_results:
        local_agreement = max(0.0, 1.0 - abs(np.log2(item["bpm"] / bpm)) / 0.09)
        confidence = int(round(100 * min(1.0, 0.45 * item["consistency"] + 0.55 * local_agreement)))
        result_segments.append(
            {
                "startMs": item["startMs"],
                "endMs": item["endMs"],
                "bpm": round(item["bpm"], 2),
                "confidence": confidence,
                "beatCount": item["beatCount"],
            }
        )
    sections = _merge_tempo_segments(result_segments)
    mean_consistency = float(np.average([item["consistency"] for item in local_results], weights=candidate_weights))
    confidence = int(round(100 * min(0.99, 0.45 * agreement + 0.35 * mean_consistency + 0.20 * margin)))
    candidates = [{"bpm": round(bpm, 2), "label": "推荐拍层"}]
    if bpm / 2 >= 40:
        candidates.append({"bpm": round(bpm / 2, 2), "label": "半速候选"})
    if bpm * 2 <= 320:
        candidates.append({"bpm": round(bpm * 2, 2), "label": "倍速候选"})
    _bpm_progress(progress_callback, 100, "BPM 分析完成")
    return {
        "bpm": round(bpm, 2),
        "confidence": confidence,
        "beatCount": int(sum(item["beatCount"] for item in local_results)),
        "analysisDurationMs": int(round(duration_seconds * 1000)),
        "activeStartMs": int(round(active_start_seconds * 1000)),
        "segmentCount": len(local_results),
        "isVariableTempo": len(sections) > 1,
        "segments": sections,
        "candidates": candidates,
        "method": "多片段节拍回归",
    }


def analyze_bpm(
    path: Path,
    maximum_seconds: int = 240,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_callback: Optional[Callable[[], bool]] = None,
) -> dict:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
        analysis_path = Path(temp_file.name)
    try:
        _bpm_progress(progress_callback, 8, "正在解码音频")
        result = subprocess.run(
            [
                str(FFMPEG_PATH), "-y", "-i", str(path), "-vn", "-ac", "1", "-ar", str(BPM_ANALYSIS_SAMPLE_RATE),
                "-t", str(maximum_seconds), "-c:a", "pcm_s16le", str(analysis_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=maximum_seconds + 45,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0,
        )
        _check_bpm_cancelled(cancel_callback)
        if result.returncode != 0:
            raise RuntimeError("无法准备 BPM 分析音频。")
        import librosa

        samples, sample_rate = librosa.load(str(analysis_path), sr=None, mono=True)
        _bpm_progress(progress_callback, 20, "已解码音频，正在建立节奏特征")
        return analyze_bpm_samples(samples, sample_rate, progress_callback, cancel_callback)
    finally:
        analysis_path.unlink(missing_ok=True)


def encode_with_ffmpeg_progress(
    temp_input: Path,
    output_path: Path,
    target_fmt: str,
    bitrate_kbps: int,
    bit_depth: int,
    total_ms: int,
    progress_callback: Callable[[int, str], None],
) -> None:
    command = [str(FFMPEG_PATH), "-y", "-i", str(temp_input), "-vn"]
    codecs = {
        "mp3": "libmp3lame",
        "m4a": "aac",
        "aac": "aac",
        "ogg": "libvorbis",
        "opus": "libopus",
        "wma": "wmav2",
        "flac": "flac",
    }
    pcm_codecs = {
        "wav": {8: "pcm_u8", 16: "pcm_s16le", 24: "pcm_s24le", 32: "pcm_s32le"},
        "aiff": {8: "pcm_s8", 16: "pcm_s16be", 24: "pcm_s24be", 32: "pcm_s32be"},
    }
    if target_fmt in pcm_codecs:
        command.extend(["-c:a", pcm_codecs[target_fmt][bit_depth]])
    elif target_fmt in codecs:
        command.extend(["-c:a", codecs[target_fmt]])
    if target_fmt not in LOSSLESS_FORMATS and bitrate_kbps > 0:
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
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0,
    )

    logs: list[str] = []
    last_progress = 66
    if process.stdout:
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            logs.append(line)
            logs = logs[-40:]
            if line.startswith(("out_time_ms=", "out_time_us=")):
                try:
                    encoded_ms = int(line.split("=", 1)[1]) // 1000
                except ValueError:
                    continue
                ratio = max(0.0, min(1.0, encoded_ms / max(1, total_ms)))
                mapped = 66 + int(ratio * 32)
                if mapped > last_progress:
                    last_progress = mapped
                    progress_callback(last_progress, "正在编码导出")
            elif line == "progress=end":
                progress_callback(99, "正在写入文件")

    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"FFmpeg 导出失败（错误码 {return_code}）\n" + "\n".join(logs[-15:]))


def estimate_output_bytes(duration_ms: int, fmt: str, params: AudioParameterSettings) -> int:
    seconds = max(0.0, duration_ms / 1000)
    if fmt in {"wav", "aiff"}:
        return int(seconds * params.sample_rate * params.channels * max(1, params.bit_depth // 8))
    if fmt == "flac":
        raw = seconds * params.sample_rate * params.channels * max(1, params.bit_depth // 8)
        return int(raw * 0.58)
    return int(seconds * max(1, params.bitrate_kbps) * 1000 / 8)


def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    index = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def sanitize_filename(name: str) -> str:
    return re.sub(INVALID_FILENAME_CHARS, "_", name).strip().strip(".")


def open_folder(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
