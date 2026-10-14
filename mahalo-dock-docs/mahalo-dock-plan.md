# MAHALO-dock — Implementation Plan (Task Breakdown)

> Companion to `mahalo-dock-spec.md`. Each task is an independent, demoable
> increment with its own tests. Work them in order. Update
> `mahalo-dock-progress.md` as you complete each one.
>
> **Phase 0 (switchover) is already DONE** — see `mahalo-dock-progress.md`.
> Implementation starts at **Task 1**, in the `/mnt/ONETBSSD/ai/mahalo-dock`
> workspace.

## Conventions

- Python services: test with `pytest`. Preserve existing mock tests.
- Keep the HTTP contract + `X-API-Token` auth identical in both GITHUB_MODE
  values so MAHALO (agent tools, proxy, dashboard) needs no changes in mock mode.
- Follow the existing `__PROPOSAL__...__END_PROPOSAL__` pattern for all write
  tools (mirror `github_create_branch`).
- Pin image/version tags (Gitea especially). Make bootstrap idempotent.
- Never commit secrets. `.env` stays gitignored; ship `.env.example` only.

## Task 1 — Stand up Gitea in Compose with a persistent volume
- Add a `gitea` service (official `gitea/gitea`, pinned tag) to
  `docker-compose.yml`, host-exposed (e.g. `3001:3000`), named volume for
  `/data`, first-run config via env (app name, HTTP settings, disable installer),
  healthcheck on Gitea `/api/healthz`, attached to the stack network as
  `http://gitea:3000`.
- **Test:** `docker compose up gitea` becomes healthy; curl health; load web UI.
- **Demo:** browse the local Gitea web UI.

## Task 2 — Automate Gitea bootstrap (admin + token + seeded repo)
- Add a one-shot `gitea-bootstrap` container/entrypoint that waits for Gitea
  health, creates an admin user, generates an API token, and creates + seeds a
  sample repo (initial commit with real files: README + small source + basic
  structure). Persist the token where the adapter reads it (shared volume/env).
- Use `gitea admin user create` + REST API. Idempotent: skip if already present.
- **Test:** after `up`, assert admin/token/seeded repo+files exist via Gitea API;
  re-running does not error or duplicate.
- **Demo:** fresh `up` yields a pre-populated repo in the web UI.

## Task 3 — Introduce GITHUB_MODE + mode-dispatching layer
- Refactor `mock-services/github` so `main.py` routes each endpoint to either the
  existing JSON-store impl (`mock`, default) or a new Gitea-backed impl (`real`),
  chosen by `GITHUB_MODE`. Extract current handlers into a `mock_backend` module
  behind a common interface; add an empty `gitea_backend` stub.
- Contract + auth identical in both modes. No Gitea calls yet (stub = not impl).
- **Test:** `GITHUB_MODE=mock` → all existing endpoints behave as before
  (regression). `GITHUB_MODE=real` → endpoints resolve to the stub.
- **Demo:** flip the env var; mock mode unchanged.

## Task 4 — Gitea backend: READ endpoints
- Implement all GET endpoints in `gitea_backend` by translating to Gitea REST and
  mapping responses back into MAHALO's existing JSON shapes. Handle
  `repo_id` ↔ Gitea `owner/repo` mapping. Centralize a Gitea client (base
  `http://gitea:3000`, token from bootstrap) + mapping helpers. Map
  `/repos/{id}/stats` from Gitea contributor/commit data; degrade gracefully.
- **Test:** against running Gitea + seeded repo, assert `/repos`, `/branches`,
  `/commits`, `/pulls`, `/stats` return expected shapes; `github_tools.py` read
  tools render correctly in real mode.
- **Demo:** chatbot "list repositories" / "show recent commits" → real Gitea data.

## Task 5 — Gitea backend: WRITE endpoints (branches + real file commits)
- Implement `POST /repos` (create Gitea repo), `POST /repos/{id}/branches` (real
  branch), and extend `POST /repos/{id}/commits` to write **real file contents**
  via Gitea's contents API, producing a real commit. Define request shape for
  file contents (path + content, one or more files); keep backward-compatible
  metadata handling in mock mode. `create_readme` maps to a real file write.
- **Test:** against Gitea, create branch then commit a file; assert branch/file/
  commit exist via Gitea API. Mock mode keeps metadata-only behavior.
- **Demo:** branch + committed file appear in Gitea web UI with real content.

## Task 6 — Gitea backend: real pull request creation
- Add `POST /repos/{id}/pulls` (both modes). Real mode creates a real Gitea PR
  (head→base, title, body) and maps to MAHALO's PR shape; mock mode records a PR
  in the JSON store. Return PR number/URL. Keep GET pulls consistent with created
  PRs.
- **Test:** branch + commit + PR against Gitea; assert PR exists via API and
  `GET /repos/{id}/pulls` lists it. Mock mode records + lists locally.
- **Demo:** PR created via adapter is visible/openable in Gitea web UI.

## Task 7 — Agent tools: commit files + open PR (through approval flow)
- In `backend/app/agent/tools/github_tools.py` add `github_commit_files`
  (repo, branch, file contents) and `github_open_pull_request`
  (repo, head, base, title, body) as WRITE tools returning `__PROPOSAL__` blobs.
- Extend `execute_proposed_action` in `backend/app/agent/agent.py` to handle
  `commit_files` and `open_pull_request` by POSTing to the adapter.
- Update `backend/app/agent/prompts.py` so the orchestrator knows these tools
  exist and require approval. Ensure `chat.py` approve path returns PR number/URL.
- **Test:** unit-test proposal shape + `execute_proposed_action` dispatch (mock
  the adapter HTTP). Integration: approve commit then PR → confirm against Gitea.
- **Demo:** chatbot commits LLM-generated code to a branch and opens a PR; approve
  each; see real branch/commit/PR in Gitea.

## Task 8 — Point backend/adapter at Gitea; finalize Compose wiring
- In `docker-compose.yml`: github service runs `GITHUB_MODE=real`, receives Gitea
  URL + bootstrap token, `depends_on` Gitea healthy + bootstrap complete. Backend
  keeps `MOCK_GITHUB_URL=http://mock-github:5003`. Add env defaults so the stack
  comes up coherently from one `.env`. Document the offline `mock` path.
- **Test:** clean `docker compose up` → all healthy; end-to-end chatbot flow
  (list repos → commit → PR) against Gitea; toggling `GITHUB_MODE=mock` runs
  offline.
- **Demo:** one `up`, full GitHub demo end to end.

## Task 9 — Cross-platform run scripts + docs (Win11 + Zorin)
- Canonical path is `docker compose up`. README section: prerequisites (Docker
  Desktop on Win11, Docker Engine on Zorin), ports, `.env` setup, LLM keys,
  `GITHUB_MODE`, demo script, how to reach Gitea web UI. Note LLM calls need
  network. Watch line-ending/path concerns.
- **Test:** `docker compose config` parses; dry-run documented steps on Linux;
  note Windows checks to confirm manually.
- **Demo:** following the README from scratch brings the stack up on both OSes.

## Task 10 — Sanitize secrets + publish MAHALO-dock to GitHub
- Final secret scrub + sanitized `.env.example`. **FIX:** `.env.example` still
  has `SYNTHESIS_MODEL=deepseek-v4-flash` (invalid 1min.ai model) — change to
  `SYNTHESIS_MODEL=deepseek-flash` (valid; `deepseek-v4-pro` is the only other
  valid DeepSeek id on 1min.ai).
- Confirm `.gitignore` excludes `.env`, mock `data.json`, `.pids`, sqlite DB, and
  the Gitea volume data.
- Then: `gh repo create MAHALO-dock ...`, push clean history to a branch with
  `-u`. Verify no secrets in the committed tree first (grep staged files).
- **Demo:** clone fresh, copy `.env.example`→`.env`, add LLM keys,
  `docker compose up`, run full demo.

## Notes carried from the fix session (apply in Task 10 / as relevant)
- Valid 1min.ai DeepSeek model ids: `deepseek-flash`, `deepseek-v4-pro`. The
  value `deepseek-v4-flash` is INVALID and caused the UNIFY_CHAT_WITH_AI 400.
- MAHALO3's orchestrator was running via OpenRouter (`OPENAI_BASE_URL` pointed at
  openrouter) with `ORCHESTRATOR_MODEL=deepseek/deepseek-chat`, despite comments
  saying orchestrator must be OpenAI. Keep this in mind when writing docs; it
  works as long as the model supports function calling.
