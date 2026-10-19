# Implementation Plan — MAHALO-dock AWS demo deploy/tunnel/Bedrock fixes

Goal: make the "stop → start → open tunnel → demo" flow work end-to-end with no
manual SSM intervention, by fixing (1) the empty-`AWS_PROFILE` Bedrock bug in the
committed compose files, (2) the `AWS_EXECUTION_ENV=EC2` session-check breakage +
containers not auto-starting after a reboot, (3) finishing the partial
`open-tunnel.ps1` edits, and (4) documenting all of it in `scripts/README.md`.

Scope guard: only `docker-compose.bedrock.yml`, a NEW
`docker-compose.bedrock-profile.yml`, `scripts/deploy-aws.ps1`,
`scripts/open-tunnel.ps1`, and `scripts/README.md`. Do NOT touch `backend/app`,
`frontend/`, the base `docker-compose.yml`, or `teardown-aws.ps1`. Preserve the
existing PowerShell idioms (`Info`/`Ok`/`Warn`/`Die`, the `Aws` wrapper that
appends `--profile`/`--region`, `Invoke-Ssm`, backtick line continuations). Every
script must stay idempotent and safe to re-run.

All paths absolute from repo root `d:\lavakumar.baskaran\LavaCode\AI\mahalo-dock`.

---

## Design decisions (made here; do not re-litigate during implementation)

- **Compose layering (chosen: Option A — split the Bedrock override in two).**
  - `docker-compose.bedrock.yml` becomes the **instance-role default**: it sets
    ONLY `LLM_PROVIDER=bedrock` and `SYNTHESIS_PROVIDER=bedrock` on the backend.
    It carries NO `AWS_PROFILE` (neither `- AWS_PROFILE` nor `AWS_PROFILE=`) and
    NO `~/.aws` bind mount. With this file, boto3 on EC2 resolves the instance
    role through its standard chain; nothing ever injects an empty profile.
  - A NEW `docker-compose.bedrock-profile.yml` is the **opt-in WorkSpace case**:
    it adds the `${AWS_PROFILE_DIR:-~/.aws}:/root/.aws:ro` mount AND a NON-EMPTY
    `AWS_PROFILE=${AWS_PROFILE:?set AWS_PROFILE to a non-empty profile name}`
    (the `:?` form makes Compose refuse to start with a clear error rather than
    inject an empty value — this is the guarantee that an empty profile can never
    reach the container). Layered on top only when a named profile is genuinely
    wanted: `-f docker-compose.yml -f docker-compose.bedrock.yml -f docker-compose.bedrock-profile.yml`.
  - Rationale: the base `docker-compose.yml` already deliberately omits
    `AWS_PROFILE` (verified: only a comment remains, no env line). Making
    instance-role the default across every host and pushing the profile case into
    a separate opt-in file removes the single source of the empty-profile bug and
    keeps the common EC2 path a clean two-file invocation.
  - The backend-data volume (`backend-data:/app/data`) is defined in the base
    file and is NOT overridden by either Bedrock file, so it is preserved
    automatically. Neither Bedrock file declares a `volumes:` key for backend
    except `bedrock-profile.yml`, which adds the `~/.aws` mount; because Compose
    MERGES service lists by default (no `!override`), that mount is ADDED to the
    base `backend-data` mount, not a replacement. Confirm in step 8.

- **Auto-start on boot (chosen: a systemd oneshot unit that runs `docker compose up -d`).**
  A `systemd` unit `mahalo-dock.service` (Type=oneshot, RemainAfterExit=yes,
  WantedBy=multi-user.target, After/Requires=docker.service) runs
  `docker compose -f docker-compose.yml -f docker-compose.bedrock.yml up -d` from
  `/home/ubuntu/mahalo-dock` on boot. Preferred over `restart: unless-stopped`
  because it re-reads the compose files and recreates containers with current
  config after a stop/start (so a config change lands on next boot), and it does
  not require editing the base compose services. `systemctl enable docker` is also
  set so the Docker daemon itself comes up. Installed idempotently from the deploy
  provisioning step (write unit only if content differs; `daemon-reload`;
  `enable --now`).

---

## Ordered items

- [ ] 1. Rewrite `docker-compose.bedrock.yml` to the instance-role default.
      Replace the whole file: header comment explains this file is the
      **instance-role default** (boto3 uses the EC2 instance role via the standard
      chain; no profile, no `~/.aws` mount), documents the two usage forms
      (instance-role default = this file alone layered on base; named-profile =
      ALSO layer `docker-compose.bedrock-profile.yml`), and references that the
      base `docker-compose.yml` already sets all other Bedrock env. Body:
      `services: backend: environment:` with exactly `- LLM_PROVIDER=bedrock` and
      `- SYNTHESIS_PROVIDER=bedrock`. Remove the bare `- AWS_PROFILE` line and the
      entire `volumes:` block with the `~/.aws` mount.
      Files: `docker-compose.bedrock.yml`
      Verify: `docker compose -f docker-compose.yml -f docker-compose.bedrock.yml config`
      (run where Docker is available — the EC2 instance via SSM in step 8, or
      locally if Docker present) prints a merged config where the backend has
      `LLM_PROVIDER=bedrock`, `SYNTHESIS_PROVIDER=bedrock`, NO `AWS_PROFILE` key
      at all, and backend volumes still include `backend-data:/app/data` with NO
      `/root/.aws` mount.

- [ ] 2. Create `docker-compose.bedrock-profile.yml` (new opt-in override).
      Header comment: use ONLY on a host with a real `~/.aws` profile (e.g. the
      WorkSpace); layer it AFTER both base and `docker-compose.bedrock.yml`. Body:
      `services: backend: environment: - AWS_PROFILE=${AWS_PROFILE:?set AWS_PROFILE to a non-empty profile name}`
      and `volumes: - ${AWS_PROFILE_DIR:-~/.aws}:/root/.aws:ro`. Explain in a
      comment that the `:?` form guarantees Compose errors out loudly instead of
      injecting an empty profile.
      Files: `docker-compose.bedrock-profile.yml`
      Verify: with no `AWS_PROFILE` in the env,
      `docker compose -f docker-compose.yml -f docker-compose.bedrock.yml -f docker-compose.bedrock-profile.yml config`
      FAILS with the "set AWS_PROFILE" message; with `AWS_PROFILE=lava` set it
      succeeds and the merged backend env shows `AWS_PROFILE=lava` plus the
      `/root/.aws:ro` mount (run via SSM in step 8 or locally if Docker present).

- [ ] 3. Add the AWS env-scrub to `deploy-aws.ps1` preflight (mirror open-tunnel.ps1).
      Immediately before the `# ---------- 0. preflight` session check, add a
      `foreach` loop over
      `@("AWS_EXECUTION_ENV","AWS_ACCESS_KEY_ID","AWS_SECRET_ACCESS_KEY","AWS_SESSION_TOKEN","AWS_PROFILE")`
      that `Remove-Item "Env:$v"` when present (with a `Warn` line each), copied
      verbatim in spirit from open-tunnel.ps1 lines in its scrub block, including
      the explanatory comment about `AWS_EXECUTION_ENV=EC2`. This runs before
      `aws sts get-caller-identity` so the explicit `--profile` is used.
      Files: `scripts/deploy-aws.ps1`
      Verify: `pwsh -NoProfile -Command "$env:AWS_EXECUTION_ENV='EC2'; .\scripts\deploy-aws.ps1 -WhatIf"`
      is not viable (no `-WhatIf` support); instead run
      `pwsh -NoProfile -File scripts/deploy-aws.ps1 -Profile lava` with
      `$env:AWS_EXECUTION_ENV='EC2'` pre-set and confirm the preflight no longer
      dies with "No valid AWS session" (reaches "Authenticated as account"). If a
      live session is unavailable, at minimum
      `pwsh -NoProfile -Command "& { . .\scripts\deploy-aws.ps1 }"` must parse
      without syntax error (e.g. via `powershell -NoProfile -Command "[void][System.Management.Automation.Language.Parser]::ParseFile('scripts/deploy-aws.ps1',[ref]$null,[ref]$null)"`).

- [ ] 4. Update the `deploy-aws.ps1` remote provisioning heredoc for the new layering + no empty profile.
      In the `$remote` here-string: (a) change the stack-up command from
      `sudo docker compose up -d --build` to
      `sudo docker compose -f docker-compose.yml -f docker-compose.bedrock.yml up -d --build`
      and `sudo docker compose -f docker-compose.yml -f docker-compose.bedrock.yml ps`;
      (b) replace the stale defensive `sed` (`/- AWS_PROFILE=\${AWS_PROFILE:-}/d`
      on `docker-compose.yml` — now a no-op since that line no longer exists) with
      a comment noting the empty-profile bug is fixed at the source
      (`docker-compose.bedrock.yml` no longer passes `AWS_PROFILE`), and delete
      any stale non-committed
      `/home/ubuntu/mahalo-dock/docker-compose.instance-role.yml` if present
      (`rm -f`) so it cannot shadow the committed config; (c) do NOT write
      `AWS_PROFILE=` into `.env` — leave `.env` as-is for Bedrock (the base compose
      already omits profile). Keep the `.env` sed edits for
      LLM_PROVIDER/SYNTHESIS_PROVIDER/BEDROCK_* unchanged.
      Files: `scripts/deploy-aws.ps1`
      Verify: parse check as in step 3; and after a real provisioning run, the SSM
      check in step 8 confirms `docker exec mahalo-dock-backend-1 env | grep AWS_PROFILE`
      prints NOTHING (unset).

- [ ] 5. Add the boot auto-start systemd unit to `deploy-aws.ps1` provisioning.
      Append to the `$remote` here-string, after the stack is up: write
      `/etc/systemd/system/mahalo-dock.service` (Type=oneshot, RemainAfterExit=yes,
      After=docker.service, Requires=docker.service, WantedBy=multi-user.target;
      ExecStart runs `/usr/bin/docker compose -f docker-compose.yml -f docker-compose.bedrock.yml up -d`
      with `WorkingDirectory=/home/ubuntu/mahalo-dock`). Make it idempotent: write
      the file via a `cat >` to a temp then only `install`/replace when content
      differs (or just overwrite — identical content each run is fine), then
      `sudo systemctl daemon-reload`, `sudo systemctl enable docker`, and
      `sudo systemctl enable mahalo-dock.service`. Echo a marker so the script can
      confirm (e.g. `echo AUTOSTART_INSTALLED`).
      Files: `scripts/deploy-aws.ps1`
      Verify: via SSM (step 8) `systemctl is-enabled mahalo-dock.service` →
      `enabled`, `systemctl is-enabled docker` → `enabled`; parse check passes.
      Full confidence requires an actual stop/start of i-0234d7d98744d60b9 and
      re-checking containers are Up (step 8).

- [ ] 6. Finish `open-tunnel.ps1` — update the SSM "ensure up" block (do NOT duplicate existing edits).
      ALREADY PRESENT (keep, do not re-add): the top-of-script env-scrub `foreach`
      over AWS_EXECUTION_ENV/AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY/AWS_SESSION_TOKEN/AWS_PROFILE;
      the `Invoke-Ssm` helper (JSON via `--parameters file://$tmp`, temp cleaned in
      `finally`); the "Ensure the app stack is running" `Invoke-Ssm` block and its
      frontend/backend polling. REMAINING WORK: in that block's `-Commands`,
      (a) change the compose up line to
      `sudo docker compose -f docker-compose.yml -f docker-compose.bedrock.yml up -d`
      (it is already this two-file form — confirm it matches the new layering and
      change nothing else there); (b) ADD, before the compose-up command, a line
      `rm -f docker-compose.instance-role.yml` so the stale non-committed override
      can no longer shadow the committed config. Leave the polling/echo lines and
      the `NO_REPO_DIR` handling intact.
      Files: `scripts/open-tunnel.ps1`
      Verify: parse check
      (`[System.Management.Automation.Language.Parser]::ParseFile('scripts/open-tunnel.ps1',...)`)
      passes; via SSM (step 8) confirm no `docker-compose.instance-role.yml`
      remains and the stack comes up with the two-file layering.

- [ ] 7. Add post-tunnel local-forward verification + guidance to `open-tunnel.ps1`.
      The foreground `ssh -N` call blocks, so do NOT try to probe after it. Just
      BEFORE the `ssh -i $PemPath ... -N ...` call, add a clearly-formatted block
      that prints: the second-terminal verification one-liner
      `curl.exe -v http://localhost:3000/` (note `curl.exe` so PowerShell's `curl`
      alias is bypassed), and a short note that "Unable to connect" in Firefox at
      localhost:3000 is often a Firefox/localhost **proxy** setting (network.proxy
      / "No proxy for localhost") rather than a dead tunnel — check the tunnel
      window is still open AND Firefox proxy settings. Keep the existing
      foreground `ssh -N` behavior and the Ctrl+C-to-close UX and the post-close
      Warn lines exactly as they are. Do not background the tunnel.
      Files: `scripts/open-tunnel.ps1`
      Verify: parse check passes; visual read confirms the guidance prints before
      the blocking `ssh` call and the `ssh -N` invocation + Ctrl+C messaging is
      unchanged.

- [ ] 8. On-instance SSM verification of the full flow (instance i-0234d7d98744d60b9, profile lava, region us-east-1).
      This is the real build/behavior verification since Docker runs on the
      instance, not the WorkSpace. Use SSM RunShellScript with command JSON passed
      via `--parameters file://<tmp>` to avoid PowerShell quoting mangling, and
      delete the temp JSON after (mirror the `Invoke-Ssm` pattern already in
      open-tunnel.ps1). Steps, each its own SSM send-command (write the commands
      array to a temp .json, send, poll `get-command-invocation` for Success, read
      `StandardOutputContent`, then `Remove-Item` the temp):
        a. `git -C /home/ubuntu/mahalo-dock pull --ff-only` (land the committed
           compose + script changes on the instance) and
           `rm -f /home/ubuntu/mahalo-dock/docker-compose.instance-role.yml`.
        b. `cd /home/ubuntu/mahalo-dock && sudo docker compose -f docker-compose.yml -f docker-compose.bedrock.yml config`
           → confirm backend has no `AWS_PROFILE` key and keeps
           `backend-data:/app/data`.
        c. `sudo docker compose -f docker-compose.yml -f docker-compose.bedrock.yml up -d --force-recreate backend`
           then `docker exec mahalo-dock-backend-1 env | grep -i aws_profile || echo AWS_PROFILE_UNSET`
           → expect `AWS_PROFILE_UNSET`.
        d. `curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/` → `200`
           and `curl -s http://localhost:8008/health` → healthy JSON.
        e. Install/confirm the systemd unit from step 5 if not already present,
           then `systemctl is-enabled mahalo-dock.service docker` → both
           `enabled`.
        f. Reboot test (OPTIONAL but strongest signal, user-approved auto-start):
           `aws ec2 stop-instances` → `wait instance-stopped` →
           `aws ec2 start-instances` → `wait instance-running`, wait for SSM to
           re-register, then re-run (d). If the reboot test is skipped due to time,
           record that only `is-enabled` was confirmed, not a live reboot.
      Files: none (verification only; no new committed files — any helper script
      stays under `.agents/tasks` or a temp path, never inside the worktree).
      Verify: outputs above match (200 frontend, healthy backend, AWS_PROFILE
      unset in the container, both units enabled). Clean up every temp JSON file
      created for SSM.

- [ ] 9. Update `scripts/README.md` in place (keep structure/tone).
      Add/extend, editing in place (do NOT restructure the existing tables/flow):
      (a) the `AWS_EXECUTION_ENV=EC2` gotcha — what it does to
      `aws sts get-caller-identity`, that the scripts now scrub it per-session, and
      how to check/remove it persistently
      (`Get-ChildItem Env: | Where-Object Name -like 'AWS*'`, and
      `[Environment]::SetEnvironmentVariable('AWS_EXECUTION_ENV',$null,'User')` /
      `'Machine'` with a note that Machine scope needs an elevated shell);
      (b) containers now auto-start on boot via the `mahalo-dock.service` systemd
      oneshot (describe the step-5 mechanism, so a stop/start no longer needs
      manual bring-up); (c) the corrected Bedrock compose layering — two-file
      instance-role default
      (`-f docker-compose.yml -f docker-compose.bedrock.yml`) vs the three-file
      WorkSpace named-profile case
      (`... -f docker-compose.bedrock-profile.yml` with a non-empty `AWS_PROFILE`),
      and when to use each; (d) a short Troubleshooting subsection:
      "Unable to connect" at localhost:3000 → confirm the tunnel window is still
      open AND check Firefox/localhost proxy settings, plus the
      `curl.exe -v http://localhost:3000/` probe; chatbot "config profile ()"
      error → the empty-`AWS_PROFILE` bug, now fixed at the compose source. Update
      the existing "The AWS_PROFILE bugfix" note to reflect the new split-override
      design (the base stays profile-free; the empty value can no longer be
      injected because the profile override uses `${AWS_PROFILE:?...}`).
      Files: `scripts/README.md`
      Verify: visual read — all four topics present, existing sections/tables
      intact, tone consistent; the deploy/open-tunnel command examples match the
      new two-file layering.

---

## Gaps / assumptions

- `restart: unless-stopped` was NOT added to base services; the systemd oneshot
  (item 5) is the single chosen auto-start mechanism per the design decision. If a
  reviewer prefers belt-and-suspenders, that can be revisited, but two mechanisms
  risk fighting on `up -d` and recreation, so one is intentional.
- The reboot test (item 8f) mutates the live instance (stop/start). It is
  user-approved (auto-start is explicitly in scope) but is the one step with real
  blast radius; if time-constrained, confirm `is-enabled` and document that the
  live reboot was not exercised rather than skipping silently.
- The `config`/`docker exec`/reboot verifications must run on the instance via
  SSM because Docker does not run on the WorkSpace (per aws-deploy-plan.md:
  WorkSpaces lack nested virtualization). PowerShell parse-checks are the only
  verification runnable on the WorkSpace itself.
