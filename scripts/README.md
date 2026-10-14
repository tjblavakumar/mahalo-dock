# AWS deploy scripts

One-shot provisioning for the MAHALO-dock demo on EC2 + Bedrock, driven from the
Windows AWS WorkSpace. Built to be re-run after the monthly account reset. See
`../aws-deploy-plan.md` for the full design and rationale.

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
Then browse: App http://localhost:3000 · Gitea http://localhost:3001
(mahalo_admin / MahaloDock123!) · Backend http://localhost:8008/health

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
- **The AWS_PROFILE bugfix** (empty profile broke the instance role) is in the
  committed compose files; the deploy script also strips it defensively on the
  instance as a safety net.
