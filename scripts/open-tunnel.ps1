<#
.SYNOPSIS
    Open the SSH tunnel to the running MAHALO-dock EC2 instance, resolving its
    public IP automatically by the project=mahalo-dock tag (no copy/paste).

.DESCRIPTION
    Forwards the three ports the browser needs — frontend (3000), Gitea (3001),
    backend (8008) — from the WorkSpace's localhost to the instance. Run this in
    its own terminal and leave it open during the demo; press Ctrl+C to close.

    It finds the running instance by tag, so you don't need to know the IP (which
    changes each deploy). If the instance is stopped it offers to start it.

.PARAMETER Profile
    AWS CLI profile. Default: lava.

.PARAMETER Region
    AWS region. Default: us-east-1.

.PARAMETER KeyName
    Key pair name; the pem is expected at ~/.ssh/<KeyName>.pem. Default: mahalo-dock-key.

.EXAMPLE
    pwsh ./scripts/open-tunnel.ps1
#>

[CmdletBinding()]
param(
    [string]$Profile = "lava",
    [string]$Region  = "us-east-1",
    [string]$KeyName = "mahalo-dock-key"
)

$ErrorActionPreference = "Stop"
$ProjectTag = "mahalo-dock"
$PemPath    = Join-Path $env:USERPROFILE ".ssh\$KeyName.pem"
$RemoteDir  = "/home/ubuntu/mahalo-dock"

function Info($m){ Write-Host "[*] $m" -ForegroundColor Cyan }
function Ok($m){   Write-Host "[+] $m" -ForegroundColor Green }
function Warn($m){ Write-Host "[!] $m" -ForegroundColor Yellow }
function Die($m){  Write-Host "[x] $m" -ForegroundColor Red; exit 1 }

# Scrub env vars that hijack the AWS CLI's credential resolution. The big one is
# AWS_EXECUTION_ENV=EC2, which makes the CLI chase EC2 instance-metadata creds
# (absent on a WorkSpace) and falsely report "No valid AWS session" even right
# after a successful 'aws sso login'. We also clear any static creds / stray
# profile so the explicit --profile below is what actually gets used.
foreach ($v in @("AWS_EXECUTION_ENV","AWS_ACCESS_KEY_ID","AWS_SECRET_ACCESS_KEY","AWS_SESSION_TOKEN","AWS_PROFILE")) {
    if (Test-Path "Env:$v") { Warn "Unsetting conflicting env var $v for this session"; Remove-Item "Env:$v" -ErrorAction SilentlyContinue }
}

function Aws {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
    $out = & aws @Args --profile $Profile --region $Region 2>&1
    if ($LASTEXITCODE -ne 0) { throw "aws $($Args -join ' ') failed: $out" }
    $s = ($out | Out-String).Trim()
    if ($s -eq "None") { return "" }
    return $s
}

# Run a shell script on the instance via SSM (no SSH needed) and return its
# combined stdout. The instance role already carries AmazonSSMManagedInstanceCore
# (granted by deploy-aws.ps1). Lines are passed as a JSON file to dodge PowerShell
# quoting mangling of the inline --parameters form.
function Invoke-Ssm {
    param([string]$InstanceId, [string[]]$Commands, [int]$TimeoutSec = 180)

    # IMPORTANT (cross-PowerShell-version safety): the remote commands contain
    # shell metacharacters like '>' and '&' (e.g. "2>&1"). Windows PowerShell
    # 5.1's ConvertTo-Json escapes those to \u003e / \u0026; when AWS reads that
    # inline redirect, `aws ssm send-command` STALLS, which used to hang this
    # whole script before the tunnel opened (pwsh 7 does not escape them, so it
    # only broke under 5.1). To be version-proof we base64-encode the entire
    # remote script and send ONE command: `echo <b64> | base64 -d | bash`. The
    # JSON then holds only [A-Za-z0-9+/=] plus a fixed wrapper - nothing for any
    # PowerShell version to mangle.
    $script = ($Commands -join "`n") -replace "`r", ""
    $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($script))
    $payload = @{ commands = @("echo $b64 | base64 -d | bash") } | ConvertTo-Json -Compress
    $tmp = Join-Path $env:TEMP ("mahalo-ssm-{0}.json" -f ([guid]::NewGuid().ToString('N')))
    $payload | Out-File -FilePath $tmp -Encoding ascii
    try {
        $cmdId = Aws ssm send-command --instance-ids $InstanceId --document-name "AWS-RunShellScript" `
            --parameters "file://$tmp" --query "Command.CommandId" --output text
        if (-not $cmdId) { throw "ssm send-command returned no CommandId" }
        $deadline = (Get-Date).AddSeconds($TimeoutSec)
        $status = "Pending"
        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 4
            $status = Aws ssm get-command-invocation --command-id $cmdId --instance-id $InstanceId --query "Status" --output text
            if ($status -in @("Success","Failed","Cancelled","TimedOut")) { break }
        }
        $out = Aws ssm get-command-invocation --command-id $cmdId --instance-id $InstanceId --query "StandardOutputContent" --output text
        return [pscustomobject]@{ Status = $status; Output = $out }
    } finally { Remove-Item $tmp -ErrorAction SilentlyContinue }
}

# preflight
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) { Die "'ssh' not found on PATH (install OpenSSH client)." }
if (-not (Test-Path $PemPath)) { Die "Key not found: $PemPath. Run deploy-aws.ps1 first." }
try { Aws sts get-caller-identity --output text | Out-Null } catch { Die "No valid AWS session. Run: aws sso login --profile $Profile" }

# find the instance
Info "Locating the $ProjectTag instance..."
$InstanceId = Aws ec2 describe-instances --filters "Name=tag:project,Values=$ProjectTag" "Name=instance-state-name,Values=pending,running,stopped,stopping" --query "Reservations[0].Instances[0].InstanceId" --output text
if (-not $InstanceId) { Die "No $ProjectTag instance found. Run deploy-aws.ps1 first." }

$State = Aws ec2 describe-instances --instance-ids $InstanceId --query "Reservations[0].Instances[0].State.Name" --output text
if ($State -eq "stopped") {
    Warn "Instance $InstanceId is stopped."
    $ans = Read-Host "Start it now? (y/n)"
    if ($ans -eq "y") {
        Info "Starting $InstanceId..."
        Aws ec2 start-instances --instance-ids $InstanceId | Out-Null
        Aws ec2 wait instance-running --instance-ids $InstanceId | Out-Null
        Ok "Started"
    } else { Die "Instance not running; nothing to tunnel to." }
} elseif ($State -ne "running") {
    Info "Instance state is '$State'; waiting for running..."
    Aws ec2 wait instance-running --instance-ids $InstanceId | Out-Null
}

$PublicIp = Aws ec2 describe-instances --instance-ids $InstanceId --query "Reservations[0].Instances[0].PublicIpAddress" --output text
if (-not $PublicIp) { Die "Instance has no public IP." }
Ok "Instance $InstanceId at $PublicIp"

# quick reachability hint (non-fatal): if blocked, it's usually the egress-IP SG rule
if (-not (Test-NetConnection -ComputerName $PublicIp -Port 22 -WarningAction SilentlyContinue -InformationLevel Quiet)) {
    Warn "TCP 22 to $PublicIp not reachable yet. If this persists, your egress IP may have changed;"
    Warn "re-run deploy-aws.ps1 to re-lock the security group to your current IP."
}

# Ensure the app stack is actually UP on the instance before we forward ports to
# it. When the instance is stopped/started the containers do NOT auto-start, so
# the tunnel would forward localhost:3000 to a dead port and the browser shows
# "Unable to connect". We bring the compose stack up over SSM and wait for the
# frontend to answer, so a silent tunnel window always means a working app.
Info "Ensuring the app stack is running on the instance (via SSM)..."
# NON-FATAL: this is a best-effort convenience (the systemd unit already brings
# the stack up on boot). Wrap it so a transient SSM/CLI error here can NEVER
# abort the script before the tunnel opens - the tunnel is the whole point.
$ensure = $null
try {
    $ensure = Invoke-Ssm -InstanceId $InstanceId -TimeoutSec 240 -Commands @(
        "cd $RemoteDir || { echo 'NO_REPO_DIR'; exit 1; }",
        # Drop any stale non-committed instance-role override left by an earlier
        # manual workaround; it would shadow the committed Bedrock layering below.
        "rm -f docker-compose.instance-role.yml",
        # Instance-role Bedrock layering: base + bedrock default (no AWS_PROFILE, no
        # ~/.aws mount), so boto3 uses the EC2 instance role.
        "sudo docker compose -f docker-compose.yml -f docker-compose.bedrock.yml up -d 2>&1 | tail -30",
        "echo '--- waiting for frontend ---'",
        "for i in `$(seq 1 30); do code=`$(curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/ || echo 000); if [ `"`$code`" = '200' ]; then break; fi; sleep 2; done",
        "echo FRONTEND_HTTP=`$(curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/ || echo 000)",
        "echo BACKEND_HEALTH=`$(curl -s http://localhost:8008/health || echo unreachable)"
    )
} catch {
    Warn "Could not reach the instance over SSM ($_)."
    Warn "Skipping the stack pre-check; the boot-time service has likely started it already. Opening the tunnel anyway."
}
if ($null -eq $ensure) {
    # SSM unavailable; fall through to the tunnel (app is usually up via systemd).
} elseif ($ensure.Output -match "NO_REPO_DIR") {
    Warn "App repo not found at $RemoteDir on the instance. The stack was never deployed here."
    Warn "Run  pwsh ./scripts/deploy-aws.ps1  first, then re-run this script."
} elseif ($ensure.Status -ne "Success") {
    Warn "Could not confirm the stack via SSM (status: $($ensure.Status)). Proceeding to open the tunnel anyway;"
    Warn "if the browser can't connect, the app may still be starting on the instance."
} else {
    $feCode = if ($ensure.Output -match 'FRONTEND_HTTP=(\d+)') { $Matches[1] } else { "000" }
    $beLine = if ($ensure.Output -match 'BACKEND_HEALTH=(.+)')  { $Matches[1].Trim() } else { "unknown" }
    if ($feCode -eq "200") { Ok "App is up on the instance (frontend 200; backend: $beLine)" }
    else { Warn "Frontend returned HTTP $feCode on the instance (backend: $beLine). It may still be warming up; give it ~30s after the tunnel opens." }
}

# Local-port preflight. ssh below uses -o ExitOnForwardFailure=yes, which means
# if ANY of 3000/3001/8008 is already bound locally (almost always a PREVIOUS
# tunnel still running in another window), ssh refuses to open and exits at once
# with no useful message. This is the #1 reason "the script does nothing but the
# manual ssh works". So: detect who holds the ports, and offer to close a stale
# tunnel so this one can bind.
$TunnelPorts = 3000,3001,8008
$held = Get-NetTCPConnection -State Listen -LocalPort $TunnelPorts -ErrorAction SilentlyContinue
if ($held) {
    $pids = $held | Select-Object -ExpandProperty OwningProcess -Unique
    $busyPorts = ($held | Select-Object -ExpandProperty LocalPort -Unique | Sort-Object) -join ", "
    Warn "Local port(s) already in use: $busyPorts"
    $sshHolders  = @()
    $otherHolders = @()
    foreach ($procId in $pids) {
        $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($p -and $p.ProcessName -eq "ssh") { $sshHolders += $p } elseif ($p) { $otherHolders += $p }
    }
    if ($otherHolders) {
        foreach ($p in $otherHolders) { Warn "  Port held by non-ssh process: $($p.ProcessName) (PID $($p.Id)) - not touching it." }
        Die "A non-tunnel process is using a required port. Free it (or stop that app) and re-run. The tunnel cannot bind while it's taken."
    }
    if ($sshHolders) {
        Warn "  These look like an EXISTING tunnel (ssh PID(s): $(( $sshHolders.Id ) -join ', '))."
        Warn "  If that tunnel is already working, you can just use your browser - no need to re-run this."
        $ans = Read-Host "Close the existing tunnel and open a fresh one? (y/n)"
        if ($ans -eq "y") {
            foreach ($p in $sshHolders) { try { Stop-Process -Id $p.Id -Force -ErrorAction Stop; Ok "  Closed stale tunnel (PID $($p.Id))" } catch { Warn "  Could not stop PID $($p.Id): $_" } }
            Start-Sleep -Seconds 1
            if (Get-NetTCPConnection -State Listen -LocalPort $TunnelPorts -ErrorAction SilentlyContinue) {
                Die "Ports still in use after closing. Wait a few seconds and re-run, or close the other terminal manually."
            }
            Ok "Ports freed; opening a fresh tunnel."
        } else {
            Die "Leaving the existing tunnel in place. Nothing to do - switch to your browser at http://localhost:3000."
        }
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Ok "TUNNEL IS NOW OPENING. This window will go SILENT and look frozen."
Write-Host "    That silence is normal - it means the tunnel is working." -ForegroundColor Yellow
Write-Host "    >> Leave THIS window open and untouched. <<" -ForegroundColor Yellow
Write-Host "    >> Switch to your BROWSER to use the app.  <<" -ForegroundColor Yellow
Write-Host "    Press Ctrl+C here ONLY when you want to close the tunnel."
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host " Browse (while this window stays open):"
Write-Host "   App     : http://localhost:3000  (login: lava@dev.com / MahaloDock123!)"
Write-Host "   Gitea   : http://localhost:3001  (admin: mahalo_admin / MahaloDock123!)"
Write-Host "   Backend : http://localhost:8008/health"
Write-Host ""
# We cannot probe localhost here: the ssh call below runs in the FOREGROUND and
# blocks this terminal for the life of the tunnel, so there is no moment after
# it to curl. Instead, tell the user how to verify the forward from a SECOND
# terminal, and pre-empt the most common false alarm (a Firefox/localhost proxy
# setting, not a dead tunnel).
Write-Host " Verify the tunnel from a SECOND terminal (optional):" -ForegroundColor Yellow
Write-Host "   curl.exe -v http://localhost:3000/        # note curl.exe, not PowerShell's curl alias"
Write-Host "   A 200/HTML response means the forward works."
Write-Host ""
Write-Host " If the browser says ""Unable to connect"" at localhost:3000:" -ForegroundColor Yellow
Write-Host "   1. Confirm THIS tunnel window is still open (it should look frozen)."
Write-Host "   2. It is often a Firefox/localhost PROXY setting, not a dead tunnel:"
Write-Host "      Firefox Settings > Network Settings, ensure 'No proxy' for localhost"
Write-Host "      (or add localhost,127.0.0.1 to 'No proxy for'). The curl.exe probe"
Write-Host "      above bypasses the browser proxy, so if curl works but Firefox"
Write-Host "      doesn't, it's the proxy."
Write-Host ""

# Foreground tunnel; -N = no remote shell, just port forwarding. Keepalives are
# tuned so a brief network blip does not silently drop the tunnel:
#   ServerAliveInterval=30  -> ping the server every 30s
#   ServerAliveCountMax=3    -> only give up after 3 missed pings (~90s)
#   ExitOnForwardFailure=yes -> fail loudly if a local port is already taken
# NOTE: this command intentionally does NOT return until the tunnel closes.
ssh -i $PemPath `
    -o StrictHostKeyChecking=accept-new `
    -o ServerAliveInterval=30 `
    -o ServerAliveCountMax=3 `
    -o ExitOnForwardFailure=yes `
    -N `
    -L 3000:localhost:3000 `
    -L 3001:localhost:3001 `
    -L 8008:localhost:8008 `
    ubuntu@$PublicIp

# If ssh returns, the tunnel closed (Ctrl+C, dropped connection, or a port was
# already in use). The ports stop forwarding and the browser will show
# ERR_CONNECTION_REFUSED until you re-run this script.
Write-Host ""
Warn "Tunnel closed. localhost:3000/3001/8008 will no longer connect."
Warn "Re-run this script to reopen it."
