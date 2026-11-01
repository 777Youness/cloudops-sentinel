# Infrastructure

Terraform for the **monitored workload** only. Sentinel itself is never deployed: it runs
on your machine (ADR 0001). Decisions: [ADR 0016](../docs/adr/0016-dev-workload-network-access-and-state.md),
[ADR 0017](../docs/adr/0017-workload-deployment-operator-access-and-safety-timer.md).
Costs: [docs/cost.md](../docs/cost.md).

Status: **Day 4b, written and checked locally, never applied.** No AWS resource exists.
`terraform fmt`, `terraform validate` and the guardrail tests pass; nothing below has run
against AWS yet. **The safety timer is UNTESTED** until the termination test passes.

```
infra/
  envs/dev/                    root module, local state (gitignored)
    main.tf                    locals and file map
    network.tf                 VPC, IGW, public subnet, route table, default SG locked down
    security.tf                workload SG: app port from operator_cidr only, HTTPS out
    iam.tf                     instance role: SSM core + scoped CloudWatch (no CreateLogGroup)
    compute.tf                 t3.micro AL2023, IMDSv2, encrypted gp3, shutdown = terminate
    observability.tf           log group (3 days) and one CPU alarm without actions
    templates/                 user_data (safety timer first) and CloudWatch agent config
  policies/
    sentinel-readonly.json     Sentinel's only AWS permission (Day 5; tested)
    operator-terraform.json    YOUR permissions for Terraform (attached by hand; tested)
workload/app.py                the stdlib HTTP app the instance runs (tested locally)
scripts/cost-check.sh          read-only leftover check (tested to be read-only)
scripts/render_policy.py       fills ${region}/${account_id} into a policy template
```

## 1. Prerequisites (operator, once)
Tools (not project dependencies, CLAUDE.md "Tools"): Terraform >= 1.10 (1.16.5 used),
AWS CLI v2 >= 2.32.0 (2.38.6 used), the Session Manager plugin.

**Never enable AWS Organizations or IAM Identity Center in this account**: AWS warned that
creating an organization would immediately expire the account's credits (ADR 0017).

In the AWS console:
1. Root user: MFA on, no access keys. Use root only for account and billing settings.
2. Budget: open your budget, Edit, and **exclude credits** in its charge types (the
   Budgets API documents `IncludeCredit` with default `true`: with credits included, usage
   paid by credits nets to about $0 and the alert may never fire). Suggested alerts:
   actual $1, $5, $8 and forecasted $10. A budget is not real time: it is a backstop.
3. Check which Free Tier model applies (Billing console) and note it in `docs/cost.md`.
4. Create the operator IAM user (for example `sentinel-operator`): console access with a
   password, MFA, **no access keys**. Attach:
   - the AWS managed policy `SignInLocalDevelopmentAccess` (needed by `aws login`);
   - the project policy, rendered on your machine (the output contains your account id:
     write it outside the repository and never commit it):
     ```bash
     python scripts/render_policy.py infra/policies/operator-terraform.json --account-id <12 digits> > "$TEMP/operator-terraform.json"
     ```
     then IAM, Policies, Create policy, JSON, paste, name it `cloudops-sentinel-operator`,
     and attach it to the user.

## 2. Profiles (no secrets in the repository)
`~/.aws/config` (outside the repository). The first profile is created by `aws login`; the
second is the bridge Terraform uses (the provider does not read `login_session` natively,
ADR 0017).

```ini
[profile sentinel-login]
login_session = arn:aws:iam::<ACCOUNT_ID>:user/sentinel-operator
region = eu-west-3

[profile sentinel-admin]
credential_process = aws configure export-credentials --profile sentinel-login --format process
region = eu-west-3
```

```bash
aws login --profile sentinel-login
```

```bash
aws sts get-caller-identity --profile sentinel-admin --query Arn --output text
```

Never run `aws configure export-credentials` yourself (it prints credentials), never put
access keys in `.env`, `terraform.tfvars` or any file in this repository.

## 3. Configure, plan, apply (always from infra/envs/dev)
```bash
cp terraform.tfvars.example terraform.tfvars    # then set operator_cidr to your IP /32
```

```bash
export AWS_PROFILE=sentinel-admin              # PowerShell: $env:AWS_PROFILE = "sentinel-admin"
```

```bash
terraform init -lockfile=readonly -input=false && terraform fmt -check && terraform validate
```

```bash
terraform plan -out=tfplan                      # read it: 17 resources to add, nothing to change or destroy
```

```bash
terraform apply tfplan
```

If plan or apply fails with **AccessDenied**, the operator policy is missing one action:
add exactly that action to `infra/policies/operator-terraform.json` in a reviewed commit
(the tests must still pass), re-render, update the IAM policy. Never widen it to a wildcard.

## 4. Verification on AWS (UNTESTED until done)
Run these in order. Each run ends with `terraform destroy` and the leftover check.

**A. Termination test (first, 15 minutes).** Proves the safety net before anything runs
for hours. Bootstrap may not finish before the timer fires: that is expected.
1. `terraform apply -var safety_timer_minutes=15` (after a plan you have read).
2. Do not touch the instance. After about 15–20 minutes:
   `aws ec2 describe-instances --instance-ids <id> --query "Reservations[].Instances[].State.Name"`
   must show `shutting-down` or `terminated`.
3. `bash ../../scripts/cost-check.sh` must show no instance, no volume, no network interface
   with a public IP. The VPC, security groups, IAM role, log group and alarm are expected to
   remain (they belong to Terraform, not to the instance).
4. `terraform plan` should now propose to create the instance again (it is gone).
5. `terraform destroy`, then `bash ../../scripts/cost-check.sh` again: exit code 0.
6. Record the result (date, timings, what remained) in ADR 0017 and `docs/cost.md`. Only
   then may the timer be described as tested.

**B. Functional run (240 minutes).**
1. `terraform apply` (default timer).
2. Shell: the `ssm_session_command` output (Session Manager plugin required). On the
   instance: `systemctl list-timers cloudops-safety-shutdown.timer`,
   `systemctl status cloudops-workload amazon-cloudwatch-agent`, `dnf repolist`,
   `tail /var/log/cloud-init-output.log`.
3. From your machine: open the `app_url` output; from any other address it must time out.
4. `aws logs tail /cloudops-sentinel/dev/access --since 10m` shows the JSON lines.
5. `aws cloudwatch list-metrics --namespace CWAgent` shows exactly one metric,
   `mem_used_percent`, with only the `InstanceId` dimension.
6. `terraform destroy`, then the leftover check.

## 5. End of every session
```bash
terraform destroy
```

```bash
bash ../../scripts/cost-check.sh
```

Exit code 0: nothing billable found. 1: something is left (listed). 2: a check failed (for
example AccessDenied): the result is incomplete and must not be read as clean. The check
covers the whole region (untagged volumes and network interfaces too) and IAM roles
(global). Custom metrics are listed for information only: they cost nothing without data and
cannot be deleted.

## 6. Local state: what is ignored, and what is not protected
Ignored by git (checked with `git check-ignore`): `terraform.tfstate*` and the lock info
file, `tfplan` and any `*.tfplan`, the `.terraform/` provider cache, crash logs, real
`*.tfvars` and `*.tfvars.json` (including `*.auto.tfvars*`). Tracked: `*.tfvars.example`
and `.terraform.lock.hcl`.

Not protected: the state file is neither versioned nor backed up. It holds resource ids and
attributes (including the rendered user_data), so treat it as sensitive. Keep it until
`destroy` has completed; if it is lost while resources exist, find them with
`scripts/cost-check.sh` and delete them in the console, or `terraform import` them first
(ADR 0016, "State backup and recovery limitations").
