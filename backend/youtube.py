"""YouTube utilities: extract metadata, download audio, cut segments with ffmpeg.

We use yt-dlp for fetching info + best audio stream, and ffmpeg for segment cutting.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yt_dlp

JOBS_DIR = Path(__file__).resolve().parent.parent / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class VideoInfo:
    id: str
    title: str
    duration: int  # seconds
    channel: str
    thumbnail: str
    url: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "duration": self.duration,
            "channel": self.channel,
            "thumbnail": self.thumbnail,
            "url": self.url,
        }


# Matches any youtube.com / youtu.be / youtube-nocookie.com watch URL, shorts, embeds
YT_URL_RE = re.compile(
    r"(https?://)?(www\.|m\.)?"
    r"(youtube\.com/(watch\?v=|shorts/|embed/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)


def normalize_url(url: str) -> str:
    """Pull out the canonical watch URL. Raise ValueError if not a YouTube URL."""
    m = YT_URL_RE.search(url.strip())
    if not m:
        raise ValueError("Not a recognizable YouTube URL")
    return f"https://www.youtube.com/watch?v={m.group(5)}"


def fetch_info(url: str) -> VideoInfo:
    """Fetch video metadata using yt-dlp without downloading."""
    norm = normalize_url(url)
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "extract_flat": False,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(norm, download=False)

    return VideoInfo(
        id=info["id"],
        title=info.get("title", "Untitled"),
        duration=int(info.get("duration") or 0),
        channel=info.get("uploader") or info.get("channel") or "Unknown",
        thumbnail=info.get("thumbnail") or "",
        url=norm,
    )


def _ydl_progress_hook(d: dict) -> None:
    """Optional: hook for progress reporting. Currently a no-op stub."""
    pass


def download_full_audio(url: str, job_id: str) -> Path:
    """Download best audio stream for a video. Returns path to source file."""
    target_dir = JOBS_DIR / job_id
    target_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(target_dir / "src.%(ext)s")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": outtmpl,
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "progress_hooks": [_ydl_progress_hook],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # Find the downloaded file (extension varies)
    candidates = sorted(
        target_dir.glob("src.*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError("yt-dlp did not produce an audio file")
    return candidates[0]


def cut_segment(src: Path, start: float, end: float, job_id: str) -> Path:
    """Cut audio from start..end (seconds). Returns path to wav file (16k mono, PCM s16)."""
    target_dir = JOBS_DIR / job_id
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / f"clip_{int(start)}_{int(end)}.wav"
    duration = max(0.0, end - start)

    # Whisper prefers 16kHz mono PCM. We re-encode to that spec.
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(src),
        "-t",
        f"{duration:.3f}",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-acodec",
        "pcm_s16le",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_path


def job_paths(job_id: str) -> dict:
    """Return a dict of expected file paths for a job (used by endpoints)."""
    d = JOBS_DIR / job_id
    return {
        "dir": d,
        "source_audio": d / "src.m4a",  # may have different ext; helper for listing
        "clip": d / "clip.wav",
    }


def new_job_id() -> str:
    return uuid.uuid4().hex[:16]
