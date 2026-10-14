# MAHALO-dock — AWS Deployment Plan

> **Purpose of this file.** A self-contained handoff for deploying MAHALO-dock as
> a **personal, single-user demo** from a company AWS WorkSpace, using **Amazon
> Bedrock** for the LLM (so no personal LLM keys are spent). It was authored on
> the local Zorin dev machine (which cannot reach the company AWS). The
> deployment continues from the **AWS WorkSpace** (Windows 11, full internet,
> Kiro installed), where this repo is cloned from GitHub. Read it top-to-bottom;
> it carries the full planning context so a fresh Kiro session on the WorkSpace
> can continue with zero prior history.

---

## 1. Decision summary (what we agreed)

- **Where it runs:** directly on the **AWS WorkSpace** via Docker Desktop
  (Win11). No EC2, no SSH, no security groups. The WorkSpace is both the host and
  the demo browser, so `localhost` URLs work exactly like the local Zorin setup.
  (EC2 is kept as an optional fallback in section 6, but is NOT the plan.)
- **LLM:** **Amazon Bedrock**, using the WorkSpace's AWS credentials — so the demo
  does **not** burn the developer's personal OpenRouter / 1min.ai keys. This
  requires a code change to add Bedrock as a provider (section 4). Personal keys
  remain supported as a fallback via a provider switch.
- **Audience:** demo only, single user. No sharing, no production SLA.
- **Cost:** personal spend (approved for a company demo). Bedrock is billed per
  token; running locally on the WorkSpace adds no compute charge.
- **Code transfer:** repo is public on GitHub
  (https://github.com/tjblavakumar/mahalo-dock) -> `git clone` on the WorkSpace.

### Stack recap (what we're deploying)
One `docker compose up` brings up: frontend (Next.js), backend (FastAPI +
LangChain), mock-jira/confluence/servicenow, the mock-github **adapter**
(GITHUB_MODE=real -> Gitea), gitea (self-hosted git server), one-shot
gitea-bootstrap. Verified locally end-to-end: the chatbot creates a real branch,
commits generated code, and opens a PR in Gitea.
Ports: frontend FRONTEND_PORT (default 3000; 3010 locally), backend 8008, Gitea
UI 3001, mocks 5001-5004.

---

## 2. Prerequisites to confirm on the WorkSpace / AWS (do these first)

- [ ] **Docker Desktop for Windows** can be installed and started (WSL2 backend),
      and can pull public images (watch for a corporate proxy / SSL inspection; if
      pulls fail, set Docker Desktop proxy settings).
- [ ] **Git** installed (or GitHub Desktop).
- [ ] **Bedrock model access is enabled** in the account + region for a
      **tool-calling-capable** model (e.g. an Anthropic Claude 3.5+ model). This is
      a per-model opt-in in the Bedrock console. The orchestrator REQUIRES tool
      calling, so the chosen model must support it.
- [ ] The WorkSpace's AWS identity (or a configured profile) can call
      `bedrock:InvokeModel` / Converse for that model in that region. Verify with:
      `aws bedrock list-foundation-models --region <region>` and a Converse test.
- [ ] Decide the **region** (must have the model) and the exact **model id**.

---

## 3. Phase 1 runbook — Docker on the WorkSpace (primary path)

1. Install Docker Desktop + Git on the WorkSpace.
2. Clone and configure:
       git clone https://github.com/tjblavakumar/mahalo-dock.git
       cd mahalo-dock
       copy .env.example .env
3. Edit `.env` for Bedrock (after section 4 is built):
       LLM_PROVIDER=bedrock
       BEDROCK_REGION=<your-region>
       BEDROCK_ORCHESTRATOR_MODEL=<tool-calling model id>
       BEDROCK_SYNTHESIS_MODEL=<model id>     # can match orchestrator
       # No OPENAI_API_KEY / ONEMIN_API_KEY needed in Bedrock mode.
       # FRONTEND_PORT=3010                   # only if 3000 is busy
   Make AWS creds available to the backend container. Simplest on Win11/Docker
   Desktop: mount the WorkSpace AWS profile read-only and pass region/profile
   env (to be wired in section 4 / compose). Document the exact mechanism when built.
4. Start:
       docker compose up --build -d
       docker compose ps        # wait healthy; gitea-bootstrap should Exit (0)
5. Browse on the WorkSpace:
   - App: http://localhost:3000 (or FRONTEND_PORT)
   - Gitea UI: http://localhost:3001 (login mahalo_admin / MahaloDock123!)
6. In the UI, add Connections using Docker **service-name** URLs (the form already
   prefills these): http://mock-jira:5001, http://mock-confluence:5002,
   http://mock-github:5003, http://mock-servicenow:5004 (tokens mock-<svc>-token-12345).
7. Demo: list repos -> create branch -> commit generated code -> open PR -> show
   it in the Gitea UI.

Caveats:
- First build compiles the Next.js frontend; needs a few GB free RAM. If it OOMs,
  close apps or use a larger WorkSpace bundle.
- If Docker image pulls or Bedrock calls fail, suspect a corporate proxy; configure
  Docker Desktop proxy and the AWS SDK proxy/region.

---

## 4. Feature to build FIRST: Bedrock as an LLM provider

> **STATUS: BUILT (on Zorin) + unit-tested. One thing left: verify real Bedrock
> tool-calling on the WorkSpace.** What's done: a provider switch
> `LLM_PROVIDER=openrouter|openai|bedrock` via `backend/app/agent/llm_factory.py`
> (`build_orchestrator_llm` / `build_synthesis_llm`), used by `agent.py` and
> `synthesis.py`; config + `validate_llm_config` (bedrock needs no OpenAI key);
> `langchain-aws` + `boto3` added (version-bounded to avoid pip backtracking);
> `docker-compose.bedrock.yml` override (sets provider=bedrock + mounts
> `~/.aws`); `.env.example` documented; `backend/tests/test_llm_factory.py` (full
> suite 30 passed). Verified in-image: `ChatBedrockConverse` imports, bedrock
> validates with empty OPENAI_API_KEY, openrouter still builds ChatOpenAI.
>
> **Remaining on the WorkSpace:** (a) enable Bedrock model access + confirm
> region/model id; (b) make AWS creds reachable (AWS_PROFILE[_DIR]); (c) run and
> confirm the orchestrator actually tool-calls through Bedrock Converse end to
> end ("List my repositories" -> github tool -> Gitea's payment-service). If
> Converse tool-call parsing differs from OpenAI, adjust the agent loop.
>
> To run in Bedrock mode:
>     # .env: LLM_PROVIDER=bedrock, SYNTHESIS_PROVIDER=bedrock, BEDROCK_REGION,
>     #       BEDROCK_ORCHESTRATOR_MODEL, BEDROCK_SYNTHESIS_MODEL, AWS_PROFILE
>     docker compose -f docker-compose.yml -f docker-compose.bedrock.yml up -d --build
>
> The subsections below are the original design notes (now implemented).

This is the one real code change the AWS demo needs. Build + test it (locally is
fine, if you have any AWS creds; otherwise on the WorkSpace) before relying on it.

### Current wiring (facts)
- Orchestrator: `backend/app/agent/agent.py` builds
  `ChatOpenAI(model=settings.orchestrator_model, api_key=settings.openai_api_key,
  base_url=settings.openai_base_url)` then `.bind_tools(tools)`. **Tool calling is
  mandatory** — the agent loop expects `response.tool_calls`.
- Synthesis: `backend/app/agent/synthesis.py` already switches on
  `settings.synthesis_provider` (onemin | openai) in `_build_synthesis_llm()`.
- Config: `backend/app/core/config.py` (pydantic-settings); compose passes LLM env
  to the backend (added earlier for ORCHESTRATOR_MODEL/OPENAI_*/SYNTHESIS_*/ONEMIN_*).

### Design
Add `LLM_PROVIDER=openrouter|onemin|bedrock` (orchestrator provider). Keep the
existing `SYNTHESIS_PROVIDER` and extend it with `bedrock`. A factory returns the
right LangChain chat model:
- openrouter/openai -> `ChatOpenAI` (existing).
- bedrock -> `ChatBedrockConverse` from **langchain-aws** (Converse API supports
  tools). Credentials come from the default AWS chain (no keys in .env); region +
  model id from env.

### Tasks
1. `backend/requirements.txt`: add `langchain-aws` and `boto3`.
2. `config.py`: add `llm_provider`, `bedrock_region`, `bedrock_orchestrator_model`,
   `bedrock_synthesis_model`. Update `validate_llm_config()` so **Bedrock mode does
   not require an OpenAI key** (only non-bedrock modes do).
3. `agent.py`: extract orchestrator-LLM construction into a factory; when
   `llm_provider == "bedrock"`, build `ChatBedrockConverse(model=...,
   region_name=...)` then `.bind_tools(tools)`. Keep the existing agent loop.
4. `synthesis.py`: add a `bedrock` branch in `_build_synthesis_llm()`.
5. `docker-compose.yml`: pass `LLM_PROVIDER`, `BEDROCK_REGION`, `BEDROCK_*_MODEL`,
   `AWS_REGION`, and the AWS credential mechanism (profile mount or env) to the
   backend service.
6. `.env.example` + README: document the Bedrock path and the no-personal-keys note.
7. **VERIFY (the risk):** tool calling actually works through Bedrock Converse via
   LangChain `bind_tools` — i.e. the orchestrator picks tools and the loop in
   `agent.py` sees `tool_calls`. Smoke test: "List my repositories" must hit the
   github tool and return Gitea's payment-service. If Converse tool-call parsing
   differs, adjust the agent loop accordingly.

### AWS credentials into the backend container (options)
- **Preferred on EC2 (if ever used):** instance IAM role — boto3 picks it up, zero
  config.
- **On the WorkSpace:** mount the AWS profile read-only into the container, e.g.
  `-v %USERPROFILE%\.aws:/root/.aws:ro` (compose volume) and set
  `AWS_REGION`/`AWS_PROFILE`. Confirm the WorkSpace actually has usable AWS creds
  on disk / SSO; if it uses SSO, ensure a current `aws sso login` session and that
  boto3 can use it (may need `AWS_PROFILE` + the SSO cache mounted). **Nail down
  the exact mechanism during the build and document it.**

---

## 5. Secrets handling
- **Bedrock mode = no secrets in the repo or .env** — creds come from the AWS
  identity. This is the main benefit.
- If falling back to personal keys: keep them only in `.env` (gitignored; `bkp.env`
  guard exists), `chmod 600`, never baked into images.

---

## 6. Optional fallback: EC2 (NOT the chosen path)

Only if you later want it off the WorkSpace. Ubuntu 22.04/24.04 LTS, t3.medium
(4 GB RAM for the frontend build), 30 GB gp3, inbound 22 only, instance IAM role
with Bedrock-invoke. Reach it from the WorkSpace via SSH tunnel
(`ssh -L 3010:localhost:3010 -L 3001:localhost:3001 -L 8008:localhost:8008 ...`) so
localhost config keeps working. Install docker + git, clone, `.env`, `docker
compose up -d`. Stop the instance when idle (~$2-3/mo EBS); terminate when done.
Open item: confirm the WorkSpace can SSH to EC2 and reach its ports.

---

## 7. Open items / decisions
- [ ] Confirm Docker Desktop runs on the WorkSpace and can pull images (proxy?).
- [ ] Confirm Bedrock model access + region + exact tool-calling model id.
- [ ] Confirm how the WorkSpace provides AWS creds to boto3 (profile file / SSO).
- [ ] Verify Bedrock Converse tool-calling end-to-end (section 4, task 7).
- [ ] Company policy OK (developer states yes, personal spend).

## 8. How to resume on the WorkSpace
1. Install Docker Desktop + Git; `git clone` the repo; open it in Kiro.
2. Tell Kiro: "Read aws-deploy-plan.md and build the Bedrock provider (section 4),
   then run Phase 1 (section 3)."
3. Build + verify Bedrock (section 4) -> run the stack on the WorkSpace (section 3)
   -> demo. Keep personal-key mode as a fallback if Bedrock access isn't ready.
