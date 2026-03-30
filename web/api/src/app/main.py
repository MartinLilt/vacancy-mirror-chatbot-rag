"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, webhook

app = FastAPI(
    title="Vacancy Mirror API",
    version="0.1.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://vacancy-mirror.com",
        "https://www.vacancy-mirror.com",
        "http://localhost:3000",  # Next.js dev
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(webhook.router)
