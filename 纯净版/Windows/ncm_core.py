from __future__ import annotations

import base64
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, Optional

from Crypto.Cipher import AES

# Format reference: https://github.com/yoki123/ncmdump (Apache-2.0).
# This implementation was rewritten for bounded-memory streaming output.
_MAGIC = b"CTENFDAM"
_CORE_KEY = bytes.fromhex("687a4852416d736f356b496e62617857")
_META_KEY = bytes.fromhex("2331346c6a6b5f215c5d2630553c2728")
_CHUNK_SIZE = 0x8000


@dataclass(frozen=True)
class NcmMetadata:
    title: str = ""
    artists: tuple[str, ...] = ()
    album: str = ""
    source_format: str = ""
    bitrate: int = 0
    duration_ms: int = 0


def is_ncm_file(path: Path) -> bool:
    try:
        with path.open("rb") as source:
            return source.read(len(_MAGIC)) == _MAGIC
    except OSError:
        return False


def _read_exact(source: BinaryIO, size: int) -> bytes:
    data = source.read(size)
    if len(data) != size:
        raise ValueError("NCM 文件不完整或已损坏。")
    return data


def _read_u32(source: BinaryIO) -> int:
    return struct.unpack("<I", _read_exact(source, 4))[0]


def _read_block(source: BinaryIO, maximum: int = 64 * 1024 * 1024) -> bytes:
    size = _read_u32(source)
    if size > maximum:
        raise ValueError("NCM 数据块大小异常。")
    return _read_exact(source, size)


def _unpad_pkcs7(data: bytes) -> bytes:
    if not data:
        raise ValueError("NCM 加密数据为空。")
    padding = data[-1]
    if padding < 1 or padding > AES.block_size or data[-padding:] != bytes([padding]) * padding:
        raise ValueError("NCM 加密数据填充无效。")
    return data[:-padding]


def _decrypt_ecb(key: bytes, data: bytes) -> bytes:
    usable = len(data) - (len(data) % AES.block_size)
    if usable <= 0:
        raise ValueError("NCM 加密数据长度无效。")
    return _unpad_pkcs7(AES.new(key, AES.MODE_ECB).decrypt(data[:usable]))


def _build_key_box(key: bytes) -> bytearray:
    if not key or len(key) > 255:
        raise ValueError("NCM 音频密钥无效。")
    box = bytearray(range(256))
    last = 0
    key_offset = 0
    for index in range(256):
        swap = (box[index] + last + key[key_offset]) & 0xFF
        box[index], box[swap] = box[swap], box[index]
        last = swap
        key_offset = (key_offset + 1) % len(key)
    return box


def _parse_metadata(encrypted: bytes) -> NcmMetadata:
    if not encrypted:
        return NcmMetadata()
    decoded = bytearray(encrypted)
    for index in range(len(decoded)):
        decoded[index] ^= 0x63
    try:
        payload = base64.b64decode(decoded[22:], validate=False)
        plain = _decrypt_ecb(_META_KEY, payload)
        if plain.startswith(b"music:"):
            plain = plain[6:]
        values = json.loads(plain.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("无法解析 NCM 音乐信息。") from exc

    artists = tuple(
        str(item[0])
        for item in values.get("artist", [])
        if isinstance(item, list) and item
    )
    return NcmMetadata(
        title=str(values.get("musicName") or ""),
        artists=artists,
        album=str(values.get("album") or ""),
        source_format=str(values.get("format") or "").lower(),
        bitrate=int(values.get("bitrate") or 0),
        duration_ms=int(values.get("duration") or 0),
    )


def _detect_audio_format(header: bytes, metadata_format: str) -> str:
    if metadata_format in {"mp3", "flac"}:
        return metadata_format
    if header.startswith(b"fLaC"):
        return "flac"
    if header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0):
        return "mp3"
    raise ValueError("NCM 已解密，但无法识别内部音频格式。")


def decrypt_ncm(
    source_path: Path,
    destination_path: Path,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> tuple[Path, NcmMetadata, str]:
    callback = progress_callback or (lambda _progress, _message: None)
    last_progress = -1
    last_message = ""

    def report(progress: int, message: str) -> None:
        nonlocal last_progress, last_message
        if progress == last_progress and message == last_message:
            return
        last_progress = progress
        last_message = message
        callback(progress, message)

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    report(3, "正在读取 NCM 容器")

    try:
        with source_path.open("rb") as source, destination_path.open("wb") as output:
            if _read_exact(source, 8) != _MAGIC:
                raise ValueError("文件不是有效的网易云 NCM 容器。")
            _read_exact(source, 2)

            encrypted_key = bytearray(_read_block(source, 1024 * 1024))
            for index in range(len(encrypted_key)):
                encrypted_key[index] ^= 0x64
            key_plain = _decrypt_ecb(_CORE_KEY, bytes(encrypted_key))
            if not key_plain.startswith(b"neteasecloudmusic"):
                raise ValueError("NCM 音频密钥校验失败。")
            key_box = _build_key_box(key_plain[17:])

            metadata = _parse_metadata(_read_block(source, 8 * 1024 * 1024))
            _read_exact(source, 9)
            cover_size = _read_u32(source)
            if cover_size > 32 * 1024 * 1024:
                raise ValueError("NCM 封面数据大小异常。")
            _read_exact(source, cover_size)

            audio_start = source.tell()
            total_audio = max(1, source_path.stat().st_size - audio_start)
            processed = 0
            first_header = b""
            report(12, "正在解密 NCM 音频")
            while True:
                chunk = bytearray(source.read(_CHUNK_SIZE))
                if not chunk:
                    break
                for index in range(len(chunk)):
                    key_index = (index + 1) & 0xFF
                    chunk[index] ^= key_box[
                        (key_box[key_index] + key_box[(key_box[key_index] + key_index) & 0xFF]) & 0xFF
                    ]
                if not first_header:
                    first_header = bytes(chunk[:16])
                output.write(chunk)
                processed += len(chunk)
                report(12 + int(min(1.0, processed / total_audio) * 43), "正在解密 NCM 音频")

        audio_format = _detect_audio_format(first_header, metadata.source_format)
        report(56, "NCM 音频解密完成")
        return destination_path, metadata, audio_format
    except Exception:
        destination_path.unlink(missing_ok=True)
        raise
