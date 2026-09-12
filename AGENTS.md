# AGENTS.md — synth-canary-template

Context for AI coding agents (Claude Code, Codex, opencode, Cursor, …) working in this repo.
Read this first; keep it current.

## What this is
The **single source of truth for CloudWatch Synthetics canaries** in this workspace. It is a
minimal drop-in starter whose root is just a call to a self-contained module: one
`module "canary"` block creates the canary, the `SuccessPercent` alarm, an SNS topic + email
subscription, the IAM execution role, the artifact S3 bucket, **and builds its own deployment
zip**. Since the sibling repo `cloudwatchsyntheticcanary` was retired/destroyed on 2026-08-24,
all canary code + config changes land **here**, not there.

## Layout
- `main.tf` — the module call (the only file you touch for a basic canary).
- `variables.tf` — root inputs: `canary_name`, `sns_topic_email` (required); `region`,
  `schedule_expression`, `runtime_version`, `timeout_in_seconds`, `domino_parameter_name`.
- `backend.tf` — S3 state; key must be `<project>/terraform.tfstate`.
- `provider.tf`, `versions.tf` — `aws ~> 5.0`, `archive ~> 2.0`, `random ~> 3.0`, TF >= 1.5.
- `outputs.tf` — passthroughs: canary/alarm/SNS ARNs, artifact bucket, execution role.
- `secrets.tf` — creates a placeholder SSM `SecureString` (`ignore_changes` on value) so the
  Domino key plumbing works end-to-end.
- `modules/synthetic-canary/` — the module: `main.tf` (canary + alarm + SNS), `iam.tf` (role +
  policies, scoped SSM read when a Domino key param is set), `s3.tf` (artifact bucket),
  `vpc.tf` (VPC/subnet/SG lookups), `canary_source.tf` (plan-time zip + env vars),
  `src/` (`my-canary.py` browser example, `domino_canary.py` Data Lab monitor),
  `policies/` (assume_role.json + 3 `.json.tftpl` policy templates).
- `.github/workflows/create-secret.yml` — `workflow_dispatch` that creates/updates the Domino
  SSM parameter from the `DOMINO_API_KEY` repo secret via OIDC.

## Module inputs / outputs
Key module inputs (`modules/synthetic-canary/variables.tf`): `name`, `sns_topic_email`
(required); `type` (`browser`|`domino`), `domino{}` (endpoint, project_id, workspace_id,
action, run_command, cleanup, max_latency_ms, api_key_ssm_name|api_key), `source_file`,
`artifact_bucket_name`, `environment_variables`, `vpc_config{vpc_id|vpc_name,
subnet_ids|subnet_names, security_group_ids?}`, `schedule_expression` (default `rate(5 minutes)`),
`runtime_version` (`syn-python-selenium-11.1`), `start_canary`, `delete_lambda`,
`timeout_in_seconds` (module default 600), and the `alarm_*` tuning knobs.
Module outputs: `canary_id`, `canary_arn`, `sns_topic_arn`, `alarm_arn`, `artifact_bucket`,
`execution_role_arn`, `environment_variables`.

## Commands
```bash
cp terraform.tfvars.example terraform.tfvars   # set canary_name + sns_topic_email
# edit backend.tf key -> <project>/terraform.tfstate
terraform init && terraform plan               # LOCAL PLAN ONLY
gh workflow run create-secret.yml -f parameter_name=domino-api-key   # optional key rotation
```
No test/lint tooling in-repo; validate via `terraform fmt -check` + `terraform validate`.

## Conventions (workspace AWS/Terraform rules)
- **Terraform is applied only via GitHub Actions, never locally** — OIDC role
  `github-actions-oidc-role`; **plan on PR, apply on push to `main`**. Check the Actions run
  after any push.
- PR-based: feature branch → PR → merge. Never push to `main`.
- **No inline JSON in HCL** — policies live in `policies/*.json`/`*.json.tftpl` and are loaded
  with `file()`/`templatefile()`. Follow that pattern.
- State bucket `emr-demo-state-zxcvzxcv23` (us-east-2), `encrypt = true`; key
  `<project>/terraform.tfstate`.
- Never commit secrets or `.tfvars`/state. The Domino key goes in SSM Parameter Store.
- **AWS caps `timeout_in_seconds` at 300 for a ≤5-minute schedule.** Domino workspace canaries
  polling a session need `rate(1 hour)` + timeout 600 (poll default 240s + start time), or the
  Lambda is killed mid-poll.

## Gotchas
- **This module diverges from the retired cloudwatchsyntheticcanary copy** (self-contained + it
  builds its own zip). Do not "re-sync" `modules/` from that repo — you'd lose both.
- The `.py` must land at `python/<stem>.py` inside the zip and the handler is
  `<stem>.handler`; `canary_source.tf` does this automatically. `aws_synthetics_canary` diffs the
  zip *path* only, so the source hash is baked into `output_path` — editing the `.py` forces a
  re-upload on the next apply.
- **Domino alternation fix (2026-08-24, PR #19):** workspace status can be reported for the
  *previous* session (`stopped` from last run's cleanup) before the new one registers. The
  poller splits terminal states into `HARD_FAIL` (failed/error → always fatal) and
  `SOFT_TERMINAL` (stopped/terminated/cancelled → fatal only after `seen_alive`). Cleanup runs in
  a `try/finally` so a failed wait never leaks a running session — leaked sessions were what made
  the canary alternate pass/fail.
- **Timeout fix (PR #19):** `timeout_in_seconds` was surfaced as a variable (300 for the default
  5-min browser canary, 600 for hour-scheduled Domino workspace) so the Lambda outlives the 240s
  workspace poll.
- VPC canaries still need egress to AWS services: S3 gateway endpoint + `logs`/`xray` interface
  endpoints in a private subnet without NAT (a per-project NAT avoids that).
- **No CUE pipeline here.** The multi-canary `cloudwatch_map` + CUE→`*.auto.tfvars.json`
  generation stayed in the retired cloudwatchsyntheticcanary repo. This template is single-canary
  by design; if you need several canaries, port that map-of-objects + CUE pattern rather than
  expecting it in-tree.
- Bucket name auto-generates as `synthcan-<name>-<random>`; editing the canary name recreates it.

## Open items
- `create-secret.yml` is `workflow_dispatch`-only; there is no automatic key rotation.
- The retired repo's Domino fixes are mirrored here — keep new Domino fixes coming **here** first.
