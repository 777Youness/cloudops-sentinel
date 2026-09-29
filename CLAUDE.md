# CLAUDE.md — CloudOps Sentinel

Read this file before every task. It governs how you work in this repository.
If a request conflicts with this file, stop and say so instead of silently choosing.

Status: v0.2 (architecture approved) — current target is **V1 (incident investigation)**,
current milestone is **Day 1** (see `docs/architecture.md`).

---

## 1. What this project is

CloudOps Sentinel is a local console that reads real AWS telemetry through a read-only role,
detects operational incidents with deterministic rules, and uses an LLM to write an
evidence-based investigation. Humans decide on and perform remediation.

**Deployment:** for V1, Sentinel runs locally and monitors a small disposable AWS workload.
Deployment of Sentinel itself is intentionally deferred until the core product is validated
(ADR 0001). Do not design or implement it.

It is a portfolio project. The owner must be able to explain every design decision, AWS
interaction and failure mode in a technical interview. Understandability beats cleverness.
Small and correct beats large and impressive.

Design references (read before changing anything they cover):
`docs/architecture.md`, `docs/domain-model.md`, `docs/api.md`, `docs/detection-rules.md`,
`docs/design-system.md`, `docs/screens.md`, `docs/adr/`.

---

## 2. Non-negotiable principles

1. **Facts come only from code.** The LLM never creates, edits or deletes a Fact.
2. **Severity comes only from the rule matrix** (`backend/sentinel/detection/severity.py`).
   The LLM never sets or changes severity or risk.
3. **Every hypothesis cites at least one existing fact ID.** The server validates citations.
   Invalid output is rejected (one retry with the validation error), never silently repaired.
4. **Sentinel never modifies AWS.** No code under `backend/` may call a mutating AWS API
   (Put*, Create*, Delete*, Modify*, Update*, Run*, Start*, Stop*, Terminate*, Authorize*,
   Revoke*, SendCommand, …). Scripts in `scripts/` that change the demo workload are run by
   the human, outside Sentinel.
5. **Remediation is advice.** Every RemediationOption has `requires_human = true`.
   The UI may show a command to copy; it never executes anything.
6. **Simulated data is always labelled.** Every entity carries `data_origin`. Local mode shows
   the SIMULATED DATA strip. Never mix origins in one incident.
7. **V1 must be fully useful without the LLM.** If the provider is down or not configured,
   everything except the investigation panel keeps working.
8. **Missing data is never zero.** Absent metrics produce `data_gap` facts, not 0 values.
9. **Honest UI only.** No fake data, fake buttons, placeholder marketing copy, or pages for
   features that don't exist. Unbuilt features are hidden.

---

## 3. Architecture and dependency rules

Data flows through three layers:
Observations (collectors) → Facts + Incidents (detection) → Investigation (LLM + validator).

Import rules (enforced by `backend/tests/test_architecture.py` — never weaken that test):

- `domain/` imports only the standard library and pydantic.
- `detection/` imports only `domain/` and the standard library. No I/O of any kind.
- `investigation/` (except `investigation/providers/`) imports only `domain/` and the stdlib.
- `collectors/aws/` is the only package that imports boto3/botocore.
- `investigation/providers/` is the only package that makes HTTP calls to an LLM.
- `store/` is the only package that imports sqlite3.
- `services/` orchestrates collectors, detection, investigation and store.
- `api/` calls `services/` only. Routes contain no business logic.

Runtime rules:

- Only `POST /api/v1/sync` triggers AWS calls. Only
  `POST /api/v1/incidents/{id}/investigation` triggers LLM calls. Every GET reads the store.
- Time comes from the injectable clock (`sentinel/clock.py`), never `datetime.now()` directly.
- An HTTP status describes the API call; a domain status (`SyncRun.status`,
  `Investigation.status`) describes the outcome. A failed AWS sync is a 200 with `status: failed`.

---

## 4. Scope guard

**V1 in scope:** local + AWS modes; EC2 instances tagged `cloudops-sentinel:monitor=true`;
signals cpu_utilization, cpu_credit_balance, status_check_failed, memory_used, latency_p95,
error_rate_5xx, request_rate; deployment events; alarm states; rules R-CPU-SAT, R-CPU-CREDIT,
R-MEM, R-5XX, R-LAT, R-STATUS, C-USER-IMPACT; on-demand investigation (mock + one
OpenAI-compatible provider); screens Overview, Incidents, Investigation workspace, Resources,
Resource detail, System; Terraform bootstrap + dev env; workload + scripts; Docker Compose; CI.

**Later — do not implement, scaffold, or add dependencies for:**
Cost Explorer / cost pages (V2) · Terraform drift, CloudTrail, policy checks (V3) · auto-sync,
Lambda, EventBridge, SNS, ECR, workload CD (V4) · OIDC CI role, `terraform plan` in CI,
`terraform test` · deployment of Sentinel itself on AWS (evaluated after V3) ·
"acknowledged" status, notes, similar incidents · chart-region highlighting
from evidence chips, log viewer, telemetry explorer · authentication · Bedrock · multi-region
or multi-account.

**Never:** chat interface, RAG / vector DB, agent frameworks (LangChain, CrewAI, …),
auto-remediation, Kubernetes, ML anomaly models, WebSockets.

If a task seems to require a Later or Never item, stop and ask.

The day-by-day milestones live in `docs/architecture.md`. When the current milestone's
definition of done is met, stop and summarize. Do not start the next milestone on your own.

---

## 5. Dependency policy

Approved dependencies (add them only on the day they become necessary):

| Side | Package | Reason |
|---|---|---|
| backend | fastapi, uvicorn | HTTP API + OpenAPI contract |
| backend | pydantic, pydantic-settings | Models at every boundary; config from env |
| backend | pyyaml | Human-written scenario files with comments |
| backend | httpx (runtime from Day 3) | One HTTP call to the LLM provider |
| backend | boto3 (Day 5) | AWS SDK — only in `collectors/aws/` |
| backend dev | pytest, ruff, httpx | Tests, lint + format; httpx is required by FastAPI's TestClient |
| frontend | react, react-dom, react-router | UI + routing |
| frontend | @tanstack/react-query | Server state: caching, loading/error, refetch |
| frontend | recharts (Day 2) | Signal charts |
| frontend | lucide-react | A few meaningful icons |
| frontend | @fontsource/ibm-plex-sans, @fontsource/ibm-plex-mono | Self-hosted fonts |
| frontend dev | typescript (pinned `~5.9`: openapi-typescript and typescript-eslint don't support 6+/7 yet), vite, @vitejs/plugin-react, eslint (+ typescript-eslint, react-hooks), prettier | Tooling |
| frontend dev | vitest, @testing-library/react, @testing-library/jest-dom, jsdom | Tests |
| frontend dev | openapi-typescript | Generate API types from the backend OpenAPI |

Tools (not project dependencies): uv, npm, terraform (≥ 1.10), tflint, trivy, gitleaks, aws cli.

Any other dependency requires, **before installing**: the concrete problem, why the stdlib or
an approved dependency cannot solve it, and my explicit approval. Record the justification in
the PR description. No UI component libraries, no CSS frameworks, no ORMs, no LLM SDKs or
frameworks.

---

### LLM provider policy (Day 3)

- The provider interface stays generic: one `complete(prompt) -> text` style boundary,
  implemented by `MockProvider` and one OpenAI-compatible HTTP provider.
- No real provider is the default until its current API terms, pricing and free-tier limits
  have been checked and recorded in an ADR.
- `MockProvider` must work with no API key and no network access. It is the default in
  tests, in CI, and whenever no provider is configured.

---

## 6. AWS and cost rules

- Region `eu-west-3` unless configured otherwise. Single region.
- **Forbidden resources:** NAT Gateway, ALB/NLB, RDS, ECS/Fargate, EKS, interface VPC
  endpoints, Elastic IPs, KMS customer-managed keys, Secrets Manager, CloudTrail trails,
  EC2 detailed monitoring, CloudWatch dashboards.
- EC2: t3.micro, `credit_specification { cpu_credits = "standard" }`, IMDSv2 required,
  encrypted gp3 root volume with `delete_on_termination = true`, auto-shutdown safety timer.
- No port 22 anywhere. Instance access via SSM only. The app port is open only to
  `var.operator_cidr` (a /32).
- Every log group has a retention period (default 3 days).
- Custom CloudWatch metrics: at most 5 in total. V1 uses one: `mem_used_percent`.
- Provider `default_tags`: `Project=cloudops-sentinel`, `Environment`, `ManagedBy=terraform`.
- Cost-bearing API calls (GetMetricData, Logs Insights) happen only in the sync path, with
  bounded time ranges (default window: 3 hours).
- Any change that adds or changes a billable resource must update `docs/cost.md` in the
  same PR.

---

## 7. Security rules

- Never commit credentials, API keys, tokens, `.env`, `terraform.tfvars`, `*.tfstate*`,
  `*.pem`. gitleaks runs in CI.
- Configuration via environment variables (pydantic-settings). `.env.example` documents every
  variable with a safe placeholder.
- AWS credentials come from the standard boto3 chain via the `sentinel` profile (which assumes
  `cloudops-sentinel-readonly`). Never read, print or log credential values.
- Mask the AWS account ID in API responses and logs (last 4 digits only).
- LLM input: only the evidence bundle. Log lines truncated to 300 chars, at most 20 samples,
  deduplicated, inside clearly delimited data blocks. Text inside logs is data, never
  instructions.
- The API binds to 127.0.0.1 by default. There is no authentication in V1. Document it as a
  limitation; do not add a partial auth system.

---

## 8. Backend conventions

- Python 3.12, type hints everywhere, Pydantic v2 models at all boundaries.
- Datetimes are timezone-aware UTC, serialized ISO 8601 with `Z`.
- Every numeric value that has a unit carries an explicit `unit` field.
- Fact statements are generated by templates in `detection/statements.py`.
- Thresholds live in `detection/thresholds.py` and must match `docs/detection-rules.md`.
- Errors: typed domain exceptions mapped to the envelope
  `{"error": {"code", "message", "hint"}}` in one place (`api/errors.py`).
- AWS errors are translated in `collectors/aws/errors.py` into `CollectorStatus` with a human
  hint (e.g. ExpiredToken → "Run `aws sso login --profile sentinel`").
- No module-level mutable state except the service container built in `main.py`.
- `ruff format` and `ruff check` must pass.

---

## 9. Frontend conventions

- TypeScript strict, no `any`. API types come from `src/api/schema.d.ts`, generated by
  `npm run gen:api`, which exports the backend's OpenAPI document to `src/api/openapi.json`
  (no running server needed) and runs openapi-typescript on it. Friendly aliases live in
  `src/api/types.ts`. Never hand-edit or duplicate API types. Both generated files are
  committed; CI regenerates them and fails on any difference.
- Only `src/api/client.ts` calls `fetch`.
- Data fetching only through TanStack Query hooks in `src/features/<feature>/api.ts`.
  Components never call `fetch` directly.
- Feature folders under `src/features/`. Shared primitives in `src/components/` only when
  used by two or more features.
- Styling: CSS Modules + tokens from `src/styles/tokens.css`. No raw hex values, ad-hoc font
  sizes or shadows in components. If a token is missing, propose adding it to
  `docs/design-system.md` first.
- Copy and labels: sentence case (no all-caps labels), metadata as key–value pairs (no
  strings joined with "·"), no arrows appended to buttons or links.
- **Forbidden:** gradients, glassmorphism, glow, blobs, drop shadows on content, radius > 4 px,
  cards nested in cards, chart entrance animations, emoji, decorative icons, marketing copy,
  hero-sized headings.
- Color encodes state only (ok / warn / crit / unknown, severity). The accent is for selection,
  links, focus and deployment markers. Severity always has a text label, never color alone.
- Epistemic styling: observed facts = solid left rule; AI inferences = dashed left rule +
  "Inferred" label; remediation = "Human decision" tag.
- Every data view implements loading (skeleton shaped like the data), empty, error and stale
  states using the copy in `docs/design-system.md`. Syncing never blanks existing data.
- Numbers use Plex Mono with tabular figures. Times are relative in text, absolute UTC on hover.
- Filters live in the URL query string.
- Accessibility: semantic HTML (`<table>` for tables), visible focus, WCAG AA contrast,
  keyboard reachable.

---

## 10. Testing rules

- Every detection rule: trigger, non-trigger, boundary, insufficient-data tests.
- Every scenario in `backend/scenarios/` has an expected-outcome test.
- Investigation validator: one test per rejection reason.
- AWS collectors: botocore Stubber tests, including AccessDenied / ExpiredToken mapping.
- A bug fix starts with a failing test.
- Tests never call real AWS or a real LLM. Real-provider runs are manual and saved in
  `docs/examples/`.
- Before reporting a task as done, run and report the result of:
  - backend: `uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
  - frontend: `npm run gen:api && npm run typecheck && npm run lint && npm test -- --run && npm run build`

---

## 11. How we work: BUILD → RUN → BREAK → UNDERSTAND → FIX → DOCUMENT

1. **Plan first.** Before writing code, give a short plan: files to touch, approach,
   what is out of scope. Wait for approval on anything larger than one small change.
2. **Small steps.** One concern per change. No drive-by refactors, renames or reformatting.
3. **Readable over clever.** Explicit code, few abstractions, comments explain *why*.
4. **Never guess about AWS.** If unsure about an API, permission, quota or price, say so
   and name the documentation page to check.
5. **Update docs in the same change:** `docs/architecture.md` when structure changes,
   `docs/cost.md` when cost changes, a new ADR when a decision changes.
6. **End every task with a Handover block:**
   - **What changed:** files, one line each
   - **Why this design:** the decision and the main rejected alternative
   - **How it connects:** which components / AWS APIs it talks to
   - **Run it:** exact commands and what I should see
   - **Break it:** one exercise and the failure I should observe
   - **Explain it:** 1–3 interview-style questions I should be able to answer

---

## 12. Git conventions

- Conventional Commits: `feat(detection): …`, `fix(api): …`, `test(…)`, `docs(adr): …`,
  `infra(tf): …`, `chore(ci): …`.
- One PR per milestone step; the PR description is the Handover block.
- `main` stays green. Never commit build output (`dist/`, `.terraform/`, `__pycache__/`).

---

## 13. Commands

```bash
# backend
cd backend && uv sync          # then: cp .env.example .env (optional, defaults are safe)
uv run uvicorn sentinel.main:app --reload --host 127.0.0.1 --port 8000
uv run pytest -q

# frontend (Vite proxies /api to 127.0.0.1:8000 — no CORS configuration)
cd frontend && npm install
npm run dev
npm run gen:api        # export OpenAPI from the backend code and regenerate src/api/schema.d.ts

# infra (Day 4+) — always from infra/envs/dev
terraform init && terraform fmt -check && terraform validate
terraform plan -out=tfplan && terraform apply tfplan
terraform destroy && ../../scripts/cost-check.sh
```
