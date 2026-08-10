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
    api_key_ssm_name = "domino-api-key" # SSM SecureString parameter (preferred)
    # api_key = "***"                  # plaintext fallback — avoid for real secrets
  }
}
```

Domino env vars are built automatically (`DOMINO_HOST`, `DOMINO_PROJECT_ID`, `DOMINO_ACTION`, …)
and the IAM role gets scoped `ssm:GetParameter` only when `api_key_ssm_name` is set.
See `src/domino_canary.py` for the `DOMINO_*_PATH` overrides if your Domino version's API paths differ.

## Creating the Domino API key parameter

Three options:

**A. Terraform (this template, starter)** — `secrets.tf` creates an SSM
Parameter Store `SecureString` with a dummy value (`"foo bar"`) so the whole
chain works end to end. `ignore_changes` on the value means Terraform won't
revert out-of-band updates:

```hcl
# main.tf — wire the parameter name straight from the resource
api_key_ssm_name = aws_ssm_parameter.domino_api_key.name
```

Then put the real key in place (console → Systems Manager → Parameter Store, or
the create-secret workflow below) — Terraform will leave it alone on the next apply.

**B. One-off workflow** — `create-secret.yml` (workflow_dispatch) creates or
updates the parameter from the `DOMINO_API_KEY` repo secret:

```bash
gh secret set DOMINO_API_KEY
gh workflow run create-secret.yml -f parameter_name=domino-api-key
```

**C. AWS CLI** (anywhere with creds):

```bash
aws ssm put-parameter --name domino-api-key \
  --value "your-domino-api-key" \
  --type SecureString --region us-east-1 --overwrite
```

## Running inside a VPC (internal endpoints)

Set `vpc_config` to place the canary Lambda in your VPC so it can reach an
internal frontend/API (no public internet path). Just name the VPC and subnets
(or pass ids directly) — the module looks them up and creates the security
group for you:

```hcl
module "canary" {
  source = "./modules/synthetic-canary"
  name            = "internal-api-check"
  sns_topic_email = "alerts@example.com"

  vpc_config = {
    vpc_name     = "aft-global-default-vpc"          # or vpc_id = "vpc-..."
    subnet_names = ["aft-global-default-vpc-private"] # or subnet_ids = ["subnet-..."]
  }
}
```

Resolution rules: `vpc_id` wins over `vpc_name` (matched on the `Name` tag);
`subnet_ids` win over `subnet_names` (matched on the `Name` tag within the VPC).

The security group: **yes, AWS requires one** — if you don't pass
`security_group_ids`, the module creates `synth-canary-<name>` with all egress
(within a private subnet that only reaches the VPC CIDR, NAT, and VPC endpoints
per the route table anyway). For tighter control, pass existing SGs:

```hcl
  vpc_config = {
    vpc_id             = "vpc-12345678"
    subnet_ids         = ["subnet-abcdef12", "subnet-34567890"]
    security_group_ids = [aws_security_group.api_client.id]   # your SG with scoped egress
  }
```

Gotchas:

- **Egress for AWS services**: the canary still writes artifacts to S3, logs to
  CloudWatch, and traces to X-Ray. In private subnets without a NAT gateway you
  must add VPC endpoints: S3 (gateway endpoint + route table entry), and
  `com.amazonaws.<region>.logs` + `com.amazonaws.<region>.xray` (interface
  endpoints). With a NAT gateway (workspace pattern: per-project NAT), nothing
  extra is needed.
- **Security groups**: with the module-created SG, the API/ALB SG still needs
  ingress from `synth-canary-<name>` on the listener port. DNS resolution
  relies on the VPC's default DNS settings.
- The API's URL goes in `environment_variables` (or the domino `endpoint`);
  the canary just needs to be able to resolve + reach it from the private subnet.

## Optional module vars

| var | default | purpose |
|---|---|---|
| `type` | `"browser"` | `"browser"` or `"domino"` (picks the built-in source script) |
| `domino` | `null` | object — required when `type = "domino"` (see Domino section) |
| `source_file` | built-in per `type` | path to your canary `.py`; handler is derived from the filename |
| `artifact_bucket_name` | auto-generated | pin a fixed bucket name |
| `environment_variables` | `{}` | runtime env vars (e.g. API endpoint) |
| `vpc_config` | `null` | `{ vpc_id/vpc_name, subnet_ids/subnet_names, security_group_ids? }` — run inside a VPC; SG auto-created if omitted |
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
