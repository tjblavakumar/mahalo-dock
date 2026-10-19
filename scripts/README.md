# AWS deploy scripts

One-shot provisioning for the MAHALO-dock demo on EC2 + Bedrock, driven from the
Windows AWS WorkSpace. Built to be re-run after the monthly account reset. See
`../aws-deploy-plan.md` for the full design and rationale.

## TL;DR runbook — what to do, and when

Three situations. Pick the one you're in. Run everything from the repo root on
the WorkSpace, in PowerShell.

### A. Every day you want to demo (instance already exists this month)
This is the normal case. The instance is just stopped between demos.
```powershell
aws sso login --profile lava        # authenticate (skip if your session is still valid)
pwsh ./scripts/open-tunnel.ps1      # starts the instance if stopped, then tunnels
```
Then, in your **browser**, open http://localhost:3000 and log in with
`lava@dev.com` / `MahaloDock123!` (see **Login credentials**). Leave the tunnel
window open (it goes silent — that's normal). Press **Ctrl+C** in it when done.

To pause and save money after the demo:
```powershell
# Ctrl+C in the tunnel window first, then:
pwsh ./scripts/teardown-aws.ps1 -StopOnly
```

### B. First demo of the month (right after the monthly purge wiped everything)
Nothing exists yet, so you must build it once. This takes several minutes.
```powershell
aws sso login --profile lava        # 1. authenticate
pwsh ./scripts/deploy-aws.ps1       # 2. build infra + deploy app (several min)
pwsh ./scripts/open-tunnel.ps1      # 3. SEPARATE terminal; opens your window into the app
```
Then browse http://localhost:3000 and log in as above. After this, every later
demo this month is just situation **A**.

### C. You're done for the month (or want a clean slate early)
```powershell
pwsh ./scripts/teardown-aws.ps1     # deletes everything (prompts; add -Force to skip)
```

> Quick decision: **Does a `mahalo-dock` instance already exist this month?**
> Yes → situation **A** (just `open-tunnel`). No → situation **B** (`deploy`
> first). The monthly purge always puts you back in **B**.

If anything misbehaves (blank page, login fails, chatbot error), jump to
**Troubleshooting** at the bottom.

## What each script does (read this first)

The three scripts do different jobs. The one that confuses people is the tunnel,
so here is the mental model.

| Script | Touches | Analogy |
|---|---|---|
| `deploy-aws.ps1` | Builds the AWS infra **and** installs/runs the app | Build the house and move in |
| `open-tunnel.ps1` | Nothing on AWS — only your **local** connection | Open a private door to peek inside |
| `teardown-aws.ps1 -StopOnly` | **Stops** the instance (infra + data kept) | Lock up and leave (house stays) |
| `teardown-aws.ps1` (no flag) | **Deletes** everything | Demolish the house |

### Why a tunnel is needed
For security, the app's ports are **NOT exposed to the internet**. The security
group allows inbound **SSH (port 22) from your WorkSpace IP only** — nothing
else can reach the instance from outside. So after `deploy-aws.ps1`, the app is
running on EC2, but you still cannot open `http://<ec2-ip>:3000` in a browser:
that port is firewalled off.

The SSH tunnel is the bridge. It reuses the one allowed port (22) to forward the
app's ports to your WorkSpace's `localhost`:

```
Your browser                         SSH tunnel (port 22)              EC2 instance
http://localhost:3000  ───────────────────────────────────────▶      frontend (3000)
http://localhost:3001  ──── all over the single SSH connection ─▶      Gitea    (3001)
http://localhost:8008  ────────────────────────────────────────▶      backend  (8008)
```

While the tunnel is open, `http://localhost:3000` on the WorkSpace actually hits
the frontend on EC2. Close the tunnel and `localhost:3000` stops working — the
app keeps running on EC2, you just lose your private window into it. That is why
you run `deploy` rarely (once per reset) but `open-tunnel` **every time** you sit
down to demo.

**Important:** `teardown-aws.ps1` **deletes** by default — it does not merely
stop things. Use `-StopOnly` when you just want to pause between demos.

### Typical sequences

First time each month (after the reset wipes everything):
```powershell
aws sso login --profile lava        # 1. authenticate
pwsh ./scripts/deploy-aws.ps1       # 2. build infra + deploy app (several min)
pwsh ./scripts/open-tunnel.ps1      # 3. separate terminal; your window into the app
# 4. browse http://localhost:3000 and demo; keep the tunnel terminal open
```

Done with a demo (pause to save money):
```powershell
# Ctrl+C in the tunnel terminal (closes your window; app still runs)
pwsh ./scripts/teardown-aws.ps1 -StopOnly
```

Next demo the same month (instance only stopped, app still there):
```powershell
aws sso login --profile lava        # if the session expired
pwsh ./scripts/open-tunnel.ps1      # detects the stopped instance, offers to start it, then tunnels
# No deploy needed — you skip straight to demoing.
```
The containers **auto-start on boot** now (see below), so after a stop/start the
stack is already coming up by the time the tunnel opens. `open-tunnel.ps1` still
brings it up over SSM as a belt-and-suspenders step, so the window into the app
is ready either way.

End of month / clean slate:
```powershell
pwsh ./scripts/teardown-aws.ps1     # fully deletes everything (the monthly reset would too)
```

## Prerequisites (on the WorkSpace)
- AWS CLI v2 and the OpenSSH client (`ssh`, `scp`) on PATH
- A valid SSO session:
  ```powershell
  aws sso login --profile lava
  aws sts get-caller-identity --profile lava   # sanity check
  ```
- Bedrock model access enabled in the region for a tool-calling Claude Sonnet
  model (one-time per-model opt-in in the Bedrock console). The deploy script
  auto-resolves the active inference profile id.

### Gotcha: `AWS_EXECUTION_ENV=EC2` on the WorkSpace
If a leftover `AWS_EXECUTION_ENV=EC2` env var is set, the AWS CLI chases EC2
instance-metadata credentials (which the WorkSpace does not have) and reports
`No valid AWS session` even right after a successful `aws sso login`. Both
`deploy-aws.ps1` and `open-tunnel.ps1` now **scrub this for the session**
automatically (along with any stray `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
/ `AWS_SESSION_TOKEN` / `AWS_PROFILE`), so the explicit `--profile` is used.

To check whether it is set, and remove it persistently:
```powershell
Get-ChildItem Env: | Where-Object Name -like 'AWS*'           # list AWS_* vars
[Environment]::SetEnvironmentVariable('AWS_EXECUTION_ENV',$null,'User')    # per-user
# Machine scope needs an ELEVATED (Run as administrator) shell:
[Environment]::SetEnvironmentVariable('AWS_EXECUTION_ENV',$null,'Machine')
```
Open a fresh terminal afterward for the change to take effect.

## Deploy (end to end)
```powershell
pwsh ./scripts/deploy-aws.ps1
```
Creates (or reuses, if already present): VPC, internet gateway, public subnet,
route table, security group (inbound SSH locked to your current egress IP), key
pair (`~/.ssh/mahalo-dock-key.pem`), a Bedrock+SSM IAM role, and a t3.medium
Ubuntu 24.04 instance. Then installs Docker + Git, clones the repo, writes `.env`
for Bedrock mode, and brings up the compose stack. At the end it prints the SSH
tunnel command and the demo URLs.

The script is **idempotent** — safe to re-run. It looks up existing
`project=mahalo-dock` tagged resources before creating, detects your egress IP
each run (and re-locks the SG to it), and auto-resolves the Bedrock model.

It brings the stack up with the Bedrock **instance-role** layering
(`-f docker-compose.yml -f docker-compose.bedrock.yml`) so boto3 uses the EC2
instance role (no `AWS_PROFILE`, no `~/.aws` mount), and installs a systemd
oneshot (`mahalo-dock.service`) that re-runs `docker compose ... up -d` on every
boot. That is why a later stop/start just works: the stack comes back up by
itself, and `open-tunnel.ps1` only needs to open your local forward.

### Bedrock compose layering (instance-role vs WorkSpace-profile)
There are two ways to supply AWS credentials to the backend, and they differ by
which compose files you layer:

| Host | Where creds come from | Compose layering |
|---|---|---|
| EC2 (the deployed demo) | the instance role, via boto3's standard chain | `-f docker-compose.yml -f docker-compose.bedrock.yml` |
| WorkSpace / laptop with a named `~/.aws` profile | your `~/.aws` profile | `... -f docker-compose.bedrock-profile.yml` **and** a non-empty `AWS_PROFILE` |

`docker-compose.bedrock.yml` is the **default** everywhere: it only flips
`LLM_PROVIDER`/`SYNTHESIS_PROVIDER=bedrock` and carries no profile and no mount.
`docker-compose.bedrock-profile.yml` is the opt-in that adds the read-only
`~/.aws` mount plus `AWS_PROFILE=${AWS_PROFILE:?...}` — the `:?` form makes
Compose refuse to start if `AWS_PROFILE` is empty or unset, so an empty profile
can never reach the container. The deploy/tunnel scripts use the instance-role
(two-file) layering; you only add the profile override when running against a
host whose creds live in `~/.aws`:
```powershell
$env:AWS_PROFILE = "lava"
docker compose -f docker-compose.yml -f docker-compose.bedrock.yml `
  -f docker-compose.bedrock-profile.yml up -d
```

Common options:
```powershell
pwsh ./scripts/deploy-aws.ps1 -Profile lava -Region us-east-1 -InstanceType t3.large
```

## Open the tunnel (separate terminal, keep open)
Easiest — resolves the instance IP by tag automatically:
```powershell
pwsh ./scripts/open-tunnel.ps1
```
It finds the running `mahalo-dock` instance (offers to start it if stopped),
warns if TCP 22 isn't reachable (usually a changed egress IP → re-run deploy),
and opens the tunnel. Leave it running; Ctrl+C closes it.

Manual equivalent, if you prefer:
```powershell
ssh -i "$env:USERPROFILE\.ssh\mahalo-dock-key.pem" -N `
  -L 3000:localhost:3000 -L 3001:localhost:3001 -L 8008:localhost:8008 `
  ubuntu@<public-ip>
```
Then browse: App http://localhost:3000 · Gitea http://localhost:3001 · Backend
http://localhost:8008/health. See **Login credentials** below for the accounts.

## Stop / tear down
```powershell
pwsh ./scripts/teardown-aws.ps1 -StopOnly   # pause: stop instance, keep infra (cheapest)
pwsh ./scripts/teardown-aws.ps1             # full teardown (prompts; -Force to skip)
```

## Notes
- **Billing:** t3.medium + 30 GB gp3. Stop when idle. The monthly reset should
  remove everything, but run the teardown if you want a clean slate sooner.
- **Egress IP changes:** re-running deploy reconciles the SG to your current IP.
  If only the IP changed, re-run deploy (it reuses the instance) and re-open the
  tunnel to the (possibly new) public IP it prints.
- **The AWS_PROFILE bugfix** (an empty `AWS_PROFILE=` broke the EC2 instance
  role with `config profile () could not be found`) is fixed at the source:
  `docker-compose.bedrock.yml` no longer passes `AWS_PROFILE` at all, and the
  base `docker-compose.yml` never set it. The only place a profile is injected
  is the opt-in `docker-compose.bedrock-profile.yml`, which uses the required
  form `${AWS_PROFILE:?...}` so an empty value can never be injected. No
  defensive `sed` on the instance is needed anymore.
- **Auto-start on boot:** `deploy-aws.ps1` installs a systemd oneshot
  (`mahalo-dock.service`, `enable docker` too) that runs the two-file
  instance-role `docker compose ... up -d` from `/home/ubuntu/mahalo-dock` on
  every boot. A stop/start therefore brings the stack back automatically.

## Login credentials

Two different logins — don't mix them up:

| Where | Username/field | Password | Notes |
|---|---|---|---|
| **App** (http://localhost:3000) | an **email** (not a username) | `MahaloDock123!` | `lava@dev.com` (Developer), `lava@pm.com` (Product Manager), `lava@exe.com` (Executive) |
| **Gitea** (http://localhost:3001) | `mahalo_admin` | `MahaloDock123!` | admin account for the git server |

The most common app-login mistake is typing `mahalo_admin` (that's **Gitea**) or
just `lava` into the app's login box. The app wants the full **email**, e.g.
`lava@dev.com`.

These three app accounts are **seeded automatically on first backend startup**
and are **not reset** on container restart or instance stop/start — they live in
the `backend-data` Docker volume. A full teardown or the monthly purge wipes the
volume, after which the next `deploy-aws.ps1` re-seeds the same three accounts
with the same password.

If an app login ever rejects `MahaloDock123!` (e.g. an old volume whose stored
hash drifted from the current default), reset the three demo passwords to the
documented value without disturbing anything else:
```powershell
# one-off: re-hash the three persona passwords to DEFAULT_PASSWORD
docker exec -w /app mahalo-dock-backend-1 python -c "from app.core.database import SessionLocal; from app.models.user import User; from app.services.auth_service import hash_password; from app.services.user_seed import DEFAULT_PASSWORD, DEFAULT_USERS; db=SessionLocal(); [setattr(u,'password_hash',hash_password(DEFAULT_PASSWORD)) for e in DEFAULT_USERS if (u:=db.query(User).filter(User.email==e['email']).first())]; db.commit(); db.close(); print('reset done')"
```
(Run it on the instance, e.g. via SSM or an SSH session. On EC2 the containers
run as the instance user; prefix with `sudo` if your shell isn't in the docker
group.)

## Troubleshooting
- **Browser: "Unable to connect" at `localhost:3000`.** First confirm the
  `open-tunnel.ps1` window is still open (it looks frozen — that is normal and
  means the tunnel is live). Then probe the forward from a *second* terminal:
  ```powershell
  curl.exe -v http://localhost:3000/     # curl.exe, not PowerShell's curl alias
  ```
  If `curl.exe` gets a response but Firefox does not, it is almost always a
  **Firefox/localhost proxy** setting, not a dead tunnel: Firefox Settings >
  Network Settings, set 'No proxy' for localhost (or add `localhost,127.0.0.1`
  to 'No proxy for'). If `curl.exe` also fails, re-open the tunnel (and if TCP 22
  is unreachable, your egress IP likely changed — re-run `deploy-aws.ps1`).
- **App login fails ("Invalid email or password").** First check you're on the
  **app** (http://localhost:3000), using an **email** like `lava@dev.com` (not
  `mahalo_admin`, which is Gitea) and the password `MahaloDock123!` (capital M
  and D, trailing `!`). If the credentials are right and it still fails, the
  stored hash in an old `backend-data` volume may have drifted — run the
  password-reset one-liner in **Login credentials** above. If the login button
  seems to do nothing at all (no error), the frontend can't reach the backend:
  make sure all three ports (3000/3001/8008) are forwarding and hard-refresh
  (Ctrl+Shift+R).
- **Chatbot: "Bedrock error: The config profile () could not be found".** This
  was the empty-`AWS_PROFILE` bug and is now fixed in the compose files (see the
  AWS_PROFILE bugfix note above). If you still hit it, confirm the stack was
  brought up with the instance-role layering
  (`-f docker-compose.yml -f docker-compose.bedrock.yml`) and that no stray
  `AWS_PROFILE=` is set; `docker exec mahalo-dock-backend-1 env | grep -i aws`
  should show no `AWS_PROFILE` line (only `AWS_REGION` is expected).
