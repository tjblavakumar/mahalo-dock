# Verification note — MAHALO-dock AWS deploy/tunnel/Bedrock fixes

First iteration (no `mahalo-dock-fix-review.json` present). Implemented the plan
in `mahalo-dock-fix-plan.md` from scratch.

## What changed, per file

- **docker-compose.bedrock.yml** (rewritten): now the instance-role default.
  Sets ONLY `- LLM_PROVIDER=bedrock` and `- SYNTHESIS_PROVIDER=bedrock` on the
  backend. Removed the bare `- AWS_PROFILE` pass-through and the entire
  `volumes:` block with the `~/.aws` mount. Header comment rewritten to describe
  the instance-role default and the two usage forms.
- **docker-compose.bedrock-profile.yml** (new): opt-in WorkSpace override. Adds
  `- AWS_PROFILE=${AWS_PROFILE:?set AWS_PROFILE to a non-empty profile name ...}`
  (required-variable form — Compose refuses to start on empty/unset) and the
  `- ${AWS_PROFILE_DIR:-~/.aws}:/root/.aws:ro` mount.
- **scripts/deploy-aws.ps1**: (1) added the AWS env-scrub `foreach` before the
  preflight (unsets AWS_EXECUTION_ENV / AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
  / AWS_SESSION_TOKEN / AWS_PROFILE), mirroring open-tunnel.ps1; (2) remote
  provisioning now brings the stack up with
  `-f docker-compose.yml -f docker-compose.bedrock.yml` (up + ps), replaced the
  stale `sed '/- AWS_PROFILE=.../d'` with a comment + `rm -f
  docker-compose.instance-role.yml`; (3) added a systemd oneshot
  `mahalo-dock.service` (Type=oneshot, RemainAfterExit=yes) that runs the
  two-file `docker compose up -d` from /home/ubuntu/mahalo-dock on boot, with
  `daemon-reload` + `enable docker` + `enable mahalo-dock.service`
  (idempotent). `.env` is NOT given an AWS_PROFILE. SYNOPSIS updated.
- **scripts/open-tunnel.ps1**: finished the partial edits. The SSM "ensure up"
  block now `rm -f docker-compose.instance-role.yml` before the two-file
  instance-role `docker compose up -d`. Added a pre-tunnel guidance block (before
  the blocking foreground `ssh -N`) with the second-terminal
  `curl.exe -v http://localhost:3000/` probe and the Firefox/localhost proxy
  note. Foreground `ssh -N` + Ctrl+C UX unchanged; existing top-of-file env-scrub
  and `Invoke-Ssm` helper left intact.
- **scripts/README.md**: added the AWS_EXECUTION_ENV=EC2 gotcha (what it breaks,
  that the scripts scrub it, how to check/remove persistently via User/Machine
  scopes); auto-start-on-boot description; the Bedrock compose layering table
  (two-file instance-role default vs three-file WorkSpace named-profile);
  rewrote the AWS_PROFILE bugfix note for the split-override design; added a
  Troubleshooting section ("Unable to connect" -> tunnel + Firefox proxy +
  curl.exe; "config profile ()" -> fixed).

## Operator usage (compose layering)

- EC2 / instance-role default (what deploy + open-tunnel use):
  `docker compose -f docker-compose.yml -f docker-compose.bedrock.yml up -d`
- WorkSpace with a named ~/.aws profile:
  `$env:AWS_PROFILE="lava"; docker compose -f docker-compose.yml -f docker-compose.bedrock.yml -f docker-compose.bedrock-profile.yml up -d`

## Verification evidence (instance i-0234d7d98744d60b9, profile lava, us-east-1)

Instance validation used the NOT-YET-PUSHED compose files: the repo on the
instance clones from GitHub, so the two updated compose files were transported
onto the instance via SSM (base64) before validating. The committed scripts were
NOT run on the instance; the systemd unit was installed via SSM using the exact
unit text from deploy-aws.ps1.

(a) `docker compose -f docker-compose.yml -f docker-compose.bedrock.yml config`
    on the instance: `CONFIG_OK`; `NO_AWS_PROFILE_IN_MERGED`;
    `NO_AWS_MOUNT_IN_MERGED` (no /root/.aws); `backend-data` volume present;
    `LLM_PROVIDER: bedrock`, `SYNTHESIS_PROVIDER: bedrock`, all BEDROCK_*/MOCK_*
    env present.

(a') Profile override: with AWS_PROFILE UNSET,
    `-f ... -f docker-compose.bedrock-profile.yml config` FAILS with
    "set AWS_PROFILE to a non-empty profile name"; with `AWS_PROFILE=lava` it
    succeeds and shows `AWS_PROFILE: lava`, the `/root/.aws` mount, and still
    `backend-data`.

(b) Stack up (instance-role layering, `--force-recreate backend`):
    - `docker exec mahalo-dock-backend-1 env | grep -i '^AWS'` ->
      `AWS_REGION=us-east-1` ONLY; explicit check -> `AWS_PROFILE_UNSET`.
    - `FRONTEND_HTTP=200`.
    - `BACKEND_HEALTH={"status":"healthy","service":"mahalo3-backend","version":"0.1.0"}`.
    - backend logs: no `config profile` / `could not be found` /
      `Could not load credentials` lines.
    - Bedrock end-to-end: boto3 `converse` from inside the backend container
      against `us.anthropic.claude-sonnet-4-5-20250929-v1:0` returned
      `BEDROCK_REPLY=OK` (instance role authenticated; the "config profile ()"
      error is gone).

(c) Auto-start: `systemctl is-enabled mahalo-dock.service` -> `enabled`;
    `systemctl is-enabled docker` -> `enabled`. `systemctl start
    mahalo-dock.service` -> `UNIT_START_OK`, `IS_ACTIVE=active`,
    `ExecMainStatus=0` (ExecStart ran cleanly); `docker compose ... ps` shows all
    7 services running. Live reboot test (8f) skipped intentionally — optional in
    the plan and the one step with real blast radius; unit activation with exit 0
    confirms it will bring the stack up on boot.

(d) PowerShell parse-check (ParseFile, not executed): open-tunnel.ps1 OK,
    deploy-aws.ps1 OK (Windows PowerShell 5.1; pwsh not installed on this host).

All temporary SSM payloads/helpers were written under %TEMP% (outside the repo)
and deleted after use; no stray files remain in scripts/.
