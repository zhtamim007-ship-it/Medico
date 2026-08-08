# Dockerfile for AI YouTube Transcriber
# - Based on python:3.11-slim (small, official)
# - Installs ffmpeg from apt (required for audio cutting)
# - Runs uvicorn on Render's $PORT

FROM python:3.11-slim

# System deps: ffmpeg for audio cutting, curl for healthcheck
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

# Create app dir
WORKDIR /app

# Install Python deps first (better layer caching)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r backend/requirements.txt

# Copy app code
COPY backend ./backend
COPY frontend ./frontend
COPY start.sh ./start.sh
RUN chmod +x ./start.sh

# Ensure jobs dir exists (Render has ephemeral disk; this is fine for a per-job scratch dir)
RUN mkdir -p ./jobs

# Tell uvicorn to bind to Render's port
ENV PORT=8000
EXPOSE 8000

# Healthcheck (Render uses this for the free-tier instance)
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:${PORT}/api/health || exit 1

# Start the API
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
