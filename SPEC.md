# MAHALO3 — Project Specification

## Overview

MAHALO3 is an AI-powered, multi-persona SDLC platform that allows Product Managers, Developers, and Executives to interact with a conversational agent. The agent connects live to multiple project management tools (Jira, Confluence, GitHub), retrieves and correlates information across systems, and performs actions on the user's behalf — all through role-specific customizable dashboards with embedded chat.

## Key Technical Decisions

| Aspect | Decision |
|--------|----------|
| Deployment | Cloud SaaS |
| Scale | Single org, multiple projects |
| LLM | OpenAI API (GPT-4o) |
| Agent Framework | LangChain + LangGraph (open source) |
| Frontend | React + Next.js, TypeScript, Tailwind CSS |
| Backend | Python FastAPI |
| Database | SQLite with SQLAlchemy |
| Dashboard | react-grid-layout (fully customizable drag-and-drop) |
| Auth | Simple email/password with JWT |
| Roles | product_manager, developer, executive |
| Agent Behavior | Always Propose & Confirm before write actions |
| Memory | Session-only (PoC scope) |
| Reports | Ephemeral (in-chat) |
| Data Refresh | On-demand with manual refresh button |
| Mock Services | Rich seeded data simulating e-commerce platform |
| Dev Workflow | Agent creates branches, user manages their own CI/CD |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Next.js Frontend :3000                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Dashboards  │  │     Chat     │  │  Draggable       │  │
│  │  (per role)  │  │  Interface   │  │  Widgets         │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI Backend :8000                       │
│  ┌──────┐  ┌──────────────┐  ┌───────────────────────────┐ │
│  │ Auth │  │  REST API    │  │  LangChain Agent +         │ │
│  │      │  │  Layer       │  │  LangGraph Orchestration   │ │
│  └──────┘  └──────────────┘  └─────────────┬─────────────┘ │
│                                             │               │
│                                    ┌────────┴────────┐      │
│                                    │  Tool Registry  │      │
│                                    └────────┬────────┘      │
└─────────────────────────────────────────────┼───────────────┘
                              │               │
                    ┌─────────┘               │
                    ▼                         ▼
              ┌──────────┐     ┌─────────────────────────────┐
              │  SQLite  │     │       Mock Services          │
              │          │     │  Jira :5001                  │
              └──────────┘     │  Confluence :5002            │
                               │  GitHub :5003                │
                               └─────────────────────────────┘
                                             │
                                             ▼
                               ┌─────────────────────────────┐
                               │       OpenAI API            │
                               └─────────────────────────────┘
```

## Personas (Phase 1)

### Product Manager
- Sprint planning, velocity tracking, status across integrations
- Story creation and management
- Cross-project reporting
- Dashboard widgets: Sprint Board, Velocity Chart, Project Status, Upcoming Deadlines, Chat

### Executive
- High-level project overview, deployment status, risk highlights
- Portfolio health across all projects
- Strategic insights and recommendations
- Dashboard widgets: Portfolio Overview, Team Velocity Comparison, Deployment Status, Risk & Blockers, Key Metrics, Chat

### Developer
- Story assignment and tracking
- Code generation and branch management
- PR management and commit tracking
- Dashboard widgets: My Stories, My PRs, Recent Commits, Sprint Progress, Code Activity, Chat

## Integrations (Mock Services)

All integrations connect via API tokens. For the PoC, mock services simulate real systems:

### Mock Jira (:5001)
- Projects, Sprints, Stories with full CRUD
- Rich e-commerce seed data: Payment Gateway, Shopping Cart, User Auth, Product Catalog, Order Management
- Stories in various states with story points and sprint assignments

### Mock Confluence (:5002)
- Spaces, Pages with search
- Seed data: ADRs, security guidelines, API specs, retrospectives, requirement docs

### Mock GitHub (:5003)
- Repos, Branches, PRs, Commits
- Seed data: Repos matching e-commerce projects with linked PRs and commit history

## Agent Behavior

1. **Read operations**: Auto-execute, show which systems were queried
2. **Write operations**: Always Propose & Confirm
   - Agent explains what it will do
   - Shows action card with parameters
   - User approves or rejects
   - On approval: execute and show result
   - On rejection: acknowledge and offer alternatives

## Chat Starter Prompts (Dynamic Suggestions)

The chat empty-state presents suggested starter prompts that adapt to context rather than a
fixed hardcoded list.

- **Drivers**: the user's role (`product_manager` / `developer` / `executive`), the scoped
  project (its real name and system keys are injected into templates), and the set of
  connected integrations (Jira / Confluence / GitHub / ServiceNow).
- **Filtering**: suggestions that reference a system the user hasn't connected are hidden
  (e.g. no GitHub connection → no pull-request prompts); project-referencing prompts are
  skipped when no project is scoped or a required key is missing.
- **Recompute-from-context**: the default (template) suggestions are deterministic and
  recompute whenever role, scoped project, or connections change — no random rotation.
- **Hybrid generation**: a **"Generate more"** action calls `POST /chat/suggestions`, which
  reuses the agent's role prompt, integrations context, and project context to have the LLM
  write fresh, grounded suggestions. When no OpenAI key is configured (or generation fails),
  the endpoint returns a deterministic, connection-aware fallback set. LLM output is tied to
  the current context and reverts to templates when that context changes.

## File Structure

```
mahalo3/
├── SPEC.md
├── PROGRESS.md
├── DEMO.md
├── README.md
├── docker-compose.yml
├── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   │   ├── chat/
│   │   │   ├── dashboard/
│   │   │   └── common/
│   │   ├── contexts/
│   │   ├── hooks/
│   │   ├── services/
│   │   └── types/
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── agent/
│   │   └── core/
│   └── requirements.txt
└── mock-services/
    ├── jira/
    ├── confluence/
    └── github/
```

## Phases

1. **Phase 1**: Project Foundation & Infrastructure
2. **Phase 2**: Authentication & User Management
3. **Phase 3**: Mock Services (Jira, Confluence, GitHub)
4. **Phase 4**: Agent Core & Tool Framework
5. **Phase 5**: Chat Interface
6. **Phase 6**: Role-Specific Dashboards
7. **Phase 7**: Persona-Specific Agent Behaviors
8. **Phase 8**: Polish, Integration Testing & Documentation
