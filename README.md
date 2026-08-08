# 🎙️ AI YouTube Transcriber

A full-stack web app that turns any YouTube video into a clean, accurate transcript — in **any language**, even with **noisy / low-quality audio** and **no captions**.

- 🔗 Paste a YouTube link → app fetches the video duration.
- ⏱️ Drag a **dual range slider** to pick *exactly* the slice you want (or just hit "Full video").
- 🌍 **Auto-detects language** (Bangla, English, Hindi, Arabic, mixed code-switching — all preserved as-is).
- 🤖 **AI refinement button** cleans up misheard words, punctuation, and capitalization — without changing the meaning.
- 🔊 **Audio overview** of your selected slice is embedded right in the result page.
- 📥 Download as `.txt` or `.srt`.

## How it works

```
YouTube URL  →  yt-dlp (download audio)
            →  ffmpeg    (cut to your [start, end])
            →  Whisper   (transcribe — OpenAI's most robust STT, 99 languages)
            →  GPT-4o    (optional: refine wording without changing meaning)
```

## Setup

### 1. Requirements

- **Python 3.10+**
- **ffmpeg** (system package)
  - Debian/Ubuntu: `sudo apt install ffmpeg`
  - macOS: `brew install ffmpeg`
- An **OpenAI API key** with access to `whisper-1` and `gpt-4o-mini`.

### 2. Install & run

```bash
cd youtube-transcriber
cp backend/.env.example backend/.env
# → edit backend/.env and paste your OPENAI_API_KEY
./start.sh
```

`start.sh` will create a venv, install deps, and start the server on `http://localhost:8000`.

Want a different port?

```bash
PORT=9000 ./start.sh
```

### 3. Deploy to Render (free hosting, public URL)

The repo includes a `Dockerfile` and `render.yaml` so you can one-click deploy.

1. **Push the project to a GitHub repo.** Don't commit `.venv`, `__pycache__`, or `jobs/`.
2. On [render.com](https://render.com) → **New** → **Blueprint**.
3. Connect the GitHub repo — Render auto-detects `render.yaml`.
4. In the next screen, set `OPENAI_API_KEY=sk-...` as a secret env var, then **Apply**.
5. Wait ~2 min for the Docker build. Your URL will be `https://ai-youtube-transcriber.onrender.com`.

> **Note on the free tier:** Render spins the instance down after 15 min of inactivity. The first request after that takes ~30s to wake up — subsequent requests are instant. Transcription itself still runs at full speed.

## Project layout

```
youtube-transcriber/
├── backend/
│   ├── main.py          # FastAPI app + endpoints
│   ├── youtube.py       # yt-dlp + ffmpeg wrapper
│   ├── transcriber.py   # Whisper API client
│   ├── refiner.py       # GPT-based faithful cleanup
│   ├── requirements.txt
│   └── .env.example
├── frontend/            # Vanilla HTML/CSS/JS (no build step)
│   ├── index.html
│   ├── style.css
│   └── app.js
├── jobs/                # temp audio + transcripts (auto-cleaned)
└── start.sh
```

## API

| Method | Path                | Body / Params                                  | Purpose                                  |
|-------:|---------------------|------------------------------------------------|------------------------------------------|
| GET    | `/api/health`       | —                                              | Health check (OpenAI key, ffmpeg)        |
| POST   | `/api/info`         | `{ url }`                                      | Fetch title, duration, thumbnail         |
| POST   | `/api/transcribe`   | `{ url, start, end, language?, prompt? }`      | Download + cut + Whisper                 |
| POST   | `/api/refine`       | `{ mode, text?, segments?, language? }`        | AI cleanup (faithful)                    |
| GET    | `/api/audio/{job}`  | —                                              | Stream the selected audio segment        |
| GET    | `/api/transcript/{job}` | —                                          | Saved transcript JSON                    |

## Notes on accuracy

- **Whisper-1** is OpenAI's flagship speech model. It's extremely robust to noise, music, accents, and low bitrate. It also auto-detects language and supports code-switching (e.g. Bangla-English) without forcing a single language.
- We send audio as **16 kHz mono PCM** (Whisper's preferred format), which avoids any quality loss from re-encoding.
- For ultra-hard accents or heavy noise, you can supply a **context prompt** with names / jargon to bias decoding (Advanced options).
- The **Refine** button uses a low-temperature GPT-4o-mini pass with strict instructions: fix mishearings, add punctuation, preserve language mix, never paraphrase, never invent.

## Privacy

- The audio file is downloaded into `jobs/<job_id>/`, used for the request, and the original source file is deleted after transcription.
- The clip and transcript JSON stay on disk so the audio overview keeps working until you restart the server. Delete `jobs/` to wipe them.

## License

MIT. Have fun.
