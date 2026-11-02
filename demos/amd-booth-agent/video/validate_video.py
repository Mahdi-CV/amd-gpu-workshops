#!/usr/bin/env python3
"""Validate booth teaser playback metadata and optionally decode every frame."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any


FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "/usr/bin/ffmpeg")
FFPROBE_BIN = os.environ.get("FFPROBE_BIN", "/usr/bin/ffprobe")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--tolerance", type=float, default=0.05)
    parser.add_argument("--decode", action="store_true")
    return parser.parse_args()


def probe(video: Path) -> dict[str, Any]:
    command = [
        FFPROBE_BIN,
        "-v",
        "error",
        "-show_entries",
        (
            "format=duration,size,bit_rate,format_name:"
            "stream=index,codec_type,codec_name,profile,width,height,pix_fmt,"
            "r_frame_rate,avg_frame_rate,nb_frames,sample_rate,channels,"
            "channel_layout,duration"
        ),
        "-of",
        "json",
        str(video),
    ]
    return json.loads(subprocess.check_output(command, text=True))


def frame_rate(value: str) -> float:
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return math.nan


def main() -> int:
    args = parse_args()
    video = args.video.resolve()
    if not video.is_file():
        raise SystemExit(f"Video does not exist: {video}")

    data = probe(video)
    streams = data.get("streams") or []
    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        None,
    )
    audio_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"),
        None,
    )
    failures: list[str] = []

    if video_stream is None:
        failures.append("missing video stream")
    else:
        if video_stream.get("codec_name") != "h264":
            failures.append(f"video codec is {video_stream.get('codec_name')}, expected h264")
        if int(video_stream.get("width") or 0) != args.width:
            failures.append(f"width is {video_stream.get('width')}, expected {args.width}")
        if int(video_stream.get("height") or 0) != args.height:
            failures.append(f"height is {video_stream.get('height')}, expected {args.height}")
        if video_stream.get("pix_fmt") != "yuv420p":
            failures.append(
                f"pixel format is {video_stream.get('pix_fmt')}, expected yuv420p"
            )
        measured_fps = frame_rate(
            str(
                video_stream.get("avg_frame_rate")
                or video_stream.get("r_frame_rate")
                or "0/1"
            )
        )
        if not math.isfinite(measured_fps) or abs(measured_fps - args.fps) > 0.01:
            failures.append(f"frame rate is {measured_fps}, expected {args.fps}")

    duration = float((data.get("format") or {}).get("duration") or 0)
    if abs(duration - args.duration) > args.tolerance:
        failures.append(
            f"duration is {duration:.6f}s, expected {args.duration:.6f}s "
            f"± {args.tolerance:.3f}s"
        )

    if audio_stream is None:
        failures.append("missing compatibility audio stream")
    else:
        if audio_stream.get("codec_name") != "aac":
            failures.append(f"audio codec is {audio_stream.get('codec_name')}, expected aac")
        if int(audio_stream.get("sample_rate") or 0) != 48000:
            failures.append(
                f"audio sample rate is {audio_stream.get('sample_rate')}, expected 48000"
            )
        if int(audio_stream.get("channels") or 0) != 2:
            failures.append(
                f"audio channels is {audio_stream.get('channels')}, expected 2"
            )

    decode_passed: bool | None = None
    if args.decode:
        decode = subprocess.run(
            [
                FFMPEG_BIN,
                "-v",
                "error",
                "-i",
                str(video),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-f",
                "null",
                "-",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if decode.returncode:
            failures.append(f"full decode failed: {decode.stderr.strip()}")
            decode_passed = False
        else:
            decode_passed = True

    summary = {
        "path": str(video),
        "duration_seconds": duration,
        "size_bytes": int((data.get("format") or {}).get("size") or 0),
        "container": (data.get("format") or {}).get("format_name"),
        "video": video_stream,
        "audio": audio_stream,
        "decode_check": (
            "passed"
            if decode_passed is True
            else "failed"
            if decode_passed is False
            else "not run"
        ),
    }
    print(json.dumps(summary, indent=2))

    if failures:
        print("\nValidation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("\nValidation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
