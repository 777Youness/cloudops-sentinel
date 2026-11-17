# Infrastructure

Terraform for the **monitored workload** only. Sentinel itself is never deployed: it runs
on your machine (ADR 0001). Decisions: [ADR 0016](../docs/adr/0016-dev-workload-network-access-and-state.md),
[ADR 0017](../docs/adr/0017-workload-deployment-operator-access-and-safety-timer.md).
Costs: [docs/cost.md](../docs/cost.md).

Status (reported by the owner, 2026-11-17): the full configuration, **19 resources**
including Sentinel's read-only role, was applied in eu-west-3; the app answered HTTP 200;
Sentinel assumed the role and all three collectors succeeded (7/7 signals, 1 resource, 7
rules, no incident because the workload was healthy); `terraform destroy` removed the 19
resources and the state is empty. The 5xx demo (section 8, ADR 0019) was then run once: a
real high-severity R-5XX incident (peak 21.1%), followed by `terraform destroy` (19
resources) and a clean `cost-check.sh`. Nothing is running now. Resolution on AWS (step 7)
was not observed. **The safety timer is still UNTESTED**: no run has shown the instance
terminating itself.

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
    operator-assume-sentinel.json  lets YOUR user assume Sentinel's read-only role (by hand)
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
   - for Sentinel (Day 5), the small policy that lets the same user assume the read-only
     role, rendered the same way and attached as `cloudops-sentinel-assume-reader`:
     ```bash
     python scripts/render_policy.py infra/policies/operator-assume-sentinel.json --account-id <12 digits> > "$TEMP/operator-assume-sentinel.json"
     ```

## 2. Profiles (no secrets in the repository)
`~/.aws/config` (outside the repository). Three profiles, three purposes:

| Profile | Used by | Permissions |
|---|---|---|
| `sentinel-login` | `aws login` (your console sign-in) | your IAM user |
| `sentinel-terraform` | Terraform, `cost-check.sh`, Session Manager | your IAM user, through a `credential_process` bridge (the provider does not read `login_session` natively, ADR 0017) |
| `sentinel` | the Sentinel backend in aws mode | **only** the read-only role `cloudops-sentinel-dev-readonly` (ADR 0018) |

```ini
[profile sentinel-login]
login_session = arn:aws:iam::<ACCOUNT_ID>:user/<OPERATOR_USER>
region = eu-west-3

[profile sentinel-terraform]
credential_process = aws configure export-credentials --profile sentinel-login --format process
region = eu-west-3

[profile sentinel]
role_arn = arn:aws:iam::<ACCOUNT_ID>:role/cloudops-sentinel-dev-readonly
source_profile = sentinel-terraform
region = eu-west-3
```

The `sentinel` profile starts from your sign-in but every call it makes runs as the role:
it can read telemetry and nothing else (`infra/policies/sentinel-readonly.json`, explicit
Deny on every write). It works only after the role exists (`terraform apply`) and the
assume policy is attached to your user.

```bash
aws login --profile sentinel-login
```

```bash
aws sts get-caller-identity --profile sentinel-terraform --query Arn --output text
```

After the role exists, the backend's identity must be the role, not your user:

```bash
aws sts get-caller-identity --profile sentinel --query Arn --output text
```

Expect `arn:aws:sts::<account>:assumed-role/cloudops-sentinel-dev-readonly/...`.

Never run `aws configure export-credentials` yourself (it prints credentials), never put
access keys in `.env`, `terraform.tfvars` or any file in this repository.

## 3. Configure, plan, apply (always from infra/envs/dev)
```bash
cp terraform.tfvars.example terraform.tfvars    # then set operator_cidr and sentinel_reader_arn
```

```bash
export AWS_PROFILE=sentinel-terraform          # PowerShell: $env:AWS_PROFILE = "sentinel-terraform"
```

```bash
terraform init -lockfile=readonly -input=false && terraform fmt -check && terraform validate
```

```bash
terraform plan -out=tfplan                      # read it: 19 resources to add (17 + Sentinel's role and its policy)
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

## 7. Sentinel in aws mode (Day 5, ADR 0018; validated once by the owner)
1. Workload applied (section 3) and the assume policy attached (section 1).
2. `aws login --profile sentinel-login`, then check the `sentinel` profile (section 2).
3. From `backend/`:
   ```bash
   SENTINEL_MODE=aws SENTINEL_AWS_PROFILE=sentinel uv run uvicorn sentinel.main:app --host 127.0.0.1 --port 8000
   ```
4. Generate a little traffic (open `app_url` a few times), wait 2–3 minutes for the agent
   and CloudWatch, then click **Sync now** in the console. Expect sync `success` and three
   `ok` collectors on the System page (ec2, cloudwatch_metrics, cloudwatch_logs). A
   `partial` sync names the failed collector and its error code; see ADR 0018,
   "Verification", for the expected first-run surprises.
5. `terraform destroy` and `cost-check.sh` at the end, as always.

## 8. Demonstrate a real 5xx incident (Day 5b, ADR 0019; run once on AWS, step 7 not observed)
Shows the whole chain: EC2 app → access log → CloudWatch Logs → Logs Insights → R-5XX →
SQLite incident → console → investigation. Same thresholds as always; about 25 minutes;
a few kB of logs on top of the usual instance hours (`docs/cost.md`).

**Commands are PowerShell** (Windows). Three terminals: A for Terraform, B for the
backend, C for the console; the traffic runs in A after the apply.

1. **Deploy** (terminal A, from `infra/envs/dev`; `fault_injection_enabled` defaults to
   `true` in dev):
   ```powershell
   aws login --profile sentinel-login
   $env:AWS_PROFILE = "sentinel-terraform"
   terraform plan -out=tfplan
   terraform apply tfplan
   terraform output -raw app_url
   ```
   Wait about 3 minutes for the bootstrap, then check the app from your machine:
   `curl.exe <app_url>health` must print `ok`, and `curl.exe <app_url>fault/500` must
   answer `injected fault (demo)` (HTTP 500).
2. **Start Sentinel in aws mode** (terminal B, from `backend/`). Optional clean slate: stop
   the backend and delete `backend\data\sentinel-aws.db` first, so old demo incidents do
   not stay listed.
   ```powershell
   $env:SENTINEL_MODE = "aws"
   $env:SENTINEL_AWS_PROFILE = "sentinel"
   uv run uvicorn sentinel.main:app --host 127.0.0.1 --port 8000
   ```
   Terminal C, from `frontend/`: `npm run dev`, open http://127.0.0.1:5173.
3. **Healthy baseline**: click **Sync now**. Expect `success`, three `ok` collectors, no
   incident.
4. **Error traffic** (terminal A, from the repository root):
   ```powershell
   python scripts/demo_traffic.py --url (terraform -chdir=infra/envs/dev output -raw app_url) --mode errors --minutes 14
   ```
   It prints one line per minute (about 48 `ok` and 12 `fault_500` each) and
   `<- sync now` at minute 9.
5. **Detect**: at minute 9 or later, while the traffic still runs, click **Sync now**.
   Expected: one incident, **R-5XX, severity high**, `data_origin` aws, a fact like
   "5xx error rate at or above 5% for 6 min since 10:00 UTC (peak 20.0%)" (your
   times and duration), latency checked and normal,
   possibly data gaps (memory, if the agent's metric is late). Open it: the error-rate
   chart shows the breach window.
6. **Investigate**: in the workspace, click **Run investigation** (the mock provider by
   default; Ollama if configured, ADR 0015). Every hypothesis cites the R-5XX fact.
7. **Recover**: when the error traffic ends, run
   `python scripts/demo_traffic.py --url (terraform -chdir=infra/envs/dev output -raw app_url) --mode healthy --minutes 15`
   and sync again after minute 13: the incident resolves (10 clean minutes are required).
8. **Clean up** (terminal A, from `infra/envs/dev`): `terraform destroy`, then
   `bash ../../scripts/cost-check.sh` (exit code 0). Stop the backend and the console.

**If something does not happen**

| Symptom | Likely cause | Check |
|---|---|---|
| `curl` times out | your public IP changed, so `operator_cidr` no longer matches | update `terraform.tfvars`, apply again |
| `/fault/500` answers 404 | fault injection disabled | `terraform output` / `fault_injection_enabled`; changing it replaces the instance |
| Sync shows no incident at minute 9 | logs not yet ingested, or a pause broke the run | wait 2 minutes and sync again; the traffic must be continuous |
| `cloudwatch_logs` failed | Logs Insights permission or timeout | the error code and hint on the System page (ADR 0018) |
| No error rate at all | the agent is not shipping the log | Session Manager: `systemctl status amazon-cloudwatch-agent`, `tail /var/log/cloudops-workload/access.log` |
| Severity medium, not high | fewer than 5 minutes at >= 5 % (for example `--error-every 30`) | keep the default `--error-every 5` |
