from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ncm_core import decrypt_ncm  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="XMaoMusic headless NCM decoder")
    parser.add_argument("--input", required=True, type=Path, help="Source .ncm file")
    parser.add_argument("--output", required=True, type=Path, help="Decoded MP3/FLAC output")
    parser.add_argument("--json-progress", action="store_true", help="Emit newline-delimited JSON")
    args = parser.parse_args()

    def progress(value: int, message: str) -> None:
        if args.json_progress:
            emit({"type": "progress", "progress": value, "message": message})
        else:
            print(f"[{value:3d}%] {message}", flush=True)

    try:
        output, metadata, source_format = decrypt_ncm(args.input, args.output, progress)
        result = {
            "type": "result",
            "output": str(output),
            "format": source_format,
            "metadata": asdict(metadata),
        }
        emit(result) if args.json_progress else print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001
        payload = {"type": "error", "message": str(exc)}
        emit(payload) if args.json_progress else print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
