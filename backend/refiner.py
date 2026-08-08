"""AI-powered transcript refinement.

Goal: fix misheard words, punctuation, capitalization — while preserving the
speaker's original wording, slang, and meaning. If the source contains mixed
languages (e.g. Bangla + English), we keep both.
"""
from __future__ import annotations

import os
from typing import Iterable

from openai import OpenAI

SYSTEM_PROMPT = """You are a meticulous transcript editor. You receive a verbatim
speech-to-text transcript that may contain errors from noisy audio (misheard
words, dropped words, wrong punctuation, wrong capitalization). Your job:

1. Fix obvious mishearings when the intended word/phrase is clear from context.
2. Add proper punctuation and natural capitalization.
3. PRESERVE the speaker's original language(s) and code-switching. If the
   transcript mixes English and another language, keep both. Do NOT translate.
4. Do NOT paraphrase. Do NOT summarize. Do NOT add content that was not spoken.
5. Keep the meaning 100% faithful to the source. If a word is genuinely
   ambiguous, leave it rather than invent.
6. Return ONLY the corrected transcript text. No preamble, no commentary."""


def get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    return OpenAI(api_key=api_key)


def refine_text(
    text: str,
    *,
    language: str | None = None,
    model: str = "gpt-4o-mini",
) -> str:
    """Refine a single block of transcript text. Cheap, fast, faithful."""
    if not text or not text.strip():
        return text

    client = get_client()
    user_msg = text
    if language:
        user_msg = f"[Detected dominant language: {language}]\n\n" + user_msg

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,  # low temp = conservative edits
    )
    return (resp.choices[0].message.content or "").strip()


def refine_segments(
    segments: Iterable[dict],
    *,
    language: str | None = None,
    model: str = "gpt-4o-mini",
) -> list[dict]:
    """Refine each segment while keeping start/end timestamps intact.

    To preserve timestamp accuracy we rewrite each segment individually rather
    than re-segmenting. A small instruction prefix keeps the model from drifting.
    """
    client = get_client()
    out: list[dict] = []
    for seg in segments:
        original = (seg.get("text") or "").strip()
        if not original:
            out.append(seg)
            continue
        # Skip trivially short segments to save tokens
        if len(original) < 4:
            out.append(seg)
            continue

        prefix = (
            f"[Detected dominant language: {language}]\n" if language else ""
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"{prefix}"
                        "Rewrite the following transcript line. Keep it as a single "
                        "natural utterance — do not split it. Preserve any code-switching. "
                        "Reply with ONLY the corrected line, no quotes, no labels.\n\n"
                        f"TEXT: {original}"
                    ),
                },
            ],
            temperature=0.1,
        )
        new_text = (resp.choices[0].message.content or "").strip()
        # Defensive: if the model returned something wildly different in length,
        # we keep the original. Refinement should be ~similar length.
        if 0.4 <= (len(new_text) / max(1, len(original))) <= 2.5 and new_text:
            out.append({**seg, "text": new_text})
        else:
            out.append(seg)
    return out
