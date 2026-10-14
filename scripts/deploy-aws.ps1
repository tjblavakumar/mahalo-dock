<#
.SYNOPSIS
    One-shot deploy of the MAHALO-dock demo stack onto a fresh AWS account:
    networking (VPC/subnet/IGW/route), security group, key pair, Bedrock IAM
    role, an EC2 instance, then Docker + the compose stack in Bedrock mode.

.DESCRIPTION
    Built to be re-run after the monthly account reset. It is IDEMPOTENT: every
    resource is looked up by its Name/project tag before creation, so a second
    run (or a resumed partial run) reuses what already exists instead of making
    duplicates. It also:
      - detects the workspace's current public egress IP each run and locks the
        security group's inbound SSH to that /32 (the IP can change between runs);
      - auto-resolves the active Bedrock Claude Sonnet inference profile id
        rather than hardcoding a model that may rotate;
      - reuses the EC2 key pair + local .pem when both exist, else creates fresh;
      - clones the repo on the instance, writes .env for Bedrock, and (belt &
        suspenders) strips any empty AWS_PROFILE line from the compose so the
        instance role is used even on an unpatched checkout;
      - prints the ready-to-paste SSH tunnel command and a resource summary.

    This script creates BILLABLE resources (t3.medium + 30 GB gp3). Stop or tear
    down the instance when idle (see teardown-aws.ps1).

.PARAMETER Profile
    AWS CLI profile to use. Default: lava.

.PARAMETER Region
    AWS region. Default: us-east-1.

.EXAMPLE
    pwsh ./scripts/deploy-aws.ps1
    # then: aws sso login --profile lava   (if the session has expired)

.NOTES
    Prereqs on the workspace: AWS CLI v2, OpenSSH client (ssh/scp), a valid SSO
    session (aws sso login --profile <profile>). Run from anywhere; paths are
    resolved relative to the repo.
#>

[CmdletBinding()]
param(
    [string]$Profile = "lava",
    [string]$Region  = "us-east-1",
    [string]$RepoUrl = "https://github.com/tjblavakumar/mahalo-dock.git",
    [string]$KeyName = "mahalo-dock-key",
    [string]$InstanceType = "t3.medium",
    [int]$VolumeSizeGb = 30
)

$ErrorActionPreference = "Stop"
$ProjectTag = "mahalo-dock"
$PemPath    = Join-Path $env:USERPROFILE ".ssh\$KeyName.pem"

# ---------- helpers ---------------------------------------------------------
function Info($msg)  { Write-Host "[*] $msg"  -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "[+] $msg"  -ForegroundColor Green }
function Warn($msg)  { Write-Host "[!] $msg"  -ForegroundColor Yellow }
function Die($msg)   { Write-Host "[x] $msg"  -ForegroundColor Red; exit 1 }

# Run an aws cli call; returns trimmed stdout. Treats the literal "None"/"" as null.
function Aws {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    $out = & aws @Args --profile $Profile --region $Region 2>&1
    if ($LASTEXITCODE -ne 0) { throw "aws $($Args -join ' ') failed: $out" }
    $s = ($out | Out-String).Trim()
    if ($s -eq "None") { return "" }
    return $s
}

# SSH a heredoc-free script to the instance via stdin, stripping CR so bash is happy.
function Invoke-Remote {
    param([string]$Ip, [string]$Script)
    $Script -replace "`r","" | ssh -i $PemPath -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 ubuntu@$Ip "bash -s" 2>&1
}

# ---------- 0. preflight -----------------------------------------------------
Info "Verifying AWS session for profile '$Profile' in '$Region'..."
try { $ident = Aws sts get-caller-identity --output json | ConvertFrom-Json }
catch { Die "No valid AWS session. Run:  aws sso login --profile $Profile" }
Ok "Authenticated as account $($ident.Account) ($($ident.Arn))"

foreach ($bin in @("ssh","scp")) {
    if (-not (Get-Command $bin -ErrorAction SilentlyContinue)) { Die "'$bin' not found on PATH (install OpenSSH client)." }
}

Info "Detecting workspace public egress IP..."
$MyIp = (Invoke-RestMethod -Uri "https://checkip.amazonaws.com").Trim()
if (-not ($MyIp -match '^\d{1,3}(\.\d{1,3}){3}$')) { Die "Could not determine egress IP (got '$MyIp')." }
Ok "Egress IP: $MyIp  (SSH will be locked to $MyIp/32)"

# ---------- 1. VPC -----------------------------------------------------------
Info "Ensuring VPC..."
$VpcId = Aws ec2 describe-vpcs --filters "Name=tag:project,Values=$ProjectTag" --query "Vpcs[0].VpcId" --output text
if (-not $VpcId) {
    $VpcId = Aws ec2 create-vpc --cidr-block 10.0.0.0/16 `
        --tag-specifications "ResourceType=vpc,Tags=[{Key=Name,Value=$ProjectTag},{Key=project,Value=$ProjectTag}]" `
        --query "Vpc.VpcId" --output text
    Aws ec2 modify-vpc-attribute --vpc-id $VpcId --enable-dns-hostnames | Out-Null
    Aws ec2 modify-vpc-attribute --vpc-id $VpcId --enable-dns-support   | Out-Null
    Ok "Created VPC $VpcId"
} else { Ok "Reusing VPC $VpcId" }

# ---------- 2. Internet gateway ---------------------------------------------
Info "Ensuring internet gateway..."
$IgwId = Aws ec2 describe-internet-gateways --filters "Name=tag:project,Values=$ProjectTag" --query "InternetGateways[0].InternetGatewayId" --output text
if (-not $IgwId) {
    $IgwId = Aws ec2 create-internet-gateway `
        --tag-specifications "ResourceType=internet-gateway,Tags=[{Key=Name,Value=$ProjectTag},{Key=project,Value=$ProjectTag}]" `
        --query "InternetGateway.InternetGatewayId" --output text
    Ok "Created IGW $IgwId"
} else { Ok "Reusing IGW $IgwId" }
# attach if not already attached to our VPC
$attached = Aws ec2 describe-internet-gateways --internet-gateway-ids $IgwId --query "InternetGateways[0].Attachments[0].VpcId" --output text
if ($attached -ne $VpcId) {
    Aws ec2 attach-internet-gateway --internet-gateway-id $IgwId --vpc-id $VpcId | Out-Null
    Ok "Attached IGW to $VpcId"
}

# ---------- 3. Subnet --------------------------------------------------------
Info "Ensuring public subnet..."
$SubnetId = Aws ec2 describe-subnets --filters "Name=tag:project,Values=$ProjectTag" "Name=vpc-id,Values=$VpcId" --query "Subnets[0].SubnetId" --output text
if (-not $SubnetId) {
    $SubnetId = Aws ec2 create-subnet --vpc-id $VpcId --cidr-block 10.0.1.0/24 --availability-zone "${Region}a" `
        --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=$ProjectTag-public},{Key=project,Value=$ProjectTag}]" `
        --query "Subnet.SubnetId" --output text
    Aws ec2 modify-subnet-attribute --subnet-id $SubnetId --map-public-ip-on-launch | Out-Null
    Ok "Created subnet $SubnetId"
} else { Ok "Reusing subnet $SubnetId" }

# ---------- 4. Route table ---------------------------------------------------
Info "Ensuring route table + default route..."
$RtId = Aws ec2 describe-route-tables --filters "Name=tag:project,Values=$ProjectTag" "Name=vpc-id,Values=$VpcId" --query "RouteTables[0].RouteTableId" --output text
if (-not $RtId) {
    $RtId = Aws ec2 create-route-table --vpc-id $VpcId `
        --tag-specifications "ResourceType=route-table,Tags=[{Key=Name,Value=$ProjectTag-public},{Key=project,Value=$ProjectTag}]" `
        --query "RouteTable.RouteTableId" --output text
    Ok "Created route table $RtId"
} else { Ok "Reusing route table $RtId" }
# default route (ignore if it already exists)
try { Aws ec2 create-route --route-table-id $RtId --destination-cidr-block 0.0.0.0/0 --gateway-id $IgwId | Out-Null; Ok "Added default route -> IGW" }
catch { if ($_ -match "RouteAlreadyExists") { Ok "Default route already present" } else { throw } }
# associate subnet if not associated
$assoc = Aws ec2 describe-route-tables --route-table-ids $RtId --query "RouteTables[0].Associations[?SubnetId=='$SubnetId'] | [0].RouteTableAssociationId" --output text
if (-not $assoc) { Aws ec2 associate-route-table --route-table-id $RtId --subnet-id $SubnetId | Out-Null; Ok "Associated route table with subnet" }

# ---------- 5. Security group ------------------------------------------------
Info "Ensuring security group..."
$SgId = Aws ec2 describe-security-groups --filters "Name=tag:project,Values=$ProjectTag" "Name=vpc-id,Values=$VpcId" --query "SecurityGroups[0].GroupId" --output text
if (-not $SgId) {
    $SgId = Aws ec2 create-security-group --group-name "$ProjectTag-sg" --description "$ProjectTag SSH only" --vpc-id $VpcId `
        --tag-specifications "ResourceType=security-group,Tags=[{Key=Name,Value=$ProjectTag},{Key=project,Value=$ProjectTag}]" `
        --query "GroupId" --output text
    Ok "Created security group $SgId"
} else { Ok "Reusing security group $SgId" }
# Reconcile inbound SSH to CURRENT egress IP: revoke any TCP/22 rules that aren't ours, then ensure ours exists.
$existingCidrs = (Aws ec2 describe-security-groups --group-ids $SgId --query "SecurityGroups[0].IpPermissions[?FromPort==``22``].IpRanges[].CidrIp" --output text) -split "\s+" | Where-Object { $_ }
foreach ($cidr in $existingCidrs) {
    if ($cidr -and $cidr -ne "$MyIp/32") {
        try { Aws ec2 revoke-security-group-ingress --group-id $SgId --ip-permissions "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=$cidr}]" | Out-Null; Warn "Revoked stale SSH rule for $cidr" } catch {}
    }
}
if ($existingCidrs -notcontains "$MyIp/32") {
    try { Aws ec2 authorize-security-group-ingress --group-id $SgId --ip-permissions "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=$MyIp/32,Description=workspace-egress}]" | Out-Null; Ok "Allowed inbound SSH from $MyIp/32" }
    catch { if ($_ -match "Duplicate") { Ok "SSH rule already present" } else { throw } }
} else { Ok "SSH rule for $MyIp/32 already present" }

# ---------- 6. Key pair ------------------------------------------------------
Info "Ensuring key pair..."
$kpExists = $false
try { Aws ec2 describe-key-pairs --key-names $KeyName | Out-Null; $kpExists = $true } catch { $kpExists = $false }
if ($kpExists -and (Test-Path $PemPath)) {
    Ok "Reusing key pair '$KeyName' and local pem $PemPath"
} else {
    if ($kpExists) { Warn "Key pair '$KeyName' exists in AWS but local pem missing; recreating both."; Aws ec2 delete-key-pair --key-name $KeyName | Out-Null }
    New-Item -ItemType Directory -Force -Path (Split-Path $PemPath) | Out-Null
    $material = Aws ec2 create-key-pair --key-name $KeyName --key-type rsa `
        --tag-specifications "ResourceType=key-pair,Tags=[{Key=project,Value=$ProjectTag}]" `
        --query "KeyMaterial" --output text
    $material | Out-File -FilePath $PemPath -Encoding ascii
    icacls $PemPath /inheritance:r /grant:r "$($env:USERNAME):(R)" | Out-Null
    Ok "Created key pair; saved pem to $PemPath (permissions locked)"
}

# ---------- 7. IAM role + instance profile ----------------------------------
Info "Ensuring IAM role + instance profile (Bedrock + SSM)..."
$RoleName    = "$ProjectTag-ec2-role"
$ProfileName = "$ProjectTag-ec2-profile"
$roleExists = $false
try { Aws iam get-role --role-name $RoleName | Out-Null; $roleExists = $true } catch { $roleExists = $false }
if (-not $roleExists) {
    $trust = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
    $trustFile = Join-Path $env:TEMP "mahalo-trust.json"; $trust | Out-File $trustFile -Encoding ascii
    Aws iam create-role --role-name $RoleName --assume-role-policy-document "file://$trustFile" --tags "Key=project,Value=$ProjectTag" | Out-Null
    Ok "Created role $RoleName"
} else { Ok "Reusing role $RoleName" }
# (re)apply inline Bedrock policy (idempotent) + attach SSM managed policy
$pol = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream","bedrock:Converse","bedrock:ConverseStream"],"Resource":"*"}]}'
$polFile = Join-Path $env:TEMP "mahalo-bedrock.json"; $pol | Out-File $polFile -Encoding ascii
Aws iam put-role-policy --role-name $RoleName --policy-name bedrock-invoke --policy-document "file://$polFile" | Out-Null
try { Aws iam attach-role-policy --role-name $RoleName --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore | Out-Null } catch {}
Ok "Bedrock + SSM policies in place"
# instance profile
$ipExists = $false
try { Aws iam get-instance-profile --instance-profile-name $ProfileName | Out-Null; $ipExists = $true } catch { $ipExists = $false }
if (-not $ipExists) {
    Aws iam create-instance-profile --instance-profile-name $ProfileName --tags "Key=project,Value=$ProjectTag" | Out-Null
    Aws iam add-role-to-instance-profile --instance-profile-name $ProfileName --role-name $RoleName | Out-Null
    Ok "Created instance profile $ProfileName"
    Start-Sleep -Seconds 10   # allow IAM propagation before launch
} else { Ok "Reusing instance profile $ProfileName" }

# ---------- 8. Resolve latest Ubuntu AMI ------------------------------------
Info "Resolving latest Ubuntu 24.04 AMI..."
$AmiId = Aws ssm get-parameters --names "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id" --query "Parameters[0].Value" --output text
if (-not $AmiId) { Die "Could not resolve Ubuntu AMI." }
Ok "AMI: $AmiId"

# ---------- 9. Launch (or reuse) the instance -------------------------------
Info "Ensuring EC2 instance..."
$InstanceId = Aws ec2 describe-instances --filters "Name=tag:project,Values=$ProjectTag" "Name=instance-state-name,Values=pending,running,stopped,stopping" --query "Reservations[0].Instances[0].InstanceId" --output text
if (-not $InstanceId) {
    $InstanceId = Aws ec2 run-instances --image-id $AmiId --instance-type $InstanceType --key-name $KeyName `
        --subnet-id $SubnetId --security-group-ids $SgId --iam-instance-profile "Name=$ProfileName" `
        --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=$VolumeSizeGb,VolumeType=gp3}" `
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$ProjectTag},{Key=project,Value=$ProjectTag}]" `
        --query "Instances[0].InstanceId" --output text
    Ok "Launched instance $InstanceId"
} else {
    Ok "Reusing instance $InstanceId"
    $state = Aws ec2 describe-instances --instance-ids $InstanceId --query "Reservations[0].Instances[0].State.Name" --output text
    if ($state -eq "stopped" -or $state -eq "stopping") { Info "Starting stopped instance..."; Aws ec2 start-instances --instance-ids $InstanceId | Out-Null }
}
Info "Waiting for instance to be running..."
Aws ec2 wait instance-running --instance-ids $InstanceId | Out-Null
$PublicIp = Aws ec2 describe-instances --instance-ids $InstanceId --query "Reservations[0].Instances[0].PublicIpAddress" --output text
Ok "Instance running at $PublicIp"

# ---------- 10. Wait for SSH -------------------------------------------------
Info "Waiting for SSH (TCP 22) to accept connections..."
$sshReady = $false
for ($i = 0; $i -lt 30; $i++) {
    $t = Test-NetConnection -ComputerName $PublicIp -Port 22 -WarningAction SilentlyContinue -InformationLevel Quiet
    if ($t) { $sshReady = $true; break }
    Start-Sleep -Seconds 10
}
if (-not $sshReady) { Die "SSH to $PublicIp:22 not reachable. Check the security group / egress IP ($MyIp)." }
Ok "SSH reachable"

# ---------- 11. Resolve Bedrock Sonnet inference profile --------------------
Info "Resolving active Bedrock Claude Sonnet inference profile..."
$BedrockModel = Aws bedrock list-inference-profiles --query "sort_by(inferenceProfileSummaries[?starts_with(inferenceProfileId, 'us.anthropic.claude-sonnet-4-5') && status=='ACTIVE'], &inferenceProfileId)[-1].inferenceProfileId" --output text
if (-not $BedrockModel) {
    $BedrockModel = Aws bedrock list-inference-profiles --query "sort_by(inferenceProfileSummaries[?contains(inferenceProfileId, 'anthropic.claude-sonnet') && status=='ACTIVE'], &inferenceProfileId)[-1].inferenceProfileId" --output text
}
if (-not $BedrockModel) { Warn "No active Sonnet inference profile found. Enable Bedrock model access, then re-run. Using placeholder."; $BedrockModel = "us.anthropic.claude-sonnet-4-5-20250929-v1:0" }
Ok "Bedrock model: $BedrockModel"

# ---------- 12. Provision the instance (Docker, git, clone, .env, stack) ----
Info "Provisioning instance (Docker + Git + clone + .env + stack)... this takes several minutes."
$remote = @"
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# --- Docker + Git (idempotent) ---
if ! command -v git >/dev/null; then sudo apt-get update -y && sudo apt-get install -y git ca-certificates curl; fi
if ! command -v docker >/dev/null; then curl -fsSL https://get.docker.com | sudo sh; sudo usermod -aG docker ubuntu; fi

# --- Clone or update the repo ---
if [ ! -d /home/ubuntu/mahalo-dock/.git ]; then
  git clone $RepoUrl /home/ubuntu/mahalo-dock
else
  cd /home/ubuntu/mahalo-dock && git pull --ff-only || true
fi
cd /home/ubuntu/mahalo-dock

# --- .env for Bedrock mode ---
cp -f .env.example .env
sed -i 's|^LLM_PROVIDER=.*|LLM_PROVIDER=bedrock|' .env
sed -i 's|^SYNTHESIS_PROVIDER=.*|SYNTHESIS_PROVIDER=bedrock|' .env
sed -i 's|^BEDROCK_REGION=.*|BEDROCK_REGION=$Region|' .env
sed -i 's|^BEDROCK_ORCHESTRATOR_MODEL=.*|BEDROCK_ORCHESTRATOR_MODEL=$BedrockModel|' .env
sed -i 's|^BEDROCK_SYNTHESIS_MODEL=.*|BEDROCK_SYNTHESIS_MODEL=$BedrockModel|' .env

# --- Safety net: strip the empty-AWS_PROFILE bug from compose even on an
#     unpatched checkout, so the EC2 instance role is used. ---
sed -i '/- AWS_PROFILE=\${AWS_PROFILE:-}/d' docker-compose.yml || true

# --- Build + start (needs the docker group; use sudo for this first run) ---
sudo docker compose up -d --build
sudo docker compose ps
echo "PROVISION_DONE"
"@
$provisionOut = Invoke-Remote -Ip $PublicIp -Script $remote
$provisionOut | ForEach-Object { Write-Host "    $_" }
if ($provisionOut -notmatch "PROVISION_DONE") { Die "Provisioning did not complete cleanly. Review the output above." }
Ok "Stack provisioned"

# ---------- 13. Health check (on the instance) ------------------------------
Info "Checking backend health on the instance..."
$health = Invoke-Remote -Ip $PublicIp -Script "curl -s http://localhost:8008/health || true"
Ok "Backend health: $health"

# ---------- 14. Summary + tunnel command ------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " MAHALO-dock deployed" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host " Account/Region : $($ident.Account) / $Region"
Write-Host " Instance       : $InstanceId"
Write-Host " Public IP      : $PublicIp"
Write-Host " Bedrock model  : $BedrockModel"
Write-Host " VPC/Subnet/SG  : $VpcId / $SubnetId / $SgId"
Write-Host " Key (pem)      : $PemPath"
Write-Host ""
Write-Host " Open the SSH tunnel (run in a SEPARATE terminal, keep it open):" -ForegroundColor Yellow
Write-Host "   ssh -i `"$PemPath`" -N -L 3000:localhost:3000 -L 3001:localhost:3001 -L 8008:localhost:8008 ubuntu@$PublicIp"
Write-Host ""
Write-Host " Then browse (on the workspace):"
Write-Host "   App     : http://localhost:3000"
Write-Host "   Gitea   : http://localhost:3001  (mahalo_admin / MahaloDock123!)"
Write-Host "   Backend : http://localhost:8008/health"
Write-Host ""
Write-Host " Stop when idle (saves cost):  pwsh ./scripts/teardown-aws.ps1 -StopOnly"
Write-Host " Full teardown:                pwsh ./scripts/teardown-aws.ps1"
Write-Host "============================================================" -ForegroundColor Green
