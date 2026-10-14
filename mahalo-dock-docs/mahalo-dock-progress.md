# MAHALO-dock — Progress Tracker

> Companion to `mahalo-dock-spec.md` and `mahalo-dock-plan.md`. Update this file
> as tasks complete so any session can see exactly where things stand.
> Status legend: ✅ done · 🚧 in progress · ⬜ not started

## Phase 0 — Switchover (DONE ✅)

- ✅ **Task 0a** — MAHALO3 Sidebar nav reorder committed. (User chose to commit
  directly to `master` rather than open a PR.) `master` fast-forwarded
  `1005fc7..0b766c1`, pushed to GitHub, temp branch
  `feature/sidebar-project-selector-top` deleted (local + remote). `.env` never
  staged (gitignored).
- ✅ **Task 0b** — Clean copy created at `/mnt/ONETBSSD/ai/mahalo-dock` via rsync
  with exclusions (`.git`, `.env`/`.env.*`, `venv`, `node_modules`, `.next`,
  `.pids`, `*.db`, `__pycache__`, `.pytest_cache`, mock `data.json`).
  - Gotcha: rsync's `--exclude='.env.*'` also excluded `.env.example` (rsync has
    no gitignore-style `!` negation), so `.env.example` was copied back
    explicitly.
  - Secret scan of the copy returned **no matches**. `.env.example` has
    placeholder keys (`OPENAI_API_KEY=key`, `ONEMIN_API_KEY=key`).
- ✅ **Task 0c** — Fresh git repo initialized in `/mnt/ONETBSSD/ai/mahalo-dock`.
  Initial commit `b5a2de9` "chore: initial MAHALO-dock from MAHALO3 (clean
  history)", 130 files, working tree clean, branch `master`, **no remote
  attached** (GitHub repo creation deferred to Task 10). Verified `.env`
  gitignored, only `.env.example` staged among env files, no leaks.

## Phase 1 — Dockerization + Gitea (IN PROGRESS 🚧)

- ✅ **Task 1** — Gitea in Compose + persistent volume. Added `gitea` service to
  `docker-compose.yml`: image pinned `gitea/gitea:1.27.3` (newest stable on
  Docker Hub as of 2026-10), host port `3001:3000`, named volume `gitea-data`
  mounted at `/data`, first-run env config (`GITEA__security__INSTALL_LOCK=true`
  to skip the web installer, sqlite3 DB, registration disabled, SSH server off,
  `ROOT_URL`/`DOMAIN` from `GITEA_ROOT_URL`/`GITEA_DOMAIN` env with localhost
  defaults), healthcheck on `/api/healthz` (interval 10s, 10 retries, 30s
  start_period). Added `GITEA_DOMAIN` + `GITEA_ROOT_URL` to `.env.example`.
  Removed the obsolete top-level `version:` key from the compose file.
  - **Verified live** (Docker Engine 29.1.3, Compose v2.40.3 on Zorin):
    `docker compose config` parses clean; `docker compose up -d gitea` →
    container `Up (healthy)`; `GET :3001/api/healthz` → `status: pass`
    (database + cache ping pass); web UI `/` → HTTP 200, title "Gitea: Git with
    a cup of tea" (installer correctly skipped); `/api/v1/version` → `1.27.3`;
    volume `mahalo-dock_gitea-data` created and populated (`git/`, `gitea/`,
    `ssh/`).
  - **Env note:** this machine (`lalana`) was added to the `docker` group but the
    agent's shell predated it; commands were run via `sg docker -c "..."`. A full
    Kiro restart (not just window reload) will let plain `docker` work.
- ✅ **Task 2** — Gitea bootstrap (admin + token + seeded repo). New one-shot
  service `gitea-bootstrap` at `mock-services/gitea-bootstrap/` (Dockerfile +
  `bootstrap.sh`), built FROM `gitea/gitea:1.27.3` so the `gitea` CLI + shared
  `/data` volume are available (the FIRST admin can only be created via the CLI;
  the REST API cannot — verified). Script is idempotent:
  1. waits for `/api/healthz`; 2. `gitea admin user create` (as `git` user,
  `--config /data/gitea/conf/app.ini`), skips if the user exists; 3. creates an
  API token `mahalo-adapter` (scopes `write:repository`, `write:user`,
  `read:organization`), recreating it if present to get a usable secret;
  4. creates + seeds repo `payment-service` (auto_init + real files
  `README.md`, `src/payment.py`, `tests/test_payment.py`) via the contents API,
  skipping if the repo exists; 5. writes the token to a shared volume
  `gitea-bootstrap:/bootstrap/gitea_token` for the adapter to read.
  - Compose: added `gitea-bootstrap` service (`depends_on` gitea
    `service_healthy`, `restart: "no"`, mounts `gitea-data` + new
    `gitea-bootstrap` volume). Added `GITEA_ADMIN_*`, `GITEA_TOKEN_NAME`,
    `GITEA_SEED_REPO` to `.env.example` (local demo creds, not real secrets).
  - **Scope findings (verified against Gitea 1.27.3):** `write:repository` alone
    is enough for contents PUT/POST + branches/commits/PRs; creating a repo
    under the user (`POST /user/repos`) additionally needs `write:user`.
  - **Verified live:** fresh `down -v` → `up --build` → bootstrap exits **0**;
    admin + token + repo + 3 real files + 4 commits confirmed via API; token
    authenticates (whoami 200). **Idempotent re-run** exits 0, commit count
    stays 4 (no dup), exactly one `mahalo-adapter` token.
  - **Bug fixed during impl:** `curl -fsS` on the contents SHA-probe returns
    non-zero on an expected 404 and aborted the script under `set -e`; rewrote
    `put_file`/`repo_exists` to inspect HTTP codes explicitly instead of using
    `-f`.
- ✅ **Task 3** — GITHUB_MODE + mode-dispatching layer. Refactored
  `mock-services/github` into a backend-dispatch architecture while preserving
  the exact HTTP contract + `X-API-Token` auth:
  - `backend_base.py` — `GithubBackend` ABC (one method per operation) +
    `BackendError(status, detail)` so backends stay FastAPI-free.
  - `mock_backend.py` — original JSON-store logic lifted out of main.py behind
    the interface (default). Added `create_pull` (records a PR in the store) and
    moved the commit required-field validation here as explicit 422s (main.py
    now accepts a raw dict for commits so Task 5's file-contents shape can flow).
  - `gitea_backend.py` — stub; every method raises `BackendError(501, ...)` so
    real mode is observable and never silently falls back to mock data.
  - `main.py` — keeps all routing/auth/request-models; `_build_backend()` picks
    mock|real from `GITHUB_MODE` (default mock, unknown→mock+warn); `_call()`
    translates `BackendError`→`HTTPException`. Added `POST /repos/{id}/pulls`
    route (both modes). `/health` now reports `mode`. Added `httpx==0.27.2` to
    requirements for Task 4.
  - **Verified live** (built image, ran container both modes): mock mode is a
    clean regression — 5 repos, repo-1 has 5 branches/3 PRs/11 commits, 8 open
    PRs total, stats 35 commits/3 contributors, PR#142 title correct, missing
    token→401; writes work (branch 201, dup branch 409, commit 201 w/ author
    resolved, missing-field commit→422, create_pull→201 PR#145, readme 201).
    real mode: `/health` mode=real, all endpoints→501 stub, auth still 401.
    No external tests import the github mock internals (refactor self-contained).
- ✅ **Task 4** — Gitea backend READ endpoints. Implemented all GET operations
  in `gitea_backend.py` (`GiteaBackend`): `list_repos`, `get_repo`,
  `list_branches`, `list_pulls`, `list_all_pulls`, `get_pull`, `list_commits`,
  `get_stats`. Centralized httpx client (`_request` with BackendError
  translation, 404/5xx handling, pagination) + mapping helpers
  (`_map_repo/_map_branch/_map_pull/_map_commit`).
  - **Mapping decisions:** `repo_id` == Gitea repo *name* under `self.owner`
    (`payment-service` → `mahalo_admin/payment-service`). Commits use
    `?stat=true` for additions/deletions. Branch not available on Gitea's commit
    list, so `list_commits(branch=...)` passes the branch as `sha` and tags
    results. `get_stats` is **derived** from the commit history (group by
    author login, sum commits/additions/deletions) + branch count + open-PR
    count — matches the plan's "degrade gracefully."
  - **Gotcha fixed:** Gitea builds `html_url` from the request Host, so links
    came back as the in-stack `http://gitea:3000/...` (not browser-reachable).
    Added `GITEA_PUBLIC_URL` (default `http://localhost:3001`) and
    `_publicize()` to rewrite PR urls; added to `.env.example`.
  - **Verified live** (adapter container on `mahalo-dock_default` network,
    `GITHUB_MODE=real`, real bootstrap token, pointed at `http://gitea:3000`):
    repos/get_repo/branches/pulls/get_pull/all-pulls(+status filter)/commits/
    stats all return correct MAHALO shapes with real Gitea data (4 real commits
    +32/-1, derived contributor stats, 2 branches). PR url rewritten to
    `http://localhost:3001/...`. Cleaned up the demo branch/PR afterward so the
    seed repo is pristine (only `main`, 0 open PRs).
- ✅ **Task 5** — Gitea backend WRITE endpoints (branches + real file commits).
  Implemented in `gitea_backend.py`: `create_repo` (POST `/user/repos`,
  `auto_init`, 409 on duplicate), `create_branch` (POST `.../branches` with
  `new_branch_name`/`old_branch_name`, 404 bad repo / 409 dup), `create_commit`
  (writes **real file contents** via the contents API → real commits), and
  `create_readme` (real file write to the default branch). Added `_request`
  `allow_404` flag, `_normalize_files`, and `_write_file` (create via POST,
  update existing via PUT+sha; base64-encodes UTF-8 text).
  - **File-contents request shape (new):**
    `{"branch","message","files":[{"path","content"}, ...]}`; a single
    `{"path","content"}` is also accepted. `content` is plain UTF-8; the adapter
    base64-encodes for Gitea. Real mode **requires** files (metadata-only commit
    → 422, since Gitea can't make an empty commit). Returns commit id/branch/
    `files_committed`/public `url`.
  - **Mock mode** keeps metadata-only behavior and now also accepts the new
    file-contents shape (records a metadata commit, defaults `author_id` to
    `mahalo-bot`) so Task 7's tool works in both modes. Legacy shape unchanged.
  - **Verified live (real mode):** branch created; 2 real files committed to it
    with exact content confirmed via Gitea raw API; files absent on `main` (404)
    → proving branch isolation; real commits in history. `create_repo`→201
    (dup→409), `create_readme`→201 (content verified), dup branch→409, branch on
    missing repo→404, metadata-only commit→422, commit to missing branch→404.
    **Mock mode:** legacy commit 201, file-shape commit 201 (no crash,
    author_id=mahalo-bot), missing branch 422, 5-repo regression intact. Test
    artifacts (branch + inventory-service repo) cleaned up → state pristine.
- ✅ **Task 6** — Gitea backend real PR creation. Implemented
  `GiteaBackend.create_pull` (POST `.../pulls` with head/base/title/body, 404 on
  missing repo, 422 on missing head), mapping the created PR via the existing
  `_map_pull` (so the shape matches `get_pull`/`list_pulls`), with the url
  publicized. `main.py` already routes `POST /repos/{id}/pulls` in both modes;
  mock `create_pull` records in the JSON store (from Task 3).
  - **Verified live (real mode) end-to-end:** branch → real file commit → open
    PR → 201 (PR #2, head→base correct, **public url**
    `http://localhost:3001/...`). `GET /pulls` lists it; raw Gitea API confirms
    1 open PR. Status filter `open` excludes the Task-4 closed "Demo PR";
    `get_pull` single works; PR to missing repo→404; PR missing head→422.
    **Mock mode:** `create_pull`→201 (PR #145 recorded + listed). Cleaned up
    (closed PR #2, deleted branch) → seed repo pristine (main only, 0 open PRs).
- ✅ **Task 7** — Agent tools: commit files + open PR (approval flow)
  *(unit-verified; full chatbot e2e folded into Task 8)*.
  - `github_tools.py`: added `github_commit_files(repo_id, branch, message,
    files)` and `github_open_pull_request(repo_id, head, base, title, body)`,
    both returning `__PROPOSAL__{...}__END_PROPOSAL__` (actions `commit_files` /
    `open_pull_request`). Added `_normalize_files_arg` (tolerates list / single
    dict / JSON string). NB: left `files` **unannotated** so LangChain's pydantic
    schema doesn't reject a stringified list before our normalizer runs. Tool
    list now exports 7 tools (verified).
  - `agent.py` `execute_proposed_action`: added `commit_files` branch (POST
    `/repos/{id}/commits` with `{branch,message,files}`) and `open_pull_request`
    branch (POST `/repos/{id}/pulls`), both formatting a ✅ message incl. the
    returned public `url`.
  - `prompts.py`: rule #2 extended to list the new write tools + a CHECK-IN-CODE
    FLOW (create branch → commit full file contents → open PR, each a separate
    approval). Developer persona "can help with" updated.
  - **Tests:** new `backend/tests/test_github_write_tools.py` (proposal shapes;
    `_normalize_files_arg` variants; `execute_proposed_action` dispatch for both
    actions with adapter HTTP mocked, asserting endpoint + body + public url in
    message). Ran full suite in the backend image: **20 passed** (3 pre-existing
    + 17 new/at-tool, no regressions). `pytest-asyncio` isn't installed, so async
    dispatch tests drive the coroutine with `asyncio.run()`.
- ✅ **Task 8** — Point backend/adapter at Gitea; finalize Compose wiring.
  - `mock-github` service now: `GITHUB_MODE=${GITHUB_MODE:-real}` (real by
    default), `GITEA_URL=http://gitea:3000`, `GITEA_ADMIN_USER`,
    `GITEA_PUBLIC_URL`, `GITEA_TOKEN_FILE=/bootstrap/gitea_token`; mounts
    `gitea-bootstrap:/bootstrap:ro`; `depends_on` gitea `service_healthy` +
    gitea-bootstrap `service_completed_successfully`. Backend keeps
    `MOCK_GITHUB_URL=http://mock-github:5003` (unchanged).
  - `gitea_backend.py`: added `_read_token_file()` so the adapter reads the
    bootstrap token from the shared volume when `GITEA_TOKEN` env is empty
    (no secret in compose/env needed).
  - **Offline mock path:** new `docker-compose.mock.yml` override forces
    `GITHUB_MODE=mock` and `depends_on: !reset []` (verified `!reset` actually
    clears the base dependency; a plain `[]` merges and does NOT). Usage
    documented in the file header.
  - **Frontend portability:** host port made configurable via
    `${FRONTEND_PORT:-3000}` (+ `.env.example`) so a local dev server on 3000
    doesn't block the stack.
  - **Pre-existing bug fixed:** `frontend/package-lock.json` was out of sync with
    `package.json` (missing `@emnapi/*`), breaking `npm ci` in the Docker build.
    Regenerated the lockfile (`npm install --package-lock-only`); frontend image
    now builds and the Next.js production build succeeds.
  - **Verified live (full `docker compose up`, real mode):** gitea→healthy→
    bootstrap→exited 0→mock-github(real) came up healthy reading the token from
    the shared volume (listed real repo `payment-service`, no token env passed).
    backend + all 4 mocks healthy; frontend serves HTTP 200 (proven on
    `FRONTEND_PORT=3010` since host :3000 was occupied by a stray dev server).
    **End-to-end through the compose adapter at :5003:** create branch → commit
    real file `src/crypto.py` → open PR #1 (public url) → all confirmed via the
    Gitea API; artifacts then cleaned up (seed repo pristine). **Offline mock
    override:** `mock-github` recreated with the override reports `mode=mock` and
    serves the 5 seed repos with no Gitea. Restored stack to real mode.
  - **Note:** frontend has no healthcheck (pre-existing), so it shows "Up"
    without a "(healthy)" tag though it serves fine.

## Phase 2 — Publish (IN PROGRESS 🚧)

- ✅ **Task 9** — Cross-platform run scripts + docs (Win11 + Zorin).
  - **README.md** rewritten: prepended a canonical "🚀 Run with Docker" section
    (Win11 Docker Desktop + Zorin/Ubuntu Docker Engine prerequisites, `docker
    version`/`docker compose version` check, `.env` setup, `docker compose up
    --build`, ports table incl. Gitea UI :3001 + creds, `FRONTEND_PORT` note,
    GITHUB_MODE real-vs-mock with the offline override command, first-time app
    setup, and a 6-step real-code-check-in demo script ending in the Gitea UI).
    The old manual venv path is preserved under a collapsed `<details>` as "Run
    without Docker". Architecture + Project Structure updated to show the adapter
    + Gitea + bootstrap.
  - **Convenience wrappers:** `docker-up.sh`/`.bat` and `docker-down.sh`/`.bat`
    (auto-create `.env` from example; `mock` arg → offline override; `--wipe` →
    `down -v`). Shell scripts chmod +x.
  - **Verified live:** `docker compose config` parses (base + mock override).
    Dry-ran the exact documented commands from a wiped state:
    `docker compose up --build -d` (real) → correct sequencing, all healthy,
    adapter serving Gitea `payment-service`, backend/frontend/Gitea UI all HTTP
    200, documented Gitea creds authenticate. Offline override command → 6
    services up, Gitea NOT started, adapter `mode=mock`. Stack torn down clean.
  - Used `FRONTEND_PORT=3010` in tests because host :3000 is held by the user's
    stray `next-server` dev process (not killed).

- 🚧 **Task 10** — Sanitize secrets + publish MAHALO-dock to GitHub.
  **Publish step DEFERRED — needs explicit user approval before any
  `gh repo create`/push.** Preparation done (local, no network):
  - ✅ `.env.example` fix applied: `SYNTHESIS_MODEL=deepseek-v4-flash` →
    `deepseek-flash` (+ comment listing valid ids `deepseek-flash`,
    `deepseek-v4-pro`).
  - ✅ `.gitignore` verified: excludes `.env` / `.env.*` (keeps `.env.example`),
    `*.db`, `.pids/`, `mock-services/*/data.json`, `node_modules`, `.next`.
    Gitea data lives in a Docker **named volume** (`gitea-data`), not the tree,
    so nothing to ignore there.
  - ✅ Secret scan of the committable tree (144 files, tracked+untracked minus
    gitignored): **no** real-secret matches (sk-/sk-or-v1-/AKIA/ghp_/PRIVATE
    KEY); a second credential-assignment pass found only benign code refs and
    the intended local demo creds. `.env` + `backend/.env` confirmed untracked.
  - ✅ **Published** (user created the repo + pre-authorized gh): remote
    `origin` → https://github.com/tjblavakumar/mahalo-dock (PUBLIC, was empty).
    Committed the dockerization work as `c9156fe` on top of the clean initial
    import `b5a2de9`; `git push -u origin master`. Final staged-tree secret scan
    before commit was clean (only false positive = the pattern list in this
    progress doc). **Post-push verification:** remote `.env` → "Not Found"
    (correctly excluded), `.env.example` present with `SYNTHESIS_MODEL=
    deepseek-flash`. gh auth = account `tjblavakumar`, scopes incl. `repo`.
  - ⬜ **Still pending (optional):** refresh stale root docs that still describe
    MAHALO3 (`SPEC.md`, `ARCHITECTURE.md`, `DEMO.md`, `PROGRESS.md`) — README.md
    was already rewritten in Task 9.
- ⬜ **Task 10** — Sanitize secrets + publish MAHALO-dock to GitHub

## Open items / reminders

- **`.env.example` fix pending:** change `SYNTHESIS_MODEL=deepseek-v4-flash` →
  `deepseek-flash` (do in Task 10, or earlier if convenient).
- **Stale docs:** the copied `PROGRESS.md`, `SPEC.md`, `ARCHITECTURE.md`,
  `README.md`, `DEMO.md` in mahalo-dock still describe MAHALO3. Update/replace to
  reflect MAHALO-dock during Phase 2 (or as touched).
- **These planning docs** (`mahalo-dock-docs/`) were authored in the old mahalo3
  workspace and are to be moved into `/mnt/ONETBSSD/ai/mahalo-dock`. Consider
  converting to a Kiro spec at `.kiro/specs/mahalo-dock/` for native tracking.
- **No persistent agent memory across sessions** — these files ARE the memory.
  A new session should read all three before starting work.

## How to resume in a new session (mahalo-dock workspace)

1. Open Kiro on `/mnt/ONETBSSD/ai/mahalo-dock`.
2. Tell the agent: "Read mahalo-dock-docs/ and continue from the first
   unchecked task." (Or point it at the `.kiro/specs/mahalo-dock/` spec.)
3. Start at the first ⬜ task in Phase 1 (Task 1: Gitea in Compose).
