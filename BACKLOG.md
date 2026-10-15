# MAHALO-dock — Backlog

Deferred features and known gaps, with enough context to pick up cold. Newest
items first. See `aws-deploy-plan.md` for deployment and `PROGRESS.md` for the
original build history.

---

## 1. Bulk write operations in the agent

**Status:** deferred (2026-10-15)
**Priority:** medium

**Problem.** The propose/approve pipeline is single-action. A bulk request such
as "assign all of David Kim's stories to me" or "move all todo stories to
in_progress" makes the agent *describe* N changes, but only the **first** write
executes: `_extract_proposal` breaks on the first `__PROPOSAL__` block,
`session.pending_action` holds one dict, and `execute_proposed_action` runs one
action. Observed: approving a 7-story reassignment updated only PAY-104.

**Proposed fix (batch proposal).**
- Carry a list of actions through the pipeline (proposal `{"actions": [...]}`,
  or a dedicated `jira_bulk_update_stories` tool).
- `_extract_proposal` collects all actions instead of break-on-first;
  `session.pending_action` holds a list.
- `execute_proposed_action` loops, executing each; continue-on-failure and
  return a per-item success/fail summary.
- Scope: Jira-only first (reassignments / status changes); generalize later.
  Add a test for partial-failure reporting.
- Touches: `backend/app/agent/agent.py`, `backend/app/agent/tools/jira_tools.py`,
  `backend/app/routers/chat.py`.

**Workaround:** do one story per approval.

---

## 2. Per-project git repos + cross-system data consistency (Path 2)

**Status:** deferred (2026-10-15); Path 1 shipped instead (see below)
**Priority:** high (for a complete demo across all projects)

**Problem.** Jira has 5 projects (PAY, CART, AUTH, PROD, ORD) with 30 stories,
but Gitea only has ONE repo (`payment-service`). So any non-PAY story has no repo
to branch/commit/PR against -> "Repository not found". The systems don't agree on
what exists.

**Path 1 (DONE 2026-10-15) — make the single repo reliably usable:**
- Fixed the agent hallucinating repo ids: the github tool docstrings told the LLM
  to use fake ids (`repo-1`..`repo-5`); the real Gitea backend only knows repos by
  NAME. Updated all github tool docstrings + a new prompt rule (#8) to force
  `repo_id` = a real name from `github_list_repos` (e.g. `payment-service`).
- Seeded 3 default persona login users at startup (idempotent):
  `lava@dev.com` (Developer), `lava@pm.com` (Product Manager),
  `lava@exe.com` (Executive), password `MahaloDock123!`.
  Files: `backend/app/services/user_seed.py`, wired in `backend/app/main.py`.
- Net effect: PAY stories work end-to-end (branch -> commit -> PR into
  `payment-service`) for all three personas.

**Path 2 (TODO) — full consistency so EVERY story works:**
- Seed one repo per project in Gitea via `mock-services/gitea-bootstrap/bootstrap.sh`:
  `payment-service` (PAY), `shopping-cart` (CART), `auth-service` (AUTH),
  `product-catalog` (PROD), `order-management` (ORD) — each with an initial
  commit + starter file (loop the existing `put_file` logic).
- Add an explicit project -> repo mapping so the agent deterministically selects
  the right repo for a story's project (e.g. a field in Jira project seed data,
  or a mapping the github tool/prompt exposes). Without this, more repos alone
  won't stop the agent from guessing.
- Make the mock-github adapter / ServiceNow service names line up with these repo
  names (prompt already references payment-service, cart-service, auth-service,
  product-service, order-service — reconcile naming).
- Verify a non-PAY story (e.g. PROD-403) completes branch -> commit -> PR.
- Touches: `mock-services/gitea-bootstrap/bootstrap.sh`,
  `mock-services/jira/seed_data.py`, `backend/app/agent/tools/github_tools.py`,
  `backend/app/agent/prompts.py`, and possibly the ServiceNow/github mocks.

---

## 3. Candidate follow-ups (unscheduled)

- `deploy-aws.ps1 -DryRun` to preview actions without creating resources.
- A `BEDROCK_READ_TIMEOUT` already exists; consider surfacing a frontend-side
  timeout for very long generations if the UI gives up before the backend 200s.
- Automate the Bedrock model-access opt-in check in deploy (currently a manual
  console step; deploy warns + falls back if missing).
