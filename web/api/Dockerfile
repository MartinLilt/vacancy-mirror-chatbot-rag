# =============================================================================
# API Dockerfile — Placeholder/Not Implemented
# =============================================================================
# NOTE: This API container is currently not implemented or not used.
# The web/api/src/ directory is empty (no Python code).
#
# Options:
# 1. Remove this container from docker-compose.backend.yml if not needed
# 2. Implement proper FastAPI application in web/api/src/app/
# 3. Use backend container's API endpoints instead
#
# Current setup in docker-compose.backend.yml:
#   - api container binds to 127.0.0.1:8000
#   - nginx proxies / → 127.0.0.1:8000
#   - But there's no actual API code!
#
# TODO: Investigate if this is intentional or a bug.
# =============================================================================

FROM python:3.13-slim

WORKDIR /app

# Install minimal dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Install FastAPI + uvicorn
RUN pip install --no-cache-dir \
    fastapi>=0.111 \
    uvicorn[standard]>=0.30 \
    psycopg2-binary>=2.9 \
    python-dotenv>=1.0.0

# Placeholder API (returns 404 for now)
RUN echo 'from fastapi import FastAPI\n\
app = FastAPI(title="Vacancy Mirror API - Placeholder")\n\
\n\
@app.get("/health")\n\
async def health():\n\
    return {"ok": True, "message": "API placeholder - not implemented"}\n\
\n\
@app.get("/")\n\
async def root():\n\
    return {"error": "API not implemented", "status": 404}\n\
' > /app/main.py

# Create non-root user
RUN groupadd -r api && useradd -r -g api api && \
    chown -R api:api /app

USER api

ENV LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Run placeholder FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
