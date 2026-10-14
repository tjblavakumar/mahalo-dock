# MAHALO-dock — One-Command AI SDLC Platform (Dockerized)

MAHALO-dock packages the entire MAHALO platform as **one deployable unit**. A single
`docker compose up` brings up the frontend, backend, the four mock services, and a
**real self-hosted [Gitea](https://about.gitea.com/) git server**. The GitHub mock is
evolved into an **adapter**: it keeps MAHALO's existing HTTP contract but, in its default
"real" mode, is backed by Gitea — so the chatbot creates **real repositories, branches,
commits (with real file contents), and pull requests** you can open in a browser.

It runs the same way on **Windows 11** (Docker Desktop) and **Zorin / Ubuntu Linux**
(Docker Engine). The only thing that needs the internet at demo time is the LLM API call;
everything else is local.

Multi-persona: Product Managers, Developers, and Executives chat with an AI agent connected
to Jira, Confluence, GitHub (→ Gitea), and ServiceNow. It correlates information across
systems, performs actions with user approval, and presents role-specific dashboards.

---

## 🚀 Run with Docker (recommended)

This is the canonical way to run MAHALO-dock.

### Prerequisites

| OS | What to install |
|----|-----------------|
| **Windows 11** | [Docker Desktop](https://docs.docker.com/desktop/install/windows-install/) (includes Compose v2). Use a PowerShell or Git-Bash terminal. |
| **Zorin / Ubuntu Linux** | [Docker Engine](https://docs.docker.com/engine/install/ubuntu/) + the Compose plugin. Add your user to the `docker` group (`sudo usermod -aG docker $USER`, then log out/in) so you can run `docker` without `sudo`. |

Verify your install:

```bash
docker version
docker compose version   # must be Compose v2 (note: "compose", not "docker-compose")
```

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set your LLM credentials (see [LLM Configuration](#llm-configuration)). At
minimum `OPENAI_API_KEY` is required — the orchestrator uses OpenAI-style function calling.
All other defaults in `.env.example` are good to go for a local demo.

### 2. Bring up the whole stack

```bash
docker compose up --build
```

First run pulls the Gitea image and builds the app images, then starts everything in
dependency order: Gitea boots → a one-shot **bootstrap** creates an admin user, an API
token, and a seeded `payment-service` repo → the GitHub adapter comes up in **real** mode
wired to Gitea → backend, mocks, and frontend start.

Add `-d` to run detached. Shut down with `docker compose down` (add `-v` to also wipe the
Gitea data + bootstrap volumes for a totally fresh start).

**Convenience wrappers** (optional — they just call `docker compose` and auto-create `.env`
from the example on first run):

```bash
# Linux / macOS                 # Windows 11
./docker-up.sh                  docker-up.bat          # real mode, detached
./docker-up.sh mock             docker-up.bat mock     # offline mock mode
./docker-down.sh                docker-down.bat        # stop (keep data)
./docker-down.sh --wipe         docker-down.bat --wipe # stop + wipe Gitea data
```

### 3. Ports

| Service | URL | Notes |
|---------|-----|-------|
| Frontend | http://localhost:3000 | Override with `FRONTEND_PORT` if 3000 is taken |
| Backend API | http://localhost:8008 | |
| Gitea web UI | http://localhost:3001 | Login `mahalo_admin` / `MahaloDock123!` (from `.env`) |
| GitHub adapter | http://localhost:5003 | `X-API-Token` contract |
| Mock Jira / Confluence / ServiceNow | :5001 / :5002 / :5004 | |

> **Port 3000 already in use?** If you have a local dev server running, set
> `FRONTEND_PORT=3010` (or any free port) in `.env` before `docker compose up`.

### 4. GITHUB_MODE — real (Gitea) vs mock (offline)

The adapter has two interchangeable backends, selected by `GITHUB_MODE`:

- **`real` (default):** backed by the self-hosted Gitea. Real repos/branches/commits/PRs.
- **`mock`:** the original in-memory JSON store — fully offline, no Gitea needed.

Run the fully offline / Gitea-free variant with the provided override:

```bash
docker compose -f docker-compose.yml -f docker-compose.mock.yml up \
    backend frontend mock-jira mock-confluence mock-github mock-servicenow
```

(The override forces `GITHUB_MODE=mock` and drops the Gitea dependency, so Gitea and the
bootstrap simply aren't started.)

### 5. First-time app setup

Open the frontend, then:

1. **Register** at `/register` (pick a role: Product Manager, Developer, or Executive).
2. **Login** at `/login`.
3. **Connect integrations** on the Connections page (`/connections`) using these
   browser-reachable host URLs:
   - Jira — URL `http://localhost:5001`, Token `mock-jira-token-12345`
   - Confluence — URL `http://localhost:5002`, Token `mock-confluence-token-12345`
   - GitHub — URL `http://localhost:5003`, Token `mock-github-token-12345`
   - ServiceNow — URL `http://localhost:5004`, Token `mock-servicenow-token-12345`

   (These tokens are the local demo defaults from `.env.example`.)

### 6. Demo script — real code check-in to Gitea

As a **Developer**, in the chat:

1. *"List my repositories"* → shows `payment-service` (served from Gitea).
2. *"Show recent commits on payment-service"* → real commit history from Gitea.
3. *"Create a branch feature/PAY-500-coupons on payment-service"* → approve the proposal.
4. *"Write a coupon validation module and commit it to that branch"* → the agent generates
   code and proposes a commit of real file contents; approve it.
5. *"Open a pull request from that branch into main"* → approve; the reply includes a
   clickable PR link.
6. Open **http://localhost:3001** and view the branch, the committed file, and the PR in
   the Gitea web UI.

> The LLM calls (steps that generate code/decide tools) require network access. The
> Gitea/branch/commit/PR operations are entirely local.

---

## Run without Docker (manual, MAHALO3-style)

<details>
<summary>Expand: run each service directly with Python/Node (no containers, no Gitea)</summary>

### Prerequisites
- Python 3.11+
- Node.js 20+
- npm

### Fastest path (all services at once)

Convenience scripts start every mock service, the backend, and the frontend together:

```bash
# Windows
start_all.bat

# macOS / Linux
./start_all.sh
```

Stop everything with `stop_all.bat` / `./stop_all.sh`.

> The first time, create each service's virtual environment and install its `requirements.txt` (see the manual steps below). After that, the start scripts handle the rest.

### 1. Configure environment

```bash
cp .env.example .env
```

Then edit `.env` and set your LLM credentials (see [LLM Configuration](#llm-configuration)). At minimum, `OPENAI_API_KEY` is required — the orchestrator uses OpenAI for tool calling.

### 2. Start Mock Services (manual)

```bash
# Terminal 1 - Mock Jira
cd mock-services/jira
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 5001

# Terminal 2 - Mock Confluence
cd mock-services/confluence
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 5002

# Terminal 3 - Mock GitHub
cd mock-services/github
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 5003

# Terminal 4 - Mock ServiceNow
cd mock-services/servicenow
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 5004
```

### 3. Start Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8008
```

### 4. Start Frontend

```bash
cd frontend
npm install
npm run dev
```

### 5. Access the Application

Open http://localhost:3000 in your browser.

1. **Register** — Create an account at `/register` (choose your role: Product Manager, Developer, or Executive)
2. **Login** — Sign in at `/login`
3. **Connect Integrations** — Go to Connections page (`/connections`) and add:
   - Jira: URL `http://localhost:5001`, Token `mock-jira-token-12345`
   - Confluence: URL `http://localhost:5002`, Token `mock-confluence-token-12345`
   - GitHub: URL `http://localhost:5003`, Token `mock-github-token-12345`
   - ServiceNow: URL `http://localhost:5004`, Token `mock-servicenow-token-12345`
4. **Create & Manage Projects** — Under the Connections page, click **"+ Create New Project"** to define custom initiatives. The system proposes unique system keys and auto-bootstraps initial Jira stories, Confluence documentation, and GitHub repositories.
5. **Dashboard** — Select one or multiple projects via the sidebar or Connections page to view real-time aggregated metrics across all your active initiatives.
6. **Chat** — Interact with the AI agent to query cross-system telemetry, write stories, compare projects, and propose actions.

</details>

## Architecture

```
Frontend (Next.js :3000)  →  Backend (FastAPI :8008)  →  Mock Services
                                    ↕                     ├── Jira (:5001)
                        SQLite + Agent Orchestrator       ├── Confluence (:5002)
                                    ↕                     ├── GitHub adapter (:5003)
                     OpenAI (orchestrator/tool calling)   │     └─(real)→ Gitea (:3001)
                     1min.ai (response synthesis)          └── ServiceNow (:5004)
```

The **GitHub adapter** keeps MAHALO's `X-API-Token` + `/repos/...` contract on :5003, but
dispatches by `GITHUB_MODE`:
- **real** → translates each call to Gitea's REST API (real git/PR engine behind it),
- **mock** → the original in-memory JSON store (offline).

A one-shot `gitea-bootstrap` container provisions Gitea on first boot (admin user, API
token, seeded repo) and writes the token to a volume the adapter reads. Gitea data persists
in a named volume. The adapter and Gitea run as **separate containers**.

The agent uses a **mixed-provider** model: OpenAI drives the orchestrator (deciding which
tools to call from the user's intent, via native function calling), while a switchable
synthesis provider phrases the final answer. Each mock service persists its data to a
JSON store, so changes survive restarts.

## Project Structure

```
mahalo-dock/
├── frontend/               # Next.js + React + Tailwind
├── backend/                # FastAPI + SQLAlchemy + LangChain
├── mock-services/
│   ├── jira/               # Mock Jira (:5001)
│   ├── confluence/         # Mock Confluence (:5002)
│   ├── github/             # GitHub adapter (:5003) — mock | real (Gitea) backends
│   ├── gitea-bootstrap/    # One-shot Gitea provisioning (admin + token + seed repo)
│   └── servicenow/         # Mock ServiceNow (:5004) — deployments + incidents
├── docker-compose.yml      # Full stack: frontend, backend, mocks, Gitea, bootstrap
├── docker-compose.mock.yml # Override: offline mock mode (no Gitea)
├── generate_mock_data.py   # Generate correlated mock data across all systems (1min.ai)
├── start_all.bat/.sh       # Start every service at once (non-Docker path)
├── stop_all.bat/.sh        # Stop every service (non-Docker path)
└── mahalo-dock-docs/       # Spec, plan, and progress tracker for the dockerization
```

The GitHub adapter directory (`mock-services/github/`) contains:
- `main.py` — the FastAPI contract + `GITHUB_MODE` dispatch
- `backend_base.py` — the common backend interface
- `mock_backend.py` — in-memory JSON store backend (offline)
- `gitea_backend.py` — Gitea-backed backend (real repos/branches/commits/PRs)

Each mock service directory contains:
- `seed_data.py` — the curated starting dataset (source of truth for a clean state)
- `store.py` — JSON-backed persistence (loads `data.json`, or seeds it on first run)
- `data.json` — runtime state (gitignored; recreated from the seed on first start)

## Features

### Per Persona
- **Product Manager**: Multi-project sprint boards with tabbed switching, velocity charts, completion progress, story creation & proposals
- **Executive**: Multi-project portfolio overview, aggregate key metrics with project breakdowns, cross-initiative risk assessment, production deployment & incident health
- **Developer**: Assigned stories, open PRs, recent commits, feature branch proposals

### Dynamic Project Management & Resource Bootstrapping
- **Project Scope Engine**: Users can manage multiple projects (e.g. Payment Gateway, Shopping Cart, Customer Expansion, etc.) under unified service connections.
- **Automated Resource Bootstrapping**: Creating a project automatically initializes the corresponding project in Jira (with setup stories), Confluence space (with project overview pages), and GitHub repo (with README.md).
- **Multi-Project Dashboard Aggregation**: Check/uncheck projects in the sidebar or Connections page to dynamically aggregate metrics across one, several, or all projects in real time.

### Connected Systems
- **Jira** — projects, sprints, stories, developers
- **Confluence** — spaces and documentation pages
- **GitHub** — repositories, pull requests, commits, contributor stats
- **ServiceNow** — deployments (per service/environment, success/failed/rolled_back) and
  incidents (P1–P4), aligned to the same services as the code repositories so they can be
  correlated (e.g. a failed deploy → the incident it caused → the linked story and PR)

### Agent Capabilities
- **Read**: Auto-queries Jira, Confluence, GitHub, and ServiceNow and presents correlated results
- **Write**: Proposes actions (create/update story, create branch, open incident) for user approval via interactive proposal cards
- **Multi-system & Multi-project**: A single prompt can search, compare, and correlate across all connected systems and user projects (e.g. *"what is common between project A and project B"*)
- **Dynamic starter prompts**: The chat empty-state shows context-aware suggestions instead of a fixed list. They're derived from the user's role, the scoped project (real names/keys injected), and which systems are actually connected (e.g. no GitHub → no PR prompts), and recompute whenever that context changes. A **"Generate more"** button fetches fresh LLM-written suggestions on demand (`POST /chat/suggestions`), with a deterministic fallback when no LLM key is configured
- **Robust Tool Invocation & Sanitization**: Handles structured function calling and parses/cleans raw LLM tool call tokens (such as DSML/XML tags) for seamless user-facing responses
- **Name resolution**: Resolves people by name (e.g. "Raj", "assigned to me") to the right account before filtering

## LLM Configuration

The agent splits work between two providers, configured in `.env`:

| Role | Provider | Purpose |
|------|----------|---------|
| **Orchestrator** | Always OpenAI | Decides which tools to call (requires native function calling) |
| **Synthesis** | `onemin` (default) or `openai` | Phrases the final response from tool results |

Models are chosen per role (see `.env.example`):

```
ORCHESTRATOR_MODEL=gpt-4o          # OpenAI model for tool calling
SYNTHESIS_PROVIDER=onemin          # onemin | openai
SYNTHESIS_MODEL=gpt-4o             # model for the synthesis provider

OPENAI_API_KEY=sk-...              # REQUIRED (orchestrator)
OPENAI_BASE_URL=https://api.openai.com/v1

ONEMIN_API_KEY=...                 # REQUIRED when SYNTHESIS_PROVIDER=onemin
ONEMIN_BASE_URL=https://api.1min.ai
```

Startup guardrails: the backend fails fast if `OPENAI_API_KEY` is missing, and automatically
falls back to OpenAI synthesis if `SYNTHESIS_PROVIDER=onemin` but no 1min.ai key is set.

## Mock Data Persistence

Each mock service stores its data in a JSON file (`mock-services/<svc>/data.json`), so any
changes made at runtime — e.g. a story created or an incident opened through the agent —
**persist across restarts**. The files are gitignored runtime state.

- **Fresh state**: delete a service's `data.json` (or set `MOCK_RESET_ON_START=true` in `.env`
  and start once) to rebuild from the curated `seed_data.py`.
- **Reset flag**: `MOCK_RESET_ON_START=true` wipes every mock's store back to its seed on the
  next start — handy for getting a clean, known state before a demo. Set it back to `false`
  afterward so changes made during the demo are kept.

## Generating Mock Data

`generate_mock_data.py` creates correlated data across all systems. It uses **1min.ai for the
text content** (titles, descriptions, messages) while wiring all IDs and cross-system links in
code, so the result is always referentially consistent (story → PR/commits → deployment →
incident). Generated text fields are capped at 250 characters.

```bash
python generate_mock_data.py \
    --jira-stories 20 --github-prs 8 --confluence-pages 6 \
    --servicenow-deployments 5 --servicenow-incidents 4 \
    [--append | --reset] [--seed 42] [--dry-run]
```

- **All count flags are required.**
- `--append` (default) adds on top of existing data; `--reset` rebuilds from the clean seed first.
- `--seed N` makes a run reproducible; `--dry-run` previews without writing.
- Reads `ONEMIN_API_KEY` from `.env`. If the key is missing (or `--dry-run`), it falls back to
  offline placeholder content so it never fails.

After generating, restart the mock services (they load the updated `data.json` on start).

### Environment Variables

See `.env.example` for all configuration. Key variables:
- `ORCHESTRATOR_MODEL`, `SYNTHESIS_PROVIDER`, `SYNTHESIS_MODEL` — LLM roles/models
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` — required for the orchestrator
- `ONEMIN_API_KEY` / `ONEMIN_BASE_URL` — required when synthesis uses 1min.ai
- `MOCK_RESET_ON_START` — reset all mock stores to seed on startup (default `false`)
- `JWT_SECRET_KEY` — secret for JWT token signing
- Mock service tokens default to `mock-{service}-token-12345`

> **Security note:** `.env` holds live API keys and is gitignored. Never commit it, and rotate
> keys if they've been exposed.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React, TypeScript, Tailwind CSS |
| Backend | Python, FastAPI, SQLAlchemy, SQLite |
| Agent | LangChain + OpenAI GPT-4o (orchestrator / tool calling) |
| Synthesis | 1min.ai or OpenAI (switchable) |
| Dashboard | react-grid-layout |
| Auth | JWT + bcrypt |
| Mock Services | FastAPI (independent services: Jira, Confluence, GitHub, ServiceNow) with JSON persistence |
