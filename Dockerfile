# LifeHack OS — Production Dockerfile
# Build context: project root
# Runtime: python:3.11-slim

FROM python:3.11-slim AS base

# Prevent .pyc files and enable unbuffered stdout/stderr for clean container logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# -------------------------------------------------------------------
# System dependencies (only what's needed for the web stack)
# -------------------------------------------------------------------
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# -------------------------------------------------------------------
# Non-root user — principle of least privilege
# -------------------------------------------------------------------
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

# -------------------------------------------------------------------
# Install Python dependencies
# Web-only subset: flask, flask-cors, requests, python-dotenv, toml
# customtkinter and pillow are desktop-only and NOT included.
# -------------------------------------------------------------------
WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        "flask>=3.0.0" \
        "flask-cors>=4.0.0" \
        "requests>=2.31.0" \
        "python-dotenv>=1.0.0" \
        "toml>=0.10.2"

# -------------------------------------------------------------------
# Copy source code
# .dockerignore excludes: .env, data/, __pycache__, .git, *.db
# -------------------------------------------------------------------
COPY --chown=appuser:appgroup . .

# -------------------------------------------------------------------
# Persistent volume mount point for the SQLite database
# The data/ directory is created here so Docker can bind-mount it
# without root-owned files being created at runtime.
# -------------------------------------------------------------------
RUN mkdir -p /app/data && chown appuser:appgroup /app/data

VOLUME ["/app/data"]

# -------------------------------------------------------------------
# Runtime
# web/app.py adds project root to sys.path so "from src..." and
# "from routes..." both resolve correctly from /app/web.
# -------------------------------------------------------------------
USER appuser

WORKDIR /app/web

EXPOSE 8420

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8420/health || exit 1

CMD ["python", "app.py"]
