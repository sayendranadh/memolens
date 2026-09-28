FROM python:3.11-slim

# System deps for torch wheels — must run as root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

# Create non-root user (uid 1000) and make /app owned by them
RUN useradd -m -u 1000 user && \
    mkdir -p /app && chown -R user:user /app

USER user
ENV PATH="/home/user/.local/bin:$PATH"
ENV HOME=/home/user
WORKDIR /app

# Install Python deps first (Docker layer cache)
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Pre-download MiniLM so first request isn't a 30s cold start
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('all-MiniLM-L6-v2')"

# Copy application code
COPY --chown=user backend/ ./backend/
COPY --chown=user data/ ./data/
COPY --chown=user eval/ ./eval/
COPY --chown=user tools/ ./tools/
COPY --chown=user pytest.ini .

# Make sure data dir is writable for caches/logs
RUN mkdir -p /app/data/llm_cache && touch /app/data/memory_log.jsonl

ENV PORT=7860
EXPOSE 7860

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]

