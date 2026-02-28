# ============================================================
# BharatAlpha — Dockerfile (single-stage)
# ============================================================
# WHY SINGLE-STAGE:
#   Multi-stage builds copy the venv from a builder image whose
#   Python lives at /usr/local/bin/python. The runtime image's
#   Python is at the same path, BUT the venv's internal symlinks
#   (bin/python → /usr/local/bin/python) become broken after the
#   COPY --from=builder because the venv was created in a different
#   filesystem context. Result: "no such file or directory" on every
#   venv binary (streamlit, pip, etc.).
#
#   Single-stage: build tools are installed, pip runs, build tools
#   are purged in the same RUN layer — no broken symlinks possible.
#
# Base: python:3.11-slim
# Exposes: 8501 (Streamlit)
# ============================================================

FROM python:3.11-slim

# ── System dependencies ───────────────────────────────────────
# Build tools needed at pip-install time (lxml, cryptography, grpcio).
# We purge them afterwards in the same RUN layer so they don't
# bloat the final image — only the compiled .so files remain.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    libxml2-dev \
    libxslt1-dev \
    libxml2 \
    libxslt1.1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root user ─────────────────────────────────────────────
# -m creates /home/bharatalpha automatically.
# CrewAI's LTMSQLiteStorage calls db_storage_path() at import time
# and tries to mkdir ~/.local/share/app — needs a real home dir.
RUN groupadd -r bharatalpha && \
    useradd -r -g bharatalpha -m -d /home/bharatalpha bharatalpha && \
    mkdir -p /home/bharatalpha/.local/share/app && \
    chown -R bharatalpha:bharatalpha /home/bharatalpha

# ── Python dependencies ───────────────────────────────────────
WORKDIR /app

# Copy requirements first so pip layer is cached independently
# of application code changes.
COPY requirements.txt .

# Install into the system Python (no venv needed in single-stage).
# --no-cache-dir keeps image lean.
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    # Purge ONLY C build tools — setuptools and pkg_resources MUST
    # remain: CrewAI telemetry.py does "import pkg_resources" at
    # runtime (crewai/telemetry/telemetry.py line 20). Removing
    # setuptools removes pkg_resources and crashes the pipeline.
    apt-get purge -y --auto-remove \
    build-essential gcc g++ \
    libffi-dev libssl-dev libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/* /root/.cache/pip && \
    python -c "import pkg_resources; print('pkg_resources OK')"

# ── Application code ──────────────────────────────────────────
# NOTE: .env is intentionally NOT copied — credentials are injected
# at runtime via docker run -e flags from Jenkins credentials store.
COPY config/   /app/config/
COPY src/      /app/src/
COPY app.py    /app/app.py

# ── Directory ownership ───────────────────────────────────────
RUN mkdir -p /app/output /app/watchlist && \
    chown -R bharatalpha:bharatalpha /app

# ── Volumes ───────────────────────────────────────────────────
VOLUME ["/app/output", "/app/watchlist"]

# ── Environment ───────────────────────────────────────────────
ENV PYTHONPATH="/app"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ENABLE_CORS=false
ENV STREAMLIT_THEME_BASE=light

# ── Runtime ───────────────────────────────────────────────────
USER bharatalpha

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["python", "-m", "streamlit", "run", "app.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--browser.gatherUsageStats=false"]