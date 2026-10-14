"""Integration router: CRUD operations and connection testing."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.integration import Integration
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.integration import (
    IntegrationCreateRequest,
    IntegrationResponse,
    IntegrationTestResponse,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.post("", response_model=IntegrationResponse, status_code=status.HTTP_201_CREATED)
def create_integration(
    request: IntegrationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register a new integration connection."""
    integration = Integration(
        user_id=current_user.id,
        type=request.type,
        name=request.name,
        url=request.url,
        token=request.token,
        project_scope=request.project_scope,
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


@router.get("", response_model=list[IntegrationResponse])
def list_integrations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all integrations for the current user."""
    integrations = (
        db.query(Integration)
        .filter(Integration.user_id == current_user.id)
        .all()
    )
    return integrations


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration(
    integration_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove an integration."""
    integration = (
        db.query(Integration)
        .filter(Integration.id == integration_id, Integration.user_id == current_user.id)
        .first()
    )
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )
    db.delete(integration)
    db.commit()


@router.post("/{integration_id}/test", response_model=IntegrationTestResponse)
async def test_integration(
    integration_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Test an integration connection by pinging its health endpoint."""
    integration = (
        db.query(Integration)
        .filter(Integration.id == integration_id, Integration.user_id == current_user.id)
        .first()
    )
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{integration.url}/health",
                headers={"X-API-Token": integration.token},
            )

        if response.status_code == 200:
            service_info = response.json()
            return IntegrationTestResponse(
                success=True,
                message=f"Successfully connected to {integration.name}",
                service_info=service_info,
            )
        elif response.status_code == 401:
            return IntegrationTestResponse(
                success=False,
                message="Authentication failed. Check your API token.",
            )
        else:
            return IntegrationTestResponse(
                success=False,
                message=f"Service returned status {response.status_code}",
            )
    except httpx.ConnectError:
        return IntegrationTestResponse(
            success=False,
            message=f"Could not connect to {integration.url}. Is the service running?",
        )
    except httpx.TimeoutException:
        return IntegrationTestResponse(
            success=False,
            message="Connection timed out. Service may be slow or unreachable.",
        )
    except Exception as e:
        return IntegrationTestResponse(
            success=False,
            message=f"Connection test failed: {str(e)}",
        )
