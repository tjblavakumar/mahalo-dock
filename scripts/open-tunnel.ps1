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

# Every message is flushed to the console immediately via [Console]::Out so the
# user sees progress the instant each step runs. Plain Write-Host can sit in a
# buffer when the script ends in a long-blocking process (the ssh tunnel), which
# is why earlier versions looked frozen with "no output" for a long time.
function Info($m){ Write-Host "[*] $m" -ForegroundColor Cyan;   [Console]::Out.Flush() }
function Ok($m){   Write-Host "[+] $m" -ForegroundColor Green;  [Console]::Out.Flush() }
function Warn($m){ Write-Host "[!] $m" -ForegroundColor Yellow; [Console]::Out.Flush() }
function Die($m){  Write-Host "[x] $m" -ForegroundColor Red;    [Console]::Out.Flush(); exit 1 }

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

# NOTE: we deliberately do NOT run a slow SSM "is the app up?" pre-check here.
# The instance installs a systemd unit (mahalo-dock.service) that starts the
# compose stack on every boot, so by the time you can SSH in, the app is already
# coming up. The old SSM pre-check polled for up to ~4 minutes with NO output,
# which made the script look frozen/hung - the single biggest source of the
# "it just hangs with no feedback" problem. The tunnel is the whole point, so we
# open it immediately. If the app genuinely isn't up yet, the browser shows it
# within seconds and you simply refresh after ~30s.
#
# If you ever DO need to (re)start the stack on the instance by hand, SSH in and:
#   cd /home/ubuntu/mahalo-dock
#   sudo docker compose -f docker-compose.yml -f docker-compose.bedrock.yml up -d

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

Info "Opening SSH tunnel to ubuntu@$PublicIp (verbose, so you can SEE it connect)..."
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Ok "TUNNEL STARTING. Watch for this line, which means it is WORKING:"
Write-Host "      debug1: Local forwarding listening on 127.0.0.1 port 3000." -ForegroundColor Green
Write-Host "    After the forwarding lines appear, the window stays open and" -ForegroundColor Yellow
Write-Host "    quiet - that is the tunnel running. Leave it open." -ForegroundColor Yellow
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

# Foreground tunnel. -v makes ssh print connection + forwarding progress so the
# window is NEVER a silent mystery: you will see "Authenticated to ..." and
# "Local forwarding listening on 127.0.0.1 port 3000/3001/8008". -N = no remote
# shell, just port forwarding. Keepalives keep a brief network blip from
# silently dropping the tunnel:
#   ServerAliveInterval=30  -> ping the server every 30s
#   ServerAliveCountMax=3    -> only give up after 3 missed pings (~90s)
#   ExitOnForwardFailure=yes -> fail loudly if a local port is already taken
# NOTE: this command intentionally does NOT return until the tunnel closes.
ssh -v -i $PemPath `
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
