"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Return health status of the backend service."""
    return {
        "status": "healthy",
        "service": "mahalo3-backend",
        "version": "0.1.0",
    }
