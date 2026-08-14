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


def analyze_bpm(path: Path, maximum_seconds: int = 180) -> dict:
    import numpy as np
    import librosa

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
        analysis_path = Path(temp_file.name)
    try:
        result = subprocess.run(
            [
                str(FFMPEG_PATH), "-y", "-i", str(path), "-vn", "-ac", "1", "-ar", "22050",
                "-t", str(maximum_seconds), "-c:a", "pcm_s16le", str(analysis_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=maximum_seconds + 45,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0,
        )
        if result.returncode != 0:
            raise RuntimeError("无法准备 BPM 分析音频。")
        samples, sample_rate = librosa.load(str(analysis_path), sr=None, mono=True)
        if samples.size < sample_rate * 3:
            raise ValueError("音频过短，无法可靠分析 BPM。")
        onset_envelope = librosa.onset.onset_strength(y=samples, sr=sample_rate)
        tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_envelope,
            sr=sample_rate,
            units="frames",
        )
        bpm = float(np.asarray(tempo).reshape(-1)[0])
        if not np.isfinite(bpm) or bpm <= 0:
            raise ValueError("未检测到稳定节拍。")
        return {
            "bpm": round(bpm, 1),
            "beatCount": int(len(beat_frames)),
            "analysisDurationMs": int(round(samples.size / sample_rate * 1000)),
        }
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
