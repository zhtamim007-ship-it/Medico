"""Whisper-based transcription.

We use the OpenAI Whisper API (`whisper-1`). It is the most robust speech-to-text
model for noisy/low-quality audio and supports 99 languages with auto-detection.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from openai import OpenAI


@dataclass
class Segment:
    start: float
    end: float
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TranscriptionResult:
    language: str
    language_probability: float
    duration: float
    text: str  # full concatenated text
    segments: list[Segment]  # timestamped segments

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "language_probability": self.language_probability,
            "duration": self.duration,
            "text": self.text,
            "segments": [s.to_dict() for s in self.segments],
        }


def get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to backend/.env or your environment."
        )
    return OpenAI(api_key=api_key)


def transcribe(
    audio_path: Path,
    *,
    language: Optional[str] = None,  # ISO-639-1 hint like 'en', 'bn', or None for auto
    prompt: Optional[str] = None,
    model: str = "whisper-1",
) -> TranscriptionResult:
    """Send audio to Whisper API and return timestamped segments.

    - language=None -> auto-detect (Whisper picks the dominant language, preserves mixed content).
    - prompt -> optional context (names, jargon) that biases decoding without changing the model.
    """
    client = get_client()
    with open(audio_path, "rb") as f:
        kwargs = dict(
            model=model,
            file=(audio_path.name, f),
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
        if language:
            kwargs["language"] = language
        if prompt:
            kwargs["prompt"] = prompt
        resp = client.audio.transcriptions.create(**kwargs)

    segments = [
        Segment(start=float(s.start), end=float(s.end), text=str(s.text).strip())
        for s in (resp.segments or [])
    ]
    full_text = (resp.text or "").strip()
    if not segments and full_text:
        # Some short clips may return only `text` without segments. Wrap as one segment.
        segments = [Segment(start=0.0, end=float(resp.duration or 0.0), text=full_text)]

    return TranscriptionResult(
        language=getattr(resp, "language", language or "auto"),
        language_probability=float(getattr(resp, "language_probability", 0.0) or 0.0),
        duration=float(getattr(resp, "duration", 0.0) or 0.0),
        text=full_text,
        segments=segments,
    )
