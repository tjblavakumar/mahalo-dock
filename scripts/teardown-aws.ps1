<#
.SYNOPSIS
    Tear down (or just stop) the MAHALO-dock AWS resources created by
    deploy-aws.ps1. Everything is selected by the project=mahalo-dock tag.

.DESCRIPTION
    Two modes:
      -StopOnly : stop the EC2 instance only (keeps all infra + EBS). Cheapest
                  pause between demos; restart later with deploy-aws.ps1.
      (default) : full teardown in reverse dependency order — terminate the
                  instance, then IAM, SG, routing, subnet, IGW, VPC, key pair.

    Idempotent and safe to re-run: missing resources are skipped. Since the
    account resets monthly, this is mainly for cleaning up mid-month or removing
    orphans before a fresh deploy.

.PARAMETER StopOnly
    Only stop the instance; leave all other resources in place.

.PARAMETER Force
    Skip the confirmation prompt (useful for automation).

.EXAMPLE
    pwsh ./scripts/teardown-aws.ps1 -StopOnly
    pwsh ./scripts/teardown-aws.ps1 -Force
#>

[CmdletBinding()]
param(
    [string]$Profile = "lava",
    [string]$Region  = "us-east-1",
    [string]$KeyName = "mahalo-dock-key",
    [switch]$StopOnly,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectTag = "mahalo-dock"
$RoleName    = "$ProjectTag-ec2-role"
$ProfileName = "$ProjectTag-ec2-profile"
$PemPath     = Join-Path $env:USERPROFILE ".ssh\$KeyName.pem"

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
# Best-effort variant: swallow errors (resource already gone / dependency timing).
function Try-Aws { param([string[]]$Args) try { Aws @Args | Out-Null; return $true } catch { Warn "skip: aws $($Args -join ' ')  ($($_ -replace '\s+',' '))"; return $false } }

Info "Verifying AWS session..."
try { $ident = Aws sts get-caller-identity --output json | ConvertFrom-Json } catch { Die "No valid AWS session. Run: aws sso login --profile $Profile" }
Ok "Account $($ident.Account)"

# locate the instance
$InstanceId = Aws ec2 describe-instances --filters "Name=tag:project,Values=$ProjectTag" "Name=instance-state-name,Values=pending,running,stopped,stopping" --query "Reservations[0].Instances[0].InstanceId" --output text

# ----- STOP ONLY ------------------------------------------------------------
if ($StopOnly) {
    if (-not $InstanceId) { Warn "No instance found to stop."; exit 0 }
    Info "Stopping instance $InstanceId (keeps infra + EBS)..."
    Aws ec2 stop-instances --instance-ids $InstanceId | Out-Null
    Aws ec2 wait instance-stopped --instance-ids $InstanceId | Out-Null
    Ok "Instance stopped. Restart later with deploy-aws.ps1 (it reuses this instance)."
    exit 0
}

# ----- FULL TEARDOWN --------------------------------------------------------
if (-not $Force) {
    Write-Host "This will DELETE all mahalo-dock AWS resources in $($ident.Account)/$Region (instance, VPC, IAM role, etc.)." -ForegroundColor Yellow
    $ans = Read-Host "Type 'yes' to proceed"
    if ($ans -ne "yes") { Die "Aborted." }
}

# 1. terminate instance
if ($InstanceId) {
    Info "Terminating instance $InstanceId..."
    Try-Aws @("ec2","terminate-instances","--instance-ids",$InstanceId) | Out-Null
    try { Aws ec2 wait instance-terminated --instance-ids $InstanceId | Out-Null; Ok "Instance terminated" } catch { Warn "Wait for termination timed out; continuing." }
} else { Warn "No instance found." }

# 2. IAM: detach + delete instance profile and role
if (Try-Aws @("iam","get-instance-profile","--instance-profile-name",$ProfileName)) {
    Try-Aws @("iam","remove-role-from-instance-profile","--instance-profile-name",$ProfileName,"--role-name",$RoleName) | Out-Null
    Try-Aws @("iam","delete-instance-profile","--instance-profile-name",$ProfileName) | Out-Null
    Ok "Deleted instance profile"
}
if (Try-Aws @("iam","get-role","--role-name",$RoleName)) {
    Try-Aws @("iam","delete-role-policy","--role-name",$RoleName,"--policy-name","bedrock-invoke") | Out-Null
    Try-Aws @("iam","detach-role-policy","--role-name",$RoleName,"--policy-arn","arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore") | Out-Null
    Try-Aws @("iam","delete-role","--role-name",$RoleName) | Out-Null
    Ok "Deleted IAM role"
}

# 3. key pair (AWS + local pem)
Try-Aws @("ec2","delete-key-pair","--key-name",$KeyName) | Out-Null
if (Test-Path $PemPath) { Remove-Item $PemPath -Force; Ok "Removed local pem $PemPath" }

# resolve the VPC for the networking teardown
$VpcId = Aws ec2 describe-vpcs --filters "Name=tag:project,Values=$ProjectTag" --query "Vpcs[0].VpcId" --output text
if ($VpcId) {
    # 4. security group (can't delete the default; ours is tagged)
    $SgId = Aws ec2 describe-security-groups --filters "Name=tag:project,Values=$ProjectTag" "Name=vpc-id,Values=$VpcId" --query "SecurityGroups[0].GroupId" --output text
    if ($SgId) { Try-Aws @("ec2","delete-security-group","--group-id",$SgId) | Out-Null; Ok "Deleted security group $SgId" }

    # 5. route table (disassociate non-main assoc first, then delete)
    $RtId = Aws ec2 describe-route-tables --filters "Name=tag:project,Values=$ProjectTag" "Name=vpc-id,Values=$VpcId" --query "RouteTables[0].RouteTableId" --output text
    if ($RtId) {
        $assocIds = (Aws ec2 describe-route-tables --route-table-ids $RtId --query "RouteTables[0].Associations[?Main==``false``].RouteTableAssociationId" --output text) -split "\s+" | Where-Object { $_ }
        foreach ($a in $assocIds) { Try-Aws @("ec2","disassociate-route-table","--association-id",$a) | Out-Null }
        Try-Aws @("ec2","delete-route-table","--route-table-id",$RtId) | Out-Null; Ok "Deleted route table $RtId"
    }

    # 6. internet gateway (detach then delete)
    $IgwId = Aws ec2 describe-internet-gateways --filters "Name=tag:project,Values=$ProjectTag" --query "InternetGateways[0].InternetGatewayId" --output text
    if ($IgwId) {
        Try-Aws @("ec2","detach-internet-gateway","--internet-gateway-id",$IgwId,"--vpc-id",$VpcId) | Out-Null
        Try-Aws @("ec2","delete-internet-gateway","--internet-gateway-id",$IgwId) | Out-Null; Ok "Deleted IGW $IgwId"
    }

    # 7. subnet
    $SubnetId = Aws ec2 describe-subnets --filters "Name=tag:project,Values=$ProjectTag" "Name=vpc-id,Values=$VpcId" --query "Subnets[0].SubnetId" --output text
    if ($SubnetId) { Try-Aws @("ec2","delete-subnet","--subnet-id",$SubnetId) | Out-Null; Ok "Deleted subnet $SubnetId" }

    # 8. VPC
    Try-Aws @("ec2","delete-vpc","--vpc-id",$VpcId) | Out-Null; Ok "Deleted VPC $VpcId"
} else { Warn "No tagged VPC found; networking already clean." }

Ok "Teardown complete."
