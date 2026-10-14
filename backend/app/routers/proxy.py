"""Proxy router: forwards requests to mock services using stored integration credentials."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.integration import Integration
from app.models.user import User
from app.routers.auth import get_current_user

router = APIRouter(prefix="/proxy", tags=["proxy"])


@router.get("/jira/{path:path}")
async def proxy_jira(
    path: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Proxy GET requests to the user's configured Jira integration."""
    integration = (
        db.query(Integration)
        .filter(Integration.user_id == current_user.id, Integration.type == "jira")
        .first()
    )
    if not integration:
        raise HTTPException(status_code=404, detail="No Jira integration configured")

    query_params = dict(request.query_params)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{integration.url}/{path}",
            headers={"X-API-Token": integration.token},
            params=query_params,
        )
    return response.json()


@router.get("/confluence/{path:path}")
async def proxy_confluence(
    path: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Proxy GET requests to the user's configured Confluence integration."""
    integration = (
        db.query(Integration)
        .filter(Integration.user_id == current_user.id, Integration.type == "confluence")
        .first()
    )
    if not integration:
        raise HTTPException(status_code=404, detail="No Confluence integration configured")

    query_params = dict(request.query_params)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{integration.url}/{path}",
            headers={"X-API-Token": integration.token},
            params=query_params,
        )
    return response.json()


@router.get("/github/{path:path}")
async def proxy_github(
    path: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Proxy GET requests to the user's configured GitHub integration."""
    integration = (
        db.query(Integration)
        .filter(Integration.user_id == current_user.id, Integration.type == "github")
        .first()
    )
    if not integration:
        raise HTTPException(status_code=404, detail="No GitHub integration configured")

    query_params = dict(request.query_params)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{integration.url}/{path}",
            headers={"X-API-Token": integration.token},
            params=query_params,
        )
    return response.json()


@router.get("/servicenow/{path:path}")
async def proxy_servicenow(
    path: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Proxy GET requests to the user's configured ServiceNow integration."""
    integration = (
        db.query(Integration)
        .filter(Integration.user_id == current_user.id, Integration.type == "servicenow")
        .first()
    )
    if not integration:
        raise HTTPException(status_code=404, detail="No ServiceNow integration configured")

    query_params = dict(request.query_params)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{integration.url}/{path}",
            headers={"X-API-Token": integration.token},
            params=query_params,
        )
    return response.json()
