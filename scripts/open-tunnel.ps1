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

function Info($m){ Write-Host "[*] $m" -ForegroundColor Cyan }
function Ok($m){   Write-Host "[+] $m" -ForegroundColor Green }
function Warn($m){ Write-Host "[!] $m" -ForegroundColor Yellow }
function Die($m){  Write-Host "[x] $m" -ForegroundColor Red; exit 1 }

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

Write-Host ""
Ok "Opening tunnel. Browse while this stays open:"
Write-Host "   App     : http://localhost:3000"
Write-Host "   Gitea   : http://localhost:3001  (mahalo_admin / MahaloDock123!)"
Write-Host "   Backend : http://localhost:8008/health"
Write-Host "   (Ctrl+C to close the tunnel)"
Write-Host ""

# foreground tunnel; -N = no remote shell, just forwarding
ssh -i $PemPath -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -N `
    -L 3000:localhost:3000 `
    -L 3001:localhost:3001 `
    -L 8008:localhost:8008 `
    ubuntu@$PublicIp
