"""Mock ServiceNow Service - Simulates a ServiceNow-style API for MAHALO3.

Tracks deployments and incidents, aligned to the same services (repos/projects)
and developers used by the JIRA/GitHub/Confluence mocks so data can be
correlated across systems.
"""

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

import store
from store import DEPLOYMENTS, INCIDENTS, SERVICES

app = FastAPI(title="Mock ServiceNow Service", version="1.0.0")

API_TOKEN = os.environ.get("MOCK_SERVICENOW_TOKEN", "mock-servicenow-token-12345")


def verify_token(x_api_token: Optional[str] = Header(None)):
    """Validate API token from request header."""
    if x_api_token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid API token")


# --- Health ---

@app.get("/health")
def health():
    return {"status": "healthy", "service": "mock-servicenow", "version": "1.0.0"}


# --- Services ---

@app.get("/services")
def list_services(x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    return {"services": SERVICES}


# --- Deployments ---

@app.get("/deployments")
def list_deployments(
    service: Optional[str] = Query(None),
    environment: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
):
    """List deployments with optional filters."""
    verify_token(x_api_token)

    deployments = list(DEPLOYMENTS)
    if service:
        deployments = [d for d in deployments if d["service"] == service]
    if environment:
        deployments = [d for d in deployments if d["environment"] == environment]
    if status:
        deployments = [d for d in deployments if d["status"] == status]

    deployments.sort(key=lambda d: d.get("deployed_at", ""), reverse=True)
    return {"deployments": deployments, "total": len(deployments)}


@app.get("/deployments/{deployment_id}")
def get_deployment(deployment_id: str, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    dep = next((d for d in DEPLOYMENTS if d["id"] == deployment_id), None)
    if not dep:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return dep


# --- Incidents ---

@app.get("/incidents")
def list_incidents(
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    service: Optional[str] = Query(None, description="Filter by affected_service"),
    assignee: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
):
    """List incidents with optional filters."""
    verify_token(x_api_token)

    incidents = list(INCIDENTS)
    if severity:
        incidents = [i for i in incidents if i["severity"] == severity]
    if status:
        incidents = [i for i in incidents if i["status"] == status]
    if service:
        incidents = [i for i in incidents if i["affected_service"] == service]
    if assignee:
        incidents = [i for i in incidents if i.get("assignee") == assignee]

    incidents.sort(key=lambda i: i.get("opened_at", ""), reverse=True)
    return {"incidents": incidents, "total": len(incidents)}


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    inc = next((i for i in INCIDENTS if i["id"] == incident_id), None)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return inc


class CreateIncidentRequest(BaseModel):
    title: str
    affected_service: str
    severity: str = "P3"
    description: str = ""
    assignee: Optional[str] = None
    linked_deployment: Optional[str] = None


@app.post("/incidents", status_code=201)
def create_incident(request: CreateIncidentRequest, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)

    # Validate the affected service exists.
    if not any(s["id"] == request.affected_service for s in SERVICES):
        raise HTTPException(status_code=404, detail="Unknown affected_service")

    # Generate the next incident ID.
    max_num = 2000
    for i in INCIDENTS:
        try:
            num = int(i["id"].split("-")[1])
            max_num = max(max_num, num)
        except (IndexError, ValueError):
            continue
    new_id = f"INC-{max_num + 1}"

    new_incident = {
        "id": new_id,
        "title": request.title,
        "severity": request.severity,
        "status": "open",
        "affected_service": request.affected_service,
        "assignee": request.assignee,
        "opened_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "resolved_at": None,
        "linked_deployment": request.linked_deployment,
        "description": request.description,
    }
    INCIDENTS.append(new_incident)
    store.save()
    return new_incident


class UpdateIncidentRequest(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None
    assignee: Optional[str] = None


@app.put("/incidents/{incident_id}")
def update_incident(
    incident_id: str,
    request: UpdateIncidentRequest,
    x_api_token: Optional[str] = Header(None),
):
    verify_token(x_api_token)
    inc = next((i for i in INCIDENTS if i["id"] == incident_id), None)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    if request.status is not None:
        inc["status"] = request.status
        if request.status == "resolved" and not inc.get("resolved_at"):
            inc["resolved_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if request.severity is not None:
        inc["severity"] = request.severity
    if request.assignee is not None:
        inc["assignee"] = request.assignee

    store.save()
    return inc


# --- Stats (for exec/portfolio views) ---

@app.get("/stats")
def get_stats(x_api_token: Optional[str] = Header(None)):
    """Portfolio-level deployment/incident health summary."""
    verify_token(x_api_token)

    by_status = {}
    for d in DEPLOYMENTS:
        by_status[d["status"]] = by_status.get(d["status"], 0) + 1

    open_incidents = [i for i in INCIDENTS if i["status"] != "resolved"]
    by_severity = {}
    for i in open_incidents:
        by_severity[i["severity"]] = by_severity.get(i["severity"], 0) + 1

    return {
        "total_deployments": len(DEPLOYMENTS),
        "deployments_by_status": by_status,
        "total_incidents": len(INCIDENTS),
        "open_incidents": len(open_incidents),
        "open_incidents_by_severity": by_severity,
    }
