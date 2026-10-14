# MAHALO3 — Architecture & System Flow

MAHALO3 is an AI-powered, multi-persona SDLC assistant. A Next.js frontend talks to a FastAPI backend, which runs a LangChain agent that orchestrates OpenAI (for tool-calling) plus a switchable synthesis LLM, calling out to four mock SDLC systems (Jira, Confluence, GitHub, ServiceNow).

## High-Level Architecture

```mermaid
graph TB
    subgraph client["🖥️ FRONTEND — Next.js 16 / React 19 (App Router)"]
        UI["Pages<br/>login · register · chat · dashboard · connections"]
        CTX["Contexts<br/>Auth · Connections · Project"]
        APIC["services/api.ts<br/>fetch wrapper + Bearer token"]
        STORE["sessionStorage<br/>mahalo3_token (JWT)"]
        UI --> CTX --> APIC
        APIC -.reads.-> STORE
    end

    subgraph backend["⚙️ BACKEND — FastAPI (Python)"]
        direction TB
        MW["CORS Middleware"]
        subgraph routers["Routers"]
            RAUTH["/auth"]
            RCHAT["/chat"]
            RPROJ["/projects"]
            RINTEG["/integrations"]
            RPROXY["/proxy"]
            RHEALTH["/health"]
        end
        AUTHSVC["auth_service<br/>bcrypt + JWT (HS256)"]
        GUARD["get_current_user<br/>(JWT dependency)"]

        subgraph agent["🤖 Agent Subsystem"]
            AGENT["agent.chat()<br/>orchestration loop"]
            SESS["session.py<br/>in-memory sessions"]
            SYNTH["synthesis.py<br/>rephrase answer"]
            PROMPTS["prompts.py<br/>role prompts"]
            TOOLS["tools/<br/>jira · confluence · github · servicenow"]
        end
    end

    subgraph data["💾 PERSISTENCE"]
        DB["SQLite (SQLAlchemy)<br/>users · integrations · projects"]
    end

    subgraph llm["🧠 LLM PROVIDERS"]
        OPENAI["OpenAI<br/>Orchestrator (tool-calling) — ALWAYS"]
        ONEMIN["1min.ai / OpenAI<br/>Synthesis — switchable"]
    end

    subgraph mocks["🔌 MOCK SDLC SYSTEMS (HTTP + X-API-Token)"]
        JIRA["Jira :5001"]
        CONF["Confluence :5002"]
        GH["GitHub :5003"]
        SNOW["ServiceNow :5004"]
    end

    APIC -->|"HTTPS + Bearer JWT"| MW --> routers
    RAUTH --> AUTHSVC
    routers --> GUARD --> DB
    RCHAT --> AGENT
    RPROXY -->|direct reads| mocks

    AGENT --> SESS
    AGENT --> PROMPTS
    AGENT --> TOOLS
    AGENT -->|tool-calling| OPENAI
    AGENT --> SYNTH --> ONEMIN
    TOOLS -->|httpx| mocks
    AGENT -.reads integrations/projects.-> DB
```

## Chat / Agent Request Flow (the core loop)

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Frontend (chat page)
    participant CH as /chat router
    participant AG as agent.chat()
    participant DB as SQLite
    participant OAI as OpenAI Orchestrator
    participant TL as Tools (httpx)
    participant MS as Mock System<br/>(Jira/Conf/GH/SNOW)
    participant SY as Synthesis LLM

    U->>FE: type message
    FE->>CH: POST /chat {message, session_id, project_id}<br/>Authorization: Bearer JWT
    CH->>CH: get_current_user (decode JWT)
    CH->>DB: resolve active Project + Integrations
    CH->>AG: chat(message, user, session, project)
    AG->>AG: get/create in-memory session
    AG->>AG: build tools (per integration) + role system prompt

    loop Agent loop (≤10 iterations)
        AG->>OAI: ainvoke(messages + tools)
        alt model requests tools
            OAI-->>AG: tool_calls
            AG->>TL: invoke tool
            TL->>MS: GET/POST + X-API-Token
            MS-->>TL: data
            TL-->>AG: ToolMessage result
        else final answer
            OAI-->>AG: response (no tool calls) → break
        end
    end

    alt WRITE action proposed
        AG-->>CH: proposal (__PROPOSAL__) — stored as pending_action
        CH-->>FE: ProposalCard (awaiting approval)
        U->>FE: Approve
        FE->>CH: POST /chat/approve {session_id, approved}
        CH->>MS: execute_proposed_action (real POST/PUT)
        MS-->>CH: created/updated
        CH-->>FE: success message
    else READ request
        AG->>SY: synthesize_response(answer, role)
        SY-->>AG: reformatted answer
        AG-->>CH: {response, systems_queried, session_id}
        CH-->>FE: rendered markdown
    end
```

## Authentication Flow

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Frontend
    participant AU as /auth router
    participant SVC as auth_service
    participant DB as SQLite

    U->>FE: register (email, password, name, role)
    FE->>AU: POST /auth/register
    AU->>SVC: bcrypt hash password
    AU->>DB: insert User (409 if email exists)

    U->>FE: login (email, password)
    FE->>AU: POST /auth/login
    AU->>DB: load user
    AU->>SVC: verify bcrypt password
    SVC-->>AU: create JWT (HS256, sub=user.id, 60 min)
    AU-->>FE: {access_token}
    FE->>FE: store token in sessionStorage

    Note over FE,DB: Every protected call sends Authorization: Bearer <JWT>.<br/>get_current_user decodes it and loads the User.
```

## Component Responsibilities

### Frontend — Next.js 16 / React 19 (App Router)
- **Pages** (`src/app`): public `login` / `register`, and a `(protected)` route group guarding `chat`, `dashboard`, `connections`.
- **Contexts**: `AuthContext` (token restore/login/logout), `ConnectionsContext`, `ProjectContext`.
- **`services/api.ts`**: thin `fetch` client; injects `Authorization: Bearer <token>` from `sessionStorage`, normalizes FastAPI errors. Base URL `NEXT_PUBLIC_API_URL` (default `http://localhost:8008`).

### Backend — FastAPI
- **`main.py`**: builds the app, adds CORS, registers routers, and on startup runs `init_db()` + `validate_llm_config()`.
- **Routers**: `/auth` (register/login/me + `get_current_user`), `/chat` (agent entry, suggestions, approve), `/projects` (CRUD, proposal, sync, bootstrap mock data), `/integrations` (CRUD + test), `/proxy` (direct authenticated reads of mock systems), `/health`.
- **`auth_service.py`**: bcrypt hashing + python-jose JWT (HS256).
- **Models** (SQLAlchemy over SQLite): `User`, `Integration` (per-user external system URL + token), `Project` (cross-system link keys).

### Agent Subsystem (`app/agent`)
- **`agent.py`**: the AI core — builds tools from the user's integrations, runs the OpenAI tool-calling loop (≤10 iterations), detects write proposals, hands off to synthesis, and executes approved actions.
- **`session.py`**: in-memory sessions (`_sessions` dict) holding message history and a single `pending_action`. Not persisted.
- **`synthesis.py`**: rephrases the orchestrator's answer via the switchable provider; falls back to the raw answer on failure.
- **`onemin_llm.py`**: custom LangChain chat model wrapping 1min.ai's `/api/chat-with-ai` (no function calling — synthesis only).
- **`prompts.py`**: base rules + role-specific prompts (product_manager / developer / executive).
- **`markup_utils.py`**: parses text-emitted tool calls and strips tool markup from user-facing text.
- **`demo_agent.py`**: keyword-based fallback when no OpenAI key is configured.
- **`tools/`**: factories returning LangChain tools bound to an integration's URL + token, calling mock services over httpx with `X-API-Token`.

## Key Architectural Decisions

- **Dual-LLM split.** The orchestrator is *always* OpenAI because it needs native function calling to decide which tools to invoke. Synthesis (final phrasing) is a switchable provider (`onemin` by default, falling back to OpenAI). This separates the reasoning brain from the presentation layer.

- **Propose-and-confirm writes.** Read operations execute immediately, but any write (create story, update story, create branch, create incident) returns a `__PROPOSAL__` sentinel instead of executing. The proposal is held on the session's `pending_action` and only runs after the user approves via `/chat/approve`. This is the human-in-the-loop safety gate.

- **Dynamic tool wiring.** On each request, `agent.chat()` reads the user's `Integration` rows and builds tools bound to each integration's URL + token. A user only gets Jira tools if they've connected Jira.

- **Two paths to the mock systems.** The agent tools (LLM-driven, read + write) and the `/proxy` routes (direct authenticated reads the dashboard uses without invoking the agent).

- **In-memory sessions.** Conversation history and pending actions live in a process-level dict, not the DB. Restarting the backend clears all conversations — a deliberate PoC tradeoff. The DB persists only users, integrations, and projects.

- **Stateless auth.** JWT (HS256, `sub=user.id`, 60-min expiry) stored in `sessionStorage`, sent as a Bearer token on every call, decoded by the `get_current_user` dependency on protected routes.

## External Systems

| System | Default Port | Reads | Writes (via proposal) |
|--------|--------------|-------|-----------------------|
| Jira | :5001 | projects, stories, sprints, boards, developers | create/update story |
| Confluence | :5002 | spaces, pages, search | — (read-only) |
| GitHub | :5003 | repos, PRs, commits, stats | create branch |
| ServiceNow | :5004 | deployments, incidents, stats | create incident |

Plus the LLM providers: **OpenAI** (orchestrator, mandatory) and **1min.ai** (default synthesis, switchable to OpenAI).
