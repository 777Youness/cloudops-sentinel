# Infrastructure

Terraform for the **monitored workload** only. Sentinel itself is never deployed: it runs
on your machine (ADR 0001). Decisions: [ADR 0016](../docs/adr/0016-dev-workload-network-access-and-state.md).
Costs: [docs/cost.md](../docs/cost.md).

Status: **Day 4a. No resources yet.** `envs/dev` holds versions, provider and variables; a
plan is empty. The workload arrives in Day 4b.

```
infra/
  envs/dev/              root module, local state (gitignored)
  policies/
    sentinel-readonly.json   Sentinel's only AWS permission (tested by
                             backend/tests/test_readonly_policy.py)
```

## Prerequisites (operator, once)
Not project dependencies; install them yourself (CLAUDE.md "Tools"):
Terraform >= 1.10, AWS CLI v2, Session Manager plugin, tflint, trivy.

Account hygiene before the first apply:
1. MFA on the root user; never use the root user afterwards.
2. Sign in through IAM Identity Center (short-lived credentials, nothing stored in the repo).
3. Create a **budget alert** in the AWS console.
4. Check in the Billing console which Free Tier model applies (see docs/cost.md).

## Profiles (no secrets in the repo)
`~/.aws/config` (outside the repository) holds profile names only; SSO tokens are cached
by the AWS CLI. Placeholders below.

```ini
[profile sentinel-admin]          # you: terraform and scripts
sso_session = cloudops
sso_account_id = <ACCOUNT_ID>
sso_role_name = <PERMISSION_SET>
region = eu-west-3

[profile sentinel]                # Sentinel (Day 5): read-only role only
role_arn = arn:aws:iam::<ACCOUNT_ID>:role/cloudops-sentinel-readonly
source_profile = sentinel-admin
region = eu-west-3

[sso-session cloudops]
sso_start_url = https://<portal>.awsapps.com/start
sso_region = eu-west-3
sso_registration_scopes = sso:account:access
```

Never put access keys in `.env`, `terraform.tfvars` or any file in this repository.

## "Bootstrap" (one-time procedure; no resources, ADR 0016)
State is local, so there is no state bucket to create. Bootstrapping is:
1. the prerequisites above;
2. `cp envs/dev/terraform.tfvars.example envs/dev/terraform.tfvars` and fill it in;
3. `terraform init` in `envs/dev`, then commit the generated `.terraform.lock.hcl`
   (provider versions pinned for everyone; it contains no secrets).

## Commands (always from infra/envs/dev, with AWS_PROFILE=sentinel-admin)
```bash
terraform init && terraform fmt -check && terraform validate
terraform plan -out=tfplan        # read the plan before applying
terraform apply tfplan
terraform destroy                 # at the end of every session
../../scripts/cost-check.sh       # Day 4d: lists anything left that could bill
```

## Local state: what is ignored, and what is not protected
Ignored by git (checked with `git check-ignore`): `terraform.tfstate*` and the lock info
file, `tfplan` and any `*.tfplan`, the `.terraform/` provider cache, crash logs, real
`*.tfvars` and `*.tfvars.json` (including `*.auto.tfvars*`). Tracked: `*.tfvars.example`
and `.terraform.lock.hcl`.

Not protected: the state file is neither versioned nor backed up. It holds resource ids and
attributes, so treat it as sensitive. Keep it until `destroy` has completed; if it is lost
while resources exist, find them by tag `Project=cloudops-sentinel` and delete them, or
`terraform import` them first (ADR 0016, "State backup and recovery limitations").
