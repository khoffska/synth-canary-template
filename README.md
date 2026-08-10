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
- `iam.tf` — execution role + policies (names derived from `var.name`)
- `s3.tf` — artifact bucket (auto-generated unique name, or pin with `artifact_bucket_name`)
- `canary_source.tf` — builds the zip at plan time from `src/my-canary.py` (ships an example)
- `src/my-canary.py` — example browser canary; edit it or point `source_file` elsewhere
- `policies/` — IAM JSON (assume_role + 2 policy templates; the domino secrets policy was dropped — upstream-only)

## Optional module vars

| var | default | purpose |
|---|---|---|
| `source_file` | `${path.module}/src/my-canary.py` | path to your canary `.py`; handler is derived from the filename |
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
