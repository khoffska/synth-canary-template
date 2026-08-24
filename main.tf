# Everything lives inside the module — canary, alarm, SNS topic + email
# subscription, IAM execution role, and artifact S3 bucket. The root just
# calls it. See README.md for optional overrides (source_file, bucket name,
# alarm tuning, environment variables).
module "canary" {
  source = "./modules/synthetic-canary"

  name            = var.canary_name
  sns_topic_email = var.sns_topic_email

  schedule_expression = var.schedule_expression
  runtime_version     = var.runtime_version
  timeout_in_seconds  = var.timeout_in_seconds

  # Optional overrides:
  # source_file          = "${path.module}/src/my-canary.py"  # point at your own .py anywhere
  # artifact_bucket_name = "my-fixed-bucket-name"             # pin the bucket name (else auto-generated)
  # environment_variables = { ENDPOINT = "https://api.example.com" }
}
