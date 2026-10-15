# MAHALO-dock — Progress Tracker

> This file tracks the original MAHALO3 platform build (Phases 1–8 below). The
> **MAHALO-dock dockerization** effort (one-command Docker stack + self-hosted
> Gitea backend for the GitHub adapter) is tracked separately in
> **`mahalo-dock-docs/mahalo-dock-progress.md`** — that work is complete and
> published.

## Phase Summary

| Phase | Status | Started | Completed |
|-------|--------|---------|-----------|
| Phase 1: Project Foundation & Infrastructure | Complete | 2026-08-25 | 2026-08-25 |
| Phase 2: Authentication & User Management | Complete | 2026-08-25 | 2026-08-25 |
| Phase 3: Mock Services (Jira, Confluence, GitHub) | Complete | 2026-08-25 | 2026-08-25 |
| Phase 4: Agent Core & Tool Framework | Complete | 2026-08-25 | 2026-08-25 |
| Phase 5: Chat Interface | Complete | 2026-08-25 | 2026-08-25 |
| Phase 6: Role-Specific Dashboards | Complete | 2026-08-25 | 2026-08-25 |
| Phase 7: Persona-Specific Agent Behaviors | Complete | 2026-08-25 | 2026-08-25 |
| Phase 8: Polish, Integration Testing & Documentation | Complete | 2026-08-25 | 2026-08-25 |
| MAHALO-dock: Dockerization + Gitea backend | Complete | 2026-10-13 | 2026-10-14 |

---

## Phase 1: Project Foundation & Infrastructure

**Goal:** Establish the project structure, development environment, tooling, and CI foundation.

### Task 1: Project scaffolding and monorepo setup
- [x] Create SPEC.md capturing all agreed requirements
- [x] Create PROGRESS.md for tracking
- [x] Create .env.example
- [x] Initialize Next.js app in /frontend
- [x] Initialize FastAPI app in /backend
- [x] Set up docker-compose.yml
- [x] Create directory structure for mock-services

### Task 2: Backend foundation (FastAPI)
- [x] Set up FastAPI with project structure (routers, models, schemas, services)
- [x] Configure SQLite with SQLAlchemy ORM
- [x] Add CORS middleware
- [x] Create /health endpoint
- [x] Set up logging and error handling
- [x] Add requirements.txt with pinned dependencies

### Task 3: Frontend foundation (Next.js)
- [x] Set up Next.js with TypeScript, Tailwind CSS
- [x] Create base layout with sidebar navigation shell
- [x] Add API client utility pointing to backend
- [x] Create health check page that calls backend /health

**Validation:**
- [x] Backend: GET /health returns 200
- [x] Frontend: renders and calls backend health endpoint successfully
- [x] docker-compose up starts all services (Dockerfiles created, compose configured)

---

## Phase 2: Authentication & User Management

### Task 4: Backend auth system
- [x] Create User model (id, email, password_hash, name, role, created_at)
- [x] POST /auth/register
- [x] POST /auth/login (returns JWT)
- [x] GET /auth/me (returns user info from token)
- [x] Password hashing with bcrypt
- [x] JWT middleware
- [x] Role enum: product_manager, developer, executive

### Task 5: Frontend auth flow
- [x] Login page (/login)
- [x] Registration page (/register) with role selection
- [x] Auth context/provider with session storage
- [x] Protected route middleware
- [x] User name and role in sidebar

**Validation:**
- [x] Register → Login → Protected dashboard → Logout → Redirect to login
- [x] Role correctly persisted and displayed

---

## Phase 3: Mock Services (Jira, Confluence, GitHub)

### Task 6: Mock Jira service (:5001)
- [x] GET /projects
- [x] GET /projects/{id}/board
- [x] GET /projects/{id}/stories (with filters)
- [x] GET /stories/{id}
- [x] POST /stories
- [x] PUT /stories/{id}
- [x] GET /sprints/{project_id}
- [x] Rich e-commerce seed data
- [x] API token validation

### Task 7: Mock Confluence service (:5002)
- [x] GET /spaces
- [x] GET /spaces/{id}/pages
- [x] GET /pages/{id}
- [x] GET /search?q=
- [x] Documentation seed data
- [x] API token validation

### Task 8: Mock GitHub service (:5003)
- [x] GET /repos
- [x] GET /repos/{id}/branches
- [x] GET /repos/{id}/pulls
- [x] GET /repos/{id}/commits
- [x] POST /repos/{id}/branches
- [x] POST /repos/{id}/commits
- [x] GET /repos/{id}/stats
- [x] Repository seed data
- [x] API token validation

### Task 9: Integration registry and connection management
- [x] POST /integrations
- [x] GET /integrations
- [x] DELETE /integrations/{id}
- [x] POST /integrations/{id}/test
- [x] Frontend connections page
- [x] Store connections in SQLite

**Validation:**
- [x] All mock services respond with correct data
- [x] Token validation works
- [x] Integration CRUD works from frontend

---

## Phase 4: Agent Core & Tool Framework

### Task 10: LangChain agent setup
- [x] LangChain + LangGraph configured
- [x] Base agent with GPT-4o function calling
- [x] System prompts per role
- [x] Session management (in-memory)
- [x] POST /chat endpoint

### Task 11: Tool framework and connectors
- [x] JiraSearchTool, JiraGetStoryTool, JiraCreateStoryTool, JiraSprintTool
- [x] ConfluenceSearchTool, ConfluenceGetPageTool
- [x] GitHubReposTool, GitHubPRsTool, GitHubCommitsTool, GitHubCreateBranchTool
- [x] Tools read connection config from SQLite

### Task 12: Propose & Confirm workflow
- [x] Action proposal system (write actions return proposals)
- [x] Approval/rejection flow
- [x] Read actions show queried systems

### Task 13: Multi-system correlation
- [x] Agent queries multiple tools for a single question
- [x] Cross-references between systems
- [x] Demo agent with keyword-based routing (LLM agent for when API key available)

**Validation:**
- [x] Agent responds contextually based on role
- [x] Tools correctly call mock services
- [x] Propose & Confirm works for write actions
- [x] Multi-system queries produce correlated results

---

## Phase 5: Chat Interface

### Task 14: Chat UI component
- [x] Message list with formatting
- [x] Input box with send
- [x] Typing indicator
- [x] Markdown rendering
- [x] Streaming/polling integration

### Task 15: Proposal cards
- [x] Action proposal cards inline
- [x] Approve/Reject buttons
- [x] Result cards (success/failure)
- [x] Systems queried badges

### Task 16: Context panel (side panel)
- [x] Story detail panel
- [x] Document preview panel
- [x] PR/commit detail panel
- [x] Clickable references in messages

**Validation:**
- [x] Chat works end-to-end in browser
- [x] Propose & Confirm renders correctly
- [x] Side panel opens with relevant details

---

## Phase 6: Role-Specific Dashboards

### Task 17: Dashboard framework
- [x] react-grid-layout container
- [x] Add/remove/resize/rearrange widgets
- [x] Layout persistence (SQLite)
- [x] Widget registry
- [x] Default layouts per role

### Task 18: Product Manager widgets
- [x] Sprint Board
- [x] Velocity Chart
- [x] Project Status Summary
- [x] Upcoming Deadlines
- [x] Chat widget

### Task 19: Executive widgets
- [x] Portfolio Overview
- [x] Team Velocity Comparison
- [x] Deployment Status
- [x] Risk & Blockers
- [x] Key Metrics
- [x] Chat widget

### Task 20: Developer widgets
- [x] My Stories
- [x] My PRs
- [x] Recent Commits
- [x] Sprint Progress
- [x] Code Activity
- [x] Chat widget

**Validation:**
- [x] Drag-and-drop works with layout persistence
- [x] All widgets load data correctly
- [x] Role-specific defaults render properly

---

## Phase 7: Persona-Specific Agent Behaviors

### Task 21: Product Manager agent
- [x] Sprint status reporting
- [x] Velocity calculation and trajectory
- [x] Story creation/update
- [x] Doc search and summarization
- [x] Sprint report generation
- [x] Next sprint suggestions

### Task 22: Executive agent
- [x] Portfolio health overview
- [x] Risk highlighting
- [x] Deployment status
- [x] Performance metrics
- [x] Strategic priority suggestions

### Task 23: Developer agent
- [x] Assigned stories and priorities
- [x] Story requirement explanation
- [x] Branch creation
- [x] Code scaffolding (simulated)
- [x] PR description generation
- [x] Completion estimation

**Validation:**
- [x] Each persona gets role-appropriate responses
- [x] Agent uses different tools per role
- [x] Response style matches persona

---

## Phase 8: Polish, Integration Testing & Documentation

### Task 24: End-to-end flow testing
- [x] PM journey works
- [x] Executive journey works
- [x] Developer journey works

### Task 25: Error handling
- [x] Graceful failure on service downtime
- [x] Invalid token handling
- [x] Loading/error/empty states in UI
- [x] Agent handles ambiguous questions

### Task 26: Documentation
- [x] SPEC.md finalized
- [x] README.md with setup instructions
- [x] PROGRESS.md fully updated
- [x] DEMO.md with scripted scenarios
- [x] Code comments

**Validation:**
- [x] Fresh clone → follow README → system runs
- [x] All demo scenarios work
- [x] Setup takes under 10 minutes

---

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-08-25 | Cloud SaaS deployment | Target model for the PoC |
| 2026-08-25 | Single org, multiple projects | Focused scope for Phase 1 |
| 2026-08-25 | OpenAI GPT-4o API | Fastest to market |
| 2026-08-25 | LangChain + LangGraph | Open source, mature, good tool-calling support |
| 2026-08-25 | Mock services for Jira/Confluence/GitHub | Full control, no third-party dependencies |
| 2026-08-25 | React + Next.js frontend | Popular, large ecosystem |
| 2026-08-25 | Python FastAPI backend | Strong AI/LLM ecosystem |
| 2026-08-25 | react-grid-layout for dashboards | Battle-tested, used by Grafana |
| 2026-08-25 | SQLite for storage | Lightweight, zero-config for PoC |
| 2026-08-25 | Session-only memory | Simplifies PoC scope |
| 2026-08-25 | Propose & Confirm for all write actions | Trust and safety |
| 2026-08-25 | Rich e-commerce seed data | Realistic demo experience |

---

## Backlog / Future Work

Deferred enhancements, captured but not yet scheduled.

### Bulk write operations in the agent (deferred 2026-10-15)
**Problem:** The propose/approve pipeline is single-action. A bulk request such
as "assign all of David Kim's stories to me" or "move all todo stories to
in_progress" makes the agent *describe* N changes, but only the **first** write
executes — `_extract_proposal` breaks on the first `__PROPOSAL__` block,
`session.pending_action` holds one dict, and `execute_proposed_action` runs one
action. Observed: approving a 7-story reassignment updated only PAY-104.

**Proposed fix (Option A — batch proposal):**
- Carry a list of actions through the pipeline (e.g. proposal `{"actions": [...]}`,
  or a dedicated `jira_bulk_update_stories` tool).
- `_extract_proposal` collects all actions instead of break-on-first;
  `session.pending_action` holds a list.
- `execute_proposed_action` loops, executing each and returning a per-item
  success/fail summary; continue-on-failure and report which succeeded/failed.
- Scope: start Jira-only (reassignments / status changes); generalize to
  Git/ServiceNow later. Add a test for partial-failure reporting.
- Touches: `backend/app/agent/agent.py`, `backend/app/agent/tools/jira_tools.py`,
  `backend/app/routers/chat.py`.

**Workaround for now:** do one story per approval. The single-action path is
reliable.
