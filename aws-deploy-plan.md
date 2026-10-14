# MAHALO-dock — AWS Deployment Plan

> **Purpose of this file.** A self-contained handoff for deploying MAHALO-dock as
> a **personal, single-user demo** on **Amazon EC2**, driven from a company AWS
> WorkSpace, using **Amazon Bedrock** for the LLM (so no personal LLM keys are
> spent). Authored on the local Zorin dev machine (which cannot reach the company
> AWS). Work continues from the **AWS WorkSpace** (Windows 11, full internet, AWS
> console/CLI access, Kiro installed). Read top-to-bottom; it carries the full
> planning context so a fresh Kiro session can continue with zero prior history.

> **PLAN CHANGE (important).** The original idea was to run Docker directly on the
> WorkSpace. **That is not possible:** AWS WorkSpaces are themselves virtualized
> and do **not** support nested virtualization, so Docker Desktop (which needs
> WSL2/Hyper-V) will not run there. **We therefore run the stack on an EC2 Linux
> instance** and use the WorkSpace only as the browser + SSH client. The old
> WorkSpace-Docker runbook is removed; EC2 is now the primary path (section 3).

---

## 1. Decision summary (what we agreed)

- **Where it runs:** an **EC2 Linux instance** (Ubuntu) running the existing
  `docker compose` stack — same as the local Zorin box. The WorkSpace **cannot**
  run Docker (no nested virtualization), so it serves only as the browser + SSH
  client to the instance.
- **How we reach it:** **SSH tunnel** from the WorkSpace to the EC2 instance
  (`ssh -L ...`). This forwards the stack's ports to the WorkSpace's `localhost`,
  so **the current `localhost` configuration works unchanged** and **no ports are
  exposed to the internet** (security group only needs inbound SSH). Browsing on
  the WorkSpace to `http://localhost:3010` then hits the instance.
- **LLM:** **Amazon Bedrock**, via an **EC2 instance IAM role** (boto3 reads the
  role automatically — no keys, no `~/.aws` mount). So the demo does **not** burn
  personal OpenRouter / 1min.ai keys. Provider switch already built (section 4).
- **Audience:** demo only, single user. No sharing, no production SLA.
- **Cost:** personal spend (approved). ~t3.medium is ~\$30/mo if left on 24/7, but
  **stop the instance when idle** -> only ~\$2-3/mo EBS. Bedrock billed per token.
- **Code transfer:** repo is public on GitHub
  (https://github.com/tjblavakumar/mahalo-dock) -> the EC2 instance `git clone`s
  it directly from the internet (no file copy from Zorin or the WorkSpace needed).

### Stack recap (what we're deploying)
One `docker compose up` brings up: frontend (Next.js), backend (FastAPI +
LangChain), mock-jira/confluence/servicenow, the mock-github **adapter**
(GITHUB_MODE=real -> Gitea), gitea (self-hosted git server), one-shot
gitea-bootstrap. Verified locally end-to-end: the chatbot creates a real branch,
commits generated code, and opens a PR in Gitea.
Ports: frontend FRONTEND_PORT (default 3000), backend 8008, Gitea UI 3001, mocks
5001-5004. On EC2 keep the defaults and map them with the SSH tunnel (section 3.5);
the browser only needs 3000/3001/8008.

---

## 2. Prerequisites to confirm (do these first, from the WorkSpace)

- [ ] You can launch an **EC2 instance** (console or CLI) in the account/region,
      and create/attach an **IAM role** (instance profile). If IAM role creation is
      restricted, see the fallback in section 4 (mount creds / env vars).
- [ ] You have (or can create) an **EC2 key pair** for SSH, and the private key is
      available on the WorkSpace.
- [ ] The WorkSpace can make **outbound SSH (port 22)** to the EC2 instance's
      public IP (or private IP if WorkSpace + EC2 share routing). *This is the one
      unknown — corporate network policy may block it. Test early (section 3.6).*
- [ ] **Bedrock model access is enabled** in the chosen region for a
      **tool-calling-capable** model (e.g. an Anthropic Claude 3.5+ model) — a
      per-model opt-in in the Bedrock console. The orchestrator REQUIRES tool
      calling. Decide the **region** and exact **model id**.
- [ ] Pick a region that has BOTH EC2 and your Bedrock model.

---

## 3. Primary runbook — EC2 + SSH tunnel + Bedrock

### 3.1 Launch the instance
- AMI: **Ubuntu Server 22.04 or 24.04 LTS** (x86_64).
- Type: **t3.medium** (2 vCPU / 4 GB) minimum — the Next.js build is memory-hungry
  and OOMs on smaller. t3.large is safer if available.
- Storage: **30 GB gp3**.
- **IAM role / instance profile:** create a role with Bedrock invoke permissions
  and attach it (so boto3 gets creds automatically). Minimal policy:
      {
        "Version": "2012-10-17",
        "Statement": [{
          "Effect": "Allow",
          "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:Converse", "bedrock:ConverseStream"],
          "Resource": "*"
        }]
      }
- **Security group:** inbound **TCP 22 (SSH) only**, ideally restricted to the
  WorkSpace's egress IP. **Do NOT open 3010/8008/3001/5001-5004** — the SSH tunnel
  handles those. Outbound: allow all (needs internet for git clone, image pulls,
  Bedrock).
- Key pair: use/download one you can access from the WorkSpace.

### 3.2 Install Docker + Git on the instance (SSH in first)
    ssh -i <key.pem> ubuntu@<ec2-public-ip>
    sudo apt-get update
    sudo apt-get install -y git ca-certificates curl
    # Docker Engine + Compose plugin (official convenience script)
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker ubuntu
    # log out/in (or `newgrp docker`) so docker works without sudo
    exit

### 3.3 Clone + configure
    ssh -i <key.pem> ubuntu@<ec2-public-ip>
    git clone https://github.com/tjblavakumar/mahalo-dock.git
    cd mahalo-dock
    cp .env.example .env
    nano .env    # set the Bedrock block (section 4):
      LLM_PROVIDER=bedrock
      SYNTHESIS_PROVIDER=bedrock
      BEDROCK_REGION=<region>
      BEDROCK_ORCHESTRATOR_MODEL=<tool-calling model id>
      BEDROCK_SYNTHESIS_MODEL=<model id>   # may match orchestrator
      # Leave AWS_PROFILE blank — the instance IAM role supplies creds.
      # FRONTEND_PORT stays 3000 on the server; tunnel maps it locally.

### 3.4 Start the stack
On EC2, Bedrock creds come from the instance role (no ~/.aws mount needed), so run
the **base** compose but with the Bedrock providers set in `.env`:
    docker compose up -d --build
    docker compose ps     # wait healthy; gitea-bootstrap should Exit (0)
(If you prefer the override file, note its `~/.aws` mount is harmless but
unnecessary on EC2; the instance role is used regardless. Base compose already
reads LLM_PROVIDER/SYNTHESIS_PROVIDER from `.env`.)

### 3.5 Open the SSH tunnel (from the WorkSpace)
In a WorkSpace terminal (PowerShell/Windows OpenSSH or Git Bash):
    ssh -i <key.pem> -N \
      -L 3000:localhost:3000 \
      -L 3001:localhost:3001 \
      -L 8008:localhost:8008 \
      ubuntu@<ec2-public-ip>
Leave it running during the demo. (`-N` = no remote shell, just forwarding.)
Note: tunnel the backend (8008) and Gitea UI (3001) too, because the browser calls
those directly from the WorkSpace. Mocks (5001-5004) are only called server-side
by the backend, so they do NOT need tunneling.

### 3.6 Demo from the WorkSpace browser
- App: http://localhost:3000
- Gitea UI: http://localhost:3001 (login mahalo_admin / MahaloDock123!)
- Backend health: http://localhost:8008/health
- Connections: add with Docker **service-name** URLs (form prefills them):
  http://mock-jira:5001, http://mock-confluence:5002, http://mock-github:5003,
  http://mock-servicenow:5004 (tokens mock-<svc>-token-12345).
- Flow: list repos -> create branch -> commit generated code -> open PR -> show it
  in the Gitea UI.

### 3.7 Stop / cleanup
- Pause between demos: `docker compose down` on EC2, then **Stop** the instance
  (console) -> pay only EBS (~\$2-3/mo). Start it again before the next demo.
- Done for good: **Terminate** the instance and delete the volume.

Caveats:
- Because `localhost` config is unchanged, the tunnel ports MUST match the
  container ports (3000/3001/8008). If 3000 is taken on the WorkSpace, forward a
  different local port AND update CORS/NEXT_PUBLIC accordingly — simpler to keep
  3000 free locally.
- If outbound SSH from the WorkSpace is blocked (section 2), that's the main
  blocker; options: use AWS Systems Manager **Session Manager** port forwarding
  instead of raw SSH (no inbound 22 needed), or (least preferred) expose ports via
  the security group locked to the WorkSpace IP and switch to EC2-host URLs.

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

### AWS credentials into the backend container (EC2 path)
- **Primary (EC2 instance IAM role):** attach a role with Bedrock-invoke to the
  instance (section 3.1). boto3 resolves it automatically **inside the container**
  via the EC2 metadata service — **no keys, no `~/.aws` mount, no env**. Just set
  the Bedrock providers/models in `.env` and run the base compose. This is why
  EC2 is actually cleaner than the WorkSpace would have been.
- **Fallback (no role creation allowed):** put temporary creds in the instance's
  `~/.aws` and run with the override
  (`-f docker-compose.yml -f docker-compose.bedrock.yml`, which mounts
  `~/.aws:ro`), or pass `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/
  `AWS_SESSION_TOKEN` as env to the backend. Rotate/remove when done.

---

## 5. Secrets handling
- **Bedrock mode = no secrets in the repo or .env** — creds come from the AWS
  identity. This is the main benefit.
- If falling back to personal keys: keep them only in `.env` (gitignored; `bkp.env`
  guard exists), `chmod 600`, never baked into images.

---

## 6. If the SSH tunnel is blocked (access fallbacks)

The SSH tunnel (section 3.5) is the primary access method and the one unknown is
whether the WorkSpace allows outbound SSH to EC2. If it's blocked:

- **AWS Systems Manager Session Manager (recommended fallback):** install the SSM
  agent (preinstalled on Ubuntu AMIs) + give the instance role `AmazonSSMManaged
  InstanceCore`. Then from the WorkSpace (with AWS CLI + Session Manager plugin):
      aws ssm start-session --target <instance-id> \
        --document-name AWS-StartPortForwardingSession \
        --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'
  Repeat for 3001 and 8008 (or use a multi-port document). No inbound 22, no
  public IP needed — traffic goes through SSM over HTTPS, which corporate networks
  usually allow.
- **Public ports locked to the WorkSpace IP (least preferred):** open
  3000/3001/8008 in the security group to the WorkSpace's egress IP only, browse
  `http://<ec2-ip>:3000` directly. This DROPS the localhost assumption, so you must
  set `NEXT_PUBLIC_API_URL=http://<ec2-ip>:8008`, `GITEA_PUBLIC_URL=http://<ec2-ip>:3001`,
  `GITEA_ROOT_URL=http://<ec2-ip>:3001/`, and add that origin to `CORS_ORIGINS`,
  then rebuild the frontend. More moving parts; avoid unless the tunnel and SSM
  are both unavailable.

---

## 7. Open items / decisions
- [x] WorkSpace cannot run Docker (no nested virtualization) -> use EC2. (decided)
- [x] Bedrock provider code built + unit-tested on Zorin (section 4).
- [ ] Can create/attach an EC2 instance IAM role (else use the creds fallback).
- [ ] **Can the WorkSpace SSH (outbound 22) to EC2?** If not -> SSM port
      forwarding (section 6). This is the main access unknown.
- [ ] Bedrock model access enabled + region + exact tool-calling model id.
- [ ] **Verify Bedrock Converse tool-calling end-to-end** on EC2 (the key risk):
      "List my repositories" must hit the github tool and return Gitea's
      payment-service. If Converse tool-call shape differs from OpenAI, adjust the
      agent loop in `backend/app/agent/agent.py`.

## 8. How to resume (on the WorkSpace / against EC2)
1. Launch EC2 (section 3.1), SSH in, install Docker + Git (3.2).
2. `git clone` the repo on the instance; open it in Kiro **on the WorkSpace** if
   you want Kiro to help (Kiro edits the WorkSpace clone; deploy by pushing to
   GitHub and `git pull` on EC2, or edit directly on EC2 over SSH).
3. Tell Kiro: "Read aws-deploy-plan.md and run the EC2 runbook (section 3) in
   Bedrock mode; verify Bedrock tool-calling (section 7)."
4. `.env` with the Bedrock block -> `docker compose up -d --build` on EC2 ->
   open the SSH tunnel (3.5) -> demo from the WorkSpace browser (3.6).
5. Keep personal-key mode (`LLM_PROVIDER=openrouter`) as a fallback if Bedrock
   access isn't ready yet.

---

## 9. DEPLOYED — live resource inventory (run of 2026-10-14)

> EC2 runbook (section 3) executed end-to-end from the WorkSpace in **Bedrock
> mode**. The account had **no default VPC**, so a minimal network chain was
> built first. Everything below is tagged `project=mahalo-dock` for teardown.

### AWS account / auth
- Account: **051570254217**, region **us-east-1**, SSO profile **`lava`**
  (`AWSAdministratorAccess`). Re-auth when creds expire:
  `aws sso login --profile lava` then `aws sts get-caller-identity --profile lava`.

### Resource IDs
| Resource | ID |
|---|---|
| VPC (`10.0.0.0/16`) | `vpc-099ae3ed33442bf5f` |
| Internet gateway | `igw-0f84d888117821eb6` |
| Public subnet (`10.0.1.0/24`, us-east-1a) | `subnet-0d60d82fbf18103be` |
| Route table | `rtb-001ba70697d6f760d` |
| Security group (inbound TCP 22 from workspace IP only) | `sg-0203b8f626fe1c825` |
| Key pair | `mahalo-dock-key` (pem: `D:\lavakumar.baskaran\.ssh\mahalo-dock-key.pem`) |
| IAM role | `mahalo-dock-ec2-role` (Bedrock invoke + SSM core) |
| Instance profile | `mahalo-dock-ec2-profile` |
| Instance (t3.medium, Ubuntu 24.04, 30 GB gp3) | `i-0234d7d98744d60b9` |
| Public IP | `13.223.68.203` |

### Verified
- Outbound SSH from WorkSpace -> EC2 works (TCP/22 + real authenticated session).
- Docker Engine 29.9.1 + Compose v5.6.0 installed; stack up, all services healthy,
  `gitea-bootstrap` Exited(0).
- **Bedrock tool-calling verified** via Converse (section 7 risk closed):
  model `us.anthropic.claude-sonnet-4-5-20250929-v1:0` (US inference profile,
  ACTIVE), authenticated by the instance role — returned `stopReason=tool_use`
  with a tool call. `.env` set to this id for orchestrator + synthesis.
- SSH tunnel open from WorkSpace (`-L 3000/3001/8008`); localhost serves the
  frontend, Gitea UI, and backend health through it.

### Resume / reconnect
- SSH: `ssh -i D:\lavakumar.baskaran\.ssh\mahalo-dock-key.pem ubuntu@13.223.68.203`
- Re-open tunnel (keep running during demo):
  `ssh -i D:\lavakumar.baskaran\.ssh\mahalo-dock-key.pem -N -L 3000:localhost:3000 -L 3001:localhost:3001 -L 8008:localhost:8008 ubuntu@13.223.68.203`
- App http://localhost:3000 · Gitea http://localhost:3001 (mahalo_admin /
  MahaloDock123!) · Backend http://localhost:8008/health
- NOTE: if the WorkSpace egress IP changes, update the SG ingress rule
  (`sgr-05a70975c83fc8af9`) to the new `/32`, or SSH will stop connecting.

### Stop / teardown
- Idle: `docker compose down` on EC2, then **Stop** the instance (pay only EBS).
  Restart: Start instance -> note the NEW public IP -> update SG + tunnel.
- Full teardown (reverse order): terminate `i-0234d7d98744d60b9`; delete key pair;
  remove instance profile/role (detach policies first); delete SG; disassociate +
  delete route table; detach + delete IGW; delete subnet; delete VPC.

---

## 10. BUGFIX — empty AWS_PROFILE broke the Bedrock instance role (2026-10-14)

**Symptom (chatbot):** `ChatBedrockConverse ... Could not load credentials ...
The config profile () could not be found`.

**Root cause:** base `docker-compose.yml` had
`- AWS_PROFILE=${AWS_PROFILE:-}` under the backend. With `AWS_PROFILE=` (empty)
in `.env`, the container got `AWS_PROFILE` **set to an empty string**. boto3
treats a set-but-empty `AWS_PROFILE` as "use the profile literally named '' ",
fails to find it, and never falls back to the EC2 instance-role step of the
credential chain. (`${VAR:-}` only defaults when the var is *unset*; empty is a
real value and passes straight through.)

**Fix:**
- `docker-compose.yml`: removed the `AWS_PROFILE=...` line from the backend env.
  On EC2 the instance role must be used and no profile is wanted.
- `docker-compose.bedrock.yml`: added the pass-through form `- AWS_PROFILE`
  (no `=value`) so Compose forwards it ONLY when set non-empty — for the
  ~/.aws-mount fallback on a WorkSpace. Empty is omitted, keeping the chain clean.

**Applied on the instance** (`sed` out the line) + `docker compose up -d
--no-deps backend`. Verified: `AWS_PROFILE` now UNSET in the container, and
`build_orchestrator_llm().invoke(...)` returned a live Bedrock response
("READY") using instance-role creds. The same edits are in the local repo compose
files — push them so a future `git pull` on EC2 carries the fix.
