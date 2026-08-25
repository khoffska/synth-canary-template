# Everything lives inside the module — canary, alarm, SNS topic + email
# subscription, IAM execution role, and artifact S3 bucket. The root just
# calls it. See README.md for optional overrides (source_file, bucket name,
# alarm tuning, environment variables).
locals {
  # Domino config per environment — endpoint, project_id, and workspace_id all
  # differ between envs. Add a new env here, then extend the validation on
  # var.environment. (Values below are placeholders — fill in the real ones.)
  domino_envs = {
    prod = {
      endpoint     = "https://domino.prod.example.com"
      project_id   = "proj-prod-123"
      action       = "workspace"
      workspace_id = "xyz"
    }
    stage = {
      endpoint     = "https://domino.stage.example.com"
      project_id   = "proj-stage-456"
      action       = "workspace"
      workspace_id = "abc"
    }
  }
}

module "canary" {
  source = "./modules/synthetic-canary"

  name            = var.canary_name
  sns_topic_email = var.sns_topic_email
  type            = "domino"

  schedule_expression = var.schedule_expression
  runtime_version     = var.runtime_version
  timeout_in_seconds  = var.timeout_in_seconds

  domino = local.domino_envs[var.environment]

  # Optional overrides:
  # source_file          = "${path.module}/src/my-canary.py"  # point at your own .py anywhere
  # artifact_bucket_name = "my-fixed-bucket-name"             # pin the bucket name (else auto-generated)
  # environment_variables = { ENDPOINT = "https://api.example.com" }
}
