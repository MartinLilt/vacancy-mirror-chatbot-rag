# =============================================================================
# Multi-stage build for backend image
# Stage 1: Build dependencies
# Stage 2: Runtime with minimal packages
# =============================================================================

# -----------------------------------------------------------------------------
# Build stage — install dependencies with build tools
# -----------------------------------------------------------------------------
FROM python:3.13-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

# Install CPU-only PyTorch first to avoid pulling the 2 GB CUDA stack.
# sentence-transformers will reuse this torch installation.
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -e .

# -----------------------------------------------------------------------------
# Runtime stage — minimal runtime dependencies only
# -----------------------------------------------------------------------------
FROM python:3.13-slim

# Install only runtime libraries (no gcc, no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

# Create non-root user (best practice)
# Note: Some containers may need root for specific operations,
# but for read_only containers this is safer.
RUN groupadd -r backend && useradd -r -g backend backend && \
    chown -R backend:backend /app

# Switch to non-root user
USER backend

ENV LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "backend.cli"]
