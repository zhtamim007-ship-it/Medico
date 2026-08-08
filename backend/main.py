"""FastAPI app: YouTube info, transcribe (with timeline cut), refine, and audio serving."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv  # type: ignore
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import refiner, transcriber, youtube

# Load .env if present
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
JOBS_DIR = BASE_DIR.parent / "jobs"

app = FastAPI(title="AI YouTube Transcriber", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Request / response models ------------------------------------------------

class InfoRequest(BaseModel):
    url: str


class TranscribeRequest(BaseModel):
    url: str
    start: float = Field(0.0, ge=0)
    end: float = Field(0.0, ge=0)
    language: Optional[str] = None
    prompt: Optional[str] = None
    job_id: Optional[str] = None  # reuse an existing job (skip re-download)


class RefineRequest(BaseModel):
    text: Optional[str] = None
    segments: Optional[list[dict]] = None
    language: Optional[str] = None
    mode: str = Field("text", pattern="^(text|segments)$")


# ---- Routes -------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "openai_key_set": bool(os.environ.get("OPENAI_API_KEY")),
        "ffmpeg": shutil.which("ffmpeg") is not None,
    }


@app.post("/api/info")
def api_info(req: InfoRequest):
    try:
        info = youtube.fetch_info(req.url)
        return info.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # pragma: no cover - depends on yt-dlp
        raise HTTPException(status_code=500, detail=f"Failed to fetch info: {e}")


@app.post("/api/transcribe")
def api_transcribe(req: TranscribeRequest, background: BackgroundTasks):
    if not req.url:
        raise HTTPException(400, "url is required")

    t0 = time.time()
    try:
        norm_url = youtube.normalize_url(req.url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if req.end <= req.start:
        raise HTTPException(400, "end must be greater than start")

    job_id = req.job_id or youtube.new_job_id()
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # 1) Download full audio (skip if we already have it for this job)
    src_path: Optional[Path] = None
    for cand in job_dir.glob("src.*"):
        if cand.is_file() and cand.stat().st_size > 0:
            src_path = cand
            break

    if src_path is None:
        try:
            src_path = youtube.download_full_audio(norm_url, job_id)
        except Exception as e:
            raise HTTPException(500, f"Audio download failed: {e}")

    # 2) Cut the requested segment
    try:
        clip_path = youtube.cut_segment(src_path, req.start, req.end, job_id)
    except Exception as e:
        raise HTTPException(500, f"Audio cutting failed: {e}")

    # 3) Transcribe
    try:
        result = transcriber.transcribe(
            clip_path, language=req.language, prompt=req.prompt
        )
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        raise HTTPException(500, f"Transcription failed: {e}")

    # Save transcript JSON next to the clip
    transcript_path = job_dir / f"transcript_{int(req.start)}_{int(req.end)}.json"
    transcript_path.write_text(
        json.dumps(
            {
                "job_id": job_id,
                "url": norm_url,
                "start": req.start,
                "end": req.end,
                "language_hint": req.language,
                **result.to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Schedule cleanup of source file (keep clip for audio playback)
    def _cleanup():
        try:
            if src_path and src_path.exists():
                src_path.unlink(missing_ok=True)
        except Exception:
            pass

    background.add_task(_cleanup)

    return {
        "job_id": job_id,
        "clip_url": f"/api/audio/{job_id}",
        "transcript_url": f"/api/transcript/{job_id}",
        "elapsed_sec": round(time.time() - t0, 2),
        **result.to_dict(),
    }


@app.get("/api/audio/{job_id}")
def api_audio(job_id: str):
    """Serve the most recent clip.wav for a job. Used for the audio overview player."""
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(404, "job not found")
    clips = sorted(job_dir.glob("clip_*.wav"), key=lambda p: p.stat().st_mtime)
    if not clips:
        raise HTTPException(404, "no clip available")
    return FileResponse(clips[-1], media_type="audio/wav", filename=clips[-1].name)


@app.get("/api/transcript/{job_id}")
def api_transcript(job_id: str):
    job_dir = JOBS_DIR / job_id
    files = sorted(job_dir.glob("transcript_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise HTTPException(404, "no transcript available")
    return JSONResponse(json.loads(files[-1].read_text(encoding="utf-8")))


@app.post("/api/refine")
def api_refine(req: RefineRequest):
    try:
        if req.mode == "text":
            if not req.text:
                raise HTTPException(400, "text is required for mode=text")
            refined = refiner.refine_text(req.text, language=req.language)
            return {"text": refined}
        else:  # segments
            if not req.segments:
                raise HTTPException(400, "segments is required for mode=segments")
            refined = refiner.refine_segments(req.segments, language=req.language)
            return {"segments": refined}
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Refinement failed: {e}")


# ---- Static frontend ----------------------------------------------------------

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    @app.get("/")
    def root_fallback():
        return PlainTextResponse("Frontend not built yet.", status_code=500)
