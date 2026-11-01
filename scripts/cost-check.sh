#!/usr/bin/env bash
# CloudOps Sentinel leftover check: lists anything in the account that could still bill.
#
#   AWS_PROFILE=sentinel-admin bash scripts/cost-check.sh          (from the repository root)
#   AWS_PROFILE=sentinel-admin bash ../../scripts/cost-check.sh    (from infra/envs/dev)
#
# READ-ONLY. Every AWS call below is a describe-, list- or get- operation; the test
# backend/tests/test_infra_guardrails.py fails if any other operation appears. It changes
# nothing and deletes nothing: you decide what to remove (normally `terraform destroy`).
#
# It checks the whole region, not only resources tagged Project=cloudops-sentinel: a root
# volume or a network interface may carry no tags, and an untagged leftover still bills.
#
# Exit codes: 0 nothing billable found, 1 something found (read the report), 2 a check
# failed (for example AccessDenied): the result is incomplete, never read as clean.
# The account id is printed masked (last 4 digits), as CLAUDE.md requires.

set -uo pipefail

REGION="${AWS_REGION:-eu-west-3}"
PROJECT_TAG="cloudops-sentinel"
FOUND=0
ERRORS=0

aws_ro() {
  # All AWS calls go through here, always in one region, as text, without a pager.
  AWS_PAGER="" aws --region "$REGION" --output text "$@"
}

check() {
  # check <label> <aws arguments...>: runs one read-only call and reports what it found.
  # A failed call is an ERROR, never "none": a denied check proves nothing.
  local label="$1"
  shift
  local output
  if ! output=$(aws_ro "$@" 2>&1); then
    # Error messages can contain ARNs; mask any 12-digit account id.
    echo "ERROR  $label: $(echo "$output" | head -n 1 | sed -E 's/[0-9]{12}/************/g')"
    ERRORS=1
    return
  fi
  if [[ -n "${output//[[:space:]]/}" && "$output" != "None" ]]; then
    if [[ "${INFO_ONLY:-0}" == 1 ]]; then
      echo "info   $label"
    else
      echo "FOUND  $label"
      FOUND=1
    fi
    echo "$output" | sed 's/^/       /'
  else
    echo "none   $label"
  fi
}

if ! account=$(aws_ro sts get-caller-identity --query Account 2>/dev/null); then
  echo "ERROR: cannot call AWS. Sign in first: aws login --profile sentinel-login" >&2
  exit 2
fi
echo "Account ****${account: -4}, region $REGION, $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

# EC2: anything not terminated (a stopped instance still pays for its volume).
check "EC2 instances (not terminated)" ec2 describe-instances \
  --filters Name=instance-state-name,Values=pending,running,shutting-down,stopping,stopped \
  --query 'Reservations[].Instances[].[InstanceId,State.Name,InstanceType,Tags[?Key==`Project`]|[0].Value]'

check "EBS volumes (any)" ec2 describe-volumes \
  --query 'Volumes[].[VolumeId,State,Size,VolumeType,Tags[?Key==`Project`]|[0].Value]'

check "EBS snapshots owned by this account" ec2 describe-snapshots --owner-ids self \
  --query 'Snapshots[].[SnapshotId,VolumeSize,StartTime]'

check "Elastic IPs (forbidden in this project)" ec2 describe-addresses \
  --query 'Addresses[].[PublicIp,AllocationId,AssociationId]'

check "Network interfaces with a public IPv4 address" ec2 describe-network-interfaces \
  --query 'NetworkInterfaces[?Association.PublicIp!=`null`].[NetworkInterfaceId,Association.PublicIp,Status]'

check "Network interfaces not attached (status available)" ec2 describe-network-interfaces \
  --filters Name=status,Values=available --query 'NetworkInterfaces[].[NetworkInterfaceId,VpcId]'

check "NAT gateways (forbidden)" ec2 describe-nat-gateways \
  --filter Name=state,Values=pending,available \
  --query 'NatGateways[].[NatGatewayId,State]'

check "VPC endpoints (forbidden)" ec2 describe-vpc-endpoints \
  --query 'VpcEndpoints[].[VpcEndpointId,VpcEndpointType,State]'

check "VPCs tagged Project=$PROJECT_TAG" ec2 describe-vpcs \
  --filters "Name=tag:Project,Values=$PROJECT_TAG" --query 'Vpcs[].[VpcId,CidrBlock]'

# CloudWatch
check "Log groups /cloudops-sentinel/*" logs describe-log-groups \
  --log-group-name-prefix /cloudops-sentinel/ \
  --query 'logGroups[].[logGroupName,retentionInDays,storedBytes]'

check "Log groups WITHOUT retention (never expire)" logs describe-log-groups \
  --query 'logGroups[?retentionInDays==`null`].[logGroupName,storedBytes]'

check "Alarms cloudops-sentinel-*" cloudwatch describe-alarms \
  --alarm-name-prefix cloudops-sentinel- --query 'MetricAlarms[].[AlarmName,StateValue]'

# Custom metrics are billed only in hours when data is sent; listed for the dimension check
# (exactly one metric, InstanceId only). Metrics without data for two weeks are not listed.
# Information only: listed metrics do not make the exit code non-zero.
INFO_ONLY=1 check "Custom metrics in namespace CWAgent (info)" cloudwatch list-metrics \
  --namespace CWAgent --query 'Metrics[].[MetricName,join(`,`,Dimensions[].Name)]'

# IAM (global): roles and instance profiles created by this project.
check "IAM roles cloudops-sentinel-*" iam list-roles \
  --query 'Roles[?starts_with(RoleName, `cloudops-sentinel-`)].RoleName'

check "IAM instance profiles cloudops-sentinel-*" iam list-instance-profiles \
  --query 'InstanceProfiles[?starts_with(InstanceProfileName, `cloudops-sentinel-`)].InstanceProfileName'

# Anything else that still carries the project tag (catch-all).
check "Other resources tagged Project=$PROJECT_TAG" resourcegroupstaggingapi get-resources \
  --tag-filters "Key=Project,Values=$PROJECT_TAG" --query 'ResourceTagMappingList[].ResourceARN'

echo
if [[ $ERRORS -ne 0 ]]; then
  echo "Some checks failed (ERROR above): the result is incomplete. Fix access and run again."
  exit 2
fi
if [[ $FOUND -eq 0 ]]; then
  echo "Nothing found that could bill in $REGION."
else
  echo "Something is left (see FOUND above). Run terraform destroy, or remove it in the console."
  echo "Note: the tagging API can list a deleted resource for a while after deletion."
fi
exit "$FOUND"
