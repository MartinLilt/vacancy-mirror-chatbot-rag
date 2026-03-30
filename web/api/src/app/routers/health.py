"""Health check router."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Return service health status."""
    return {"status": "ok"}
