FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir -e .

ENV LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "backend.cli"]
