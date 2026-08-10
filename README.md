# synth-canary-template

Minimal drop-in starter that reuses the `modules/synthetic-canary` module from
`cloudwatchsyntheticcanary`, refactored to be **fully self-contained**: the module
creates everything — canary, SuccessPercent alarm, SNS topic + email subscription,
IAM execution role, and artifact S3 bucket — and even builds its own deployment zip.

The root is just a module call. That's the whole point:

```hcl
module "canary" {
  source = "./modules/synthetic-canary"

  name            = "my-canary"
  sns_topic_email = "alerts@example.com"
}
```

## Root layout

- `main.tf` — the module call (the only file you touch for a basic canary)
- `variables.tf` — `canary_name`, `sns_topic_email` (required); `region`, `schedule_expression`, `runtime_version` (optional)
- `backend.tf` — change the key to `<project>/terraform.tfstate`
- `outputs.tf` — passthroughs (canary/alarm/SNS ARNs, bucket, role)

## Module internals (`modules/synthetic-canary/`)

- `main.tf` — canary + alarm + SNS resources (as upstream)
- `iam.tf` — execution role + policies (names derived from `var.name`; scoped Secrets Manager read policy added when `domino.api_key_secret_arn` is set)
- `s3.tf` — artifact bucket (auto-generated unique name, or pin with `artifact_bucket_name`)
- `canary_source.tf` — builds the zip at plan time from `src/` (browser: `my-canary.py`, domino: `domino_canary.py`), derives handler + DOMINO_* env vars
- `src/` — `my-canary.py` (example browser canary) + `domino_canary.py` (Domino Data Lab monitor)
- `policies/` — IAM JSON (assume_role + 3 policy templates incl. secrets)

## Domino workspace / job monitoring

The module ships the same Domino Data Lab monitoring used in cloudwatchsyntheticcanary:
start a Job or Workspace via the Domino v4 API, verify it was accepted, and (by default)
stop what it started so no paid compute is left running each cycle.

```hcl
module "canary" {
  source = "./modules/synthetic-canary"

  name            = "domino-workspace-monitor"
  sns_topic_email = "alerts@example.com"

  type = "domino"
  domino = {
    endpoint   = "https://domino.example.com"
    project_id = "1234"
    action     = "workspace"          # or "job"
    # run_command = "main.py"          # job only
    # cleanup = true                    # default: stops what it starts
    api_key_secret_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:domino-api-key-abc123"  # preferred
    # api_key_secret_json_key = "apiKey"  # if the secret is JSON, set the key
    # api_key = "..."                  # plaintext fallback — avoid for real secrets
  }
}
```

Domino env vars are built automatically (`DOMINO_HOST`, `DOMINO_PROJECT_ID`, `DOMINO_ACTION`, …)
and the IAM role gets scoped `secretsmanager:GetSecretValue` only when `api_key_secret_arn` is set.
See `src/domino_canary.py` for the `DOMINO_*_PATH` overrides if your Domino version's API paths differ.

## Optional module vars

| var | default | purpose |
|---|---|---|
| `type` | `"browser"` | `"browser"` or `"domino"` (picks the built-in source script) |
| `domino` | `null` | object — required when `type = "domino"` (see Domino section) |
| `source_file` | built-in per `type` | path to your canary `.py`; handler is derived from the filename |
| `artifact_bucket_name` | auto-generated | pin a fixed bucket name |
| `environment_variables` | `{}` | runtime env vars (e.g. API endpoint) |
| `schedule_expression` | `rate(5 minutes)` | run cadence |
| `runtime_version` | `syn-python-selenium-11.1` | Synthetics runtime |
| `start_canary` / `delete_lambda` | `true` / `true` | lifecycle switches |
| `alarm_*` | threshold 100, 2×300s | alarm tuning |

## Setup

```bash
cp terraform.tfvars.example terraform.tfvars   # fill in name + email
# edit backend.tf: key must be <project>/terraform.tfstate
terraform init && terraform plan
```

## Notes / gotchas

- The `.py` must end up at `python/<stem>.py` inside the zip (Synthetics runtime requirement)
  and the handler must be `<stem>.handler` — both handled automatically by the module.
- Zip hash is baked into the output path, so editing the `.py` re-uploads on next apply.
- The bucket name auto-generates from `synthcan-<name>-<random>` — no collisions across projects.
- Single-canary by design. For multiple canaries (browser + API + domino), copy the
  `cloudwatch_map` map-of-objects pattern + CUE pipeline from cloudwatchsyntheticcanary.
- ⚠️ This module now **diverges from upstream** (self-contained + auto zip). If you re-copy
  `modules/` from cloudwatchsyntheticcanary, you'll lose that — treat it as a fork.
- Deploys via the workspace standard: GitHub Actions OIDC (`github-actions-oidc-role`),
  plan on PR, apply on push to main.
