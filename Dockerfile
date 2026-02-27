# ============================================================
# BharatAlpha — Dockerfile
# ============================================================
# Multi-stage build:
#   Stage 1 (builder) — install dependencies into a clean venv
#   Stage 2 (runtime) — copy venv + app code, run as non-root
#
# Base: python:3.11-slim (matches local dev Python 3.11.2)
# Exposes: port 8501 (Streamlit default)
# ============================================================

# ── Stage 1: Builder ─────────────────────────────────────────
FROM python:3.11-slim AS builder

# Build dependencies for packages that compile C extensions
# (lxml, cryptography, grpcio, onnxruntime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    libxml2-dev \
    libxslt1-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy requirements first — Docker layer cache means pip install
# only reruns when requirements.txt changes, not on code changes
COPY requirements.txt .

# Create isolated venv inside builder
RUN python -m venv /build/venv

# Upgrade pip inside venv
RUN /build/venv/bin/pip install --upgrade pip setuptools wheel

# Install all dependencies
RUN /build/venv/bin/pip install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime ─────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Runtime system libraries only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r bharatalpha && useradd -r -g bharatalpha bharatalpha

WORKDIR /app

# Copy the venv from builder stage
COPY --from=builder /build/venv /app/venv

# Copy application code
# NOTE: .env is intentionally NOT copied — credentials are injected
# at runtime via docker run -e flags from Jenkins credentials store.
# Never bake secrets into a Docker image.
COPY config/   /app/config/
COPY src/      /app/src/
COPY app.py    /app/app.py

# Create output directory and set ownership
RUN mkdir -p /app/output && \
    chown -R bharatalpha:bharatalpha /app

# Make output directory a volume mount point
# so reports persist across container restarts
VOLUME ["/app/output", "/app/watchlist"]

# Use venv Python for all commands
ENV PATH="/app/venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Streamlit config — disable telemetry, set server options
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ENABLE_CORS=false
ENV STREAMLIT_THEME_BASE=light

# Switch to non-root user
USER bharatalpha

EXPOSE 8501

# Health check — hits the Streamlit health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--browser.gatherUsageStats=false"]