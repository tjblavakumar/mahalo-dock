# MAHALO-dock — Specification

> **Read this first.** This document and its siblings (`mahalo-dock-plan.md`,
> `mahalo-dock-progress.md`) are the single source of truth for the MAHALO-dock
> effort. They were authored in a planning session and written to disk so any
> future Kiro session can resume with **zero prior conversation context**.
>
> **Where this belongs:** these files were created inside the old `mahalo3`
> workspace and are meant to be moved into the new repo at
> `/mnt/ONETBSSD/ai/mahalo-dock/` (e.g. kept as `mahalo-dock-docs/` at the repo
> root, or converted into a Kiro spec under `.kiro/specs/mahalo-dock/`).

## Overview

MAHALO-dock packages the entire MAHALO3 concept as **one deployable unit** — a
single `docker compose up` that brings up the frontend, backend, the four mock
services, and a **real self-hosted Gitea git server**. The mock GitHub service
is evolved into an **adapter** that preserves MAHALO's existing HTTP contract
but, in "real" mode, is backed by Gitea — giving real repositories, branches,
commits with real file contents, and real pull requests. The goal is to demo
the concept locally on both Windows 11 and Zorin Linux, with the local machine
providing LLM access.

In the real world (out of scope here) the mocks are later swapped for real
GitHub/Confluence via API/MCP; the adapter pattern built here is the template.

## Confirmed decisions (from planning)

- **1 = a** — MAHALO-dock is a **fresh standalone GitHub repo** named
  `MAHALO-dock`, created with **clean history** copied from MAHALO3.
- **2 = b** — "Check in code" means the **agent/LLM provides real file contents**
  that are committed into the repo (not metadata-only). Real PR creation included.
- **3 = a** — **Everything is containerized including Gitea.** The github mock
  becomes the adapter. Jira / Confluence / ServiceNow stay as mocks.
- **One deployable unit** = one `docker compose up`, multiple containers (NOT one
  giant container). This was explicitly chosen over a single supervisord image.
- **Cross-platform:** must run on Windows 11 (Docker Desktop) and Zorin Linux
  (Docker Engine). LLM calls go to external APIs, so network is required at demo
  time; everything else is local.
- **Mode switch:** `GITHUB_MODE=mock|real` so the old offline in-memory mock
  still works for network-free demos.
- **Seed:** a sample repo is seeded into Gitea on first boot so there is
  something to branch/commit/PR against immediately; the developer adds
  LLM-generated code during the demo.
- **Secrets:** must never be committed. `.env` is gitignored; the published repo
  ships only a sanitized `.env.example`.
- **Folder location:** new repo lives at `/mnt/ONETBSSD/ai/mahalo-dock` (sibling
  of the old `/mnt/ONETBSSD/ai/mahalo3`), chosen for clean separation.

## Requirements

1. A single command (`docker compose up`) starts the whole stack: frontend,
   backend, mock-jira, mock-confluence, mock-servicenow, the github adapter,
   Gitea, and a one-shot Gitea bootstrap.
2. The github service exposes the **exact existing contract** on port 5003 with
   `X-API-Token` auth, so MAHALO's agent tools, proxy, and dashboard are
   unchanged. Endpoints to preserve:
   - `GET /health`
   - `GET /repos`, `POST /repos`, `GET /repos/{repo_id}`
   - `GET /repos/{repo_id}/branches`, `POST /repos/{repo_id}/branches`
   - `GET /pulls`, `GET /repos/{repo_id}/pulls`, `GET /repos/{repo_id}/pulls/{pr_number}`
   - `GET /repos/{repo_id}/commits`, `POST /repos/{repo_id}/commits`
   - `POST /repos/{repo_id}/readme`
   - `GET /repos/{repo_id}/stats`
3. `GITHUB_MODE=mock` reproduces today's JSON-store behavior exactly.
   `GITHUB_MODE=real` translates the contract to Gitea's REST API.
4. In real mode: real repos, real branches, **real file-content commits**, and
   **real pull requests**, all visible in the Gitea web UI.
5. New agent capabilities: commit files and open a PR via the chatbot, routed
   through the existing propose → approve → execute flow.
6. Gitea bootstrap is idempotent (safe to re-run): admin user, API token, and a
   seeded sample repository with initial real files.
7. No secrets in the committed tree; sanitized `.env.example` only.

## Non-goals

- Replacing Jira / Confluence / ServiceNow with real backends (stay mocks).
- Real github.com integration (that is the later API/MCP phase).
- A single-container (supervisord) image — explicitly rejected in favor of Compose.

## Key architecture facts (verified in the MAHALO3 codebase)

- A working `docker-compose.yml` already exists with Dockerfiles for backend,
  frontend, and all four mocks, using service-name networking
  (e.g. `http://mock-github:5003`) and healthchecks. The plan **extends** it.
- `backend/app/core/config.py` reads service URLs + LLM config from env vars;
  `mock_github_url` defaults to `http://localhost:5003`.
- The github mock (`mock-services/github/main.py`) is FastAPI with a JSON store
  (`store.py` + `seed_data.py`) persisting to `data.json`.
- Agent **reads** call the service directly via `_make_github_request` in
  `backend/app/agent/tools/github_tools.py`. Dashboard reads go through
  `backend/app/routers/proxy.py` (GET-only).
- **Writes** return a `__PROPOSAL__{json}__END_PROPOSAL__` blob from the tool;
  after user approval, `execute_proposed_action` in
  `backend/app/agent/agent.py` POSTs to the service. Today **only
  `create_branch`** is wired end-to-end; commits are metadata-only; **there is
  no PR-create tool or endpoint**.
- Approve/reject is handled in `backend/app/routers/chat.py`.
- Write-tool conventions are documented to the orchestrator in
  `backend/app/agent/prompts.py`.

## Architecture (target)

```
docker compose up
  frontend :3000  ──> backend :8008
  backend ──> mock-jira :5001
  backend ──> mock-confluence :5002
  backend ──> mock-servicenow :5004
  backend ──> github-adapter :5003   (GITHUB_MODE=mock|real)
  github-adapter ──(real)──> gitea :3000   (host-exposed e.g. :3001)
  gitea-bootstrap ──seeds──> gitea
  gitea ── named volume (data persists)
```

The adapter and Gitea are **separate containers**. The adapter keeps the
`X-API-Token` + `/repos/...` contract; Gitea is the real git/PR engine behind it.
