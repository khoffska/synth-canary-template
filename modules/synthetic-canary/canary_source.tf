# Zip the canary source at plan time so the .py is the single source of truth.
# The Synthetics Python runtime loads the handler module from a top-level
# "python/" folder inside the zip, so the .py must live at python/<stem>.py —
# which is what we write, so the handler (derived from the filename) always matches.
#
# aws_synthetics_canary only diffs the zip_file *path*, not its contents, so the
# source hash is baked into output_path — any edit to the .py yields a new path
# and forces the canary to re-upload its code on the next apply.
locals {
  source_file = coalesce(
    var.source_file,
    var.type == "domino" ? "${path.module}/src/domino_canary.py" : "${path.module}/src/my-canary.py",
  )
  handler     = "${trimsuffix(basename(local.source_file), ".py")}.handler"
  source_stem = trimsuffix(basename(local.source_file), ".py")
  bucket_name = coalesce(var.artifact_bucket_name, "synthcan-${lower(var.name)}-${random_id.suffix.hex}")

  # Domino env vars, mirroring upstream cloudwatchsyntheticcanary's merge logic.
  # Only include what's actually set so the runtime skips unconfigured checks.
  domino_env = var.domino != null ? merge(
    {
      DOMINO_HOST       = var.domino.endpoint
      DOMINO_PROJECT_ID = var.domino.project_id
      DOMINO_ACTION     = coalesce(var.domino.action, "job")
    },
    # Prefer the Secrets Manager path; only fall back to plaintext if no secret ARN is set.
    var.domino.api_key_secret_arn != null ? { DOMINO_API_KEY_SECRET_ID = var.domino.api_key_secret_arn } : (var.domino.api_key == null ? {} : { DOMINO_API_KEY = var.domino.api_key }),
    var.domino.api_key_secret_json_key == null ? {} : { DOMINO_API_KEY_SECRET_JSON_KEY = var.domino.api_key_secret_json_key },
    var.domino.run_command == null ? {} : { DOMINO_RUN_COMMAND = var.domino.run_command },
    var.domino.cleanup == null ? {} : { DOMINO_CLEANUP = tostring(var.domino.cleanup) },
    var.domino.max_latency_ms == null ? {} : { DOMINO_MAX_LATENCY_MS = tostring(var.domino.max_latency_ms) },
  ) : {}

  # Manual environment_variables win over anything the module derived.
  environment_variables = merge(local.domino_env, var.environment_variables)

  domino_secret_arns = var.domino != null && var.domino.api_key_secret_arn != null ? [var.domino.api_key_secret_arn] : []
}

data "archive_file" "canary" {
  type        = "zip"
  output_path = "${path.module}/build/${var.name}-${filemd5(local.source_file)}.zip"

  source {
    content  = file(local.source_file)
    filename = "python/${basename(local.source_file)}"
  }

  lifecycle {
    precondition {
      condition     = var.type != "domino" || var.domino != null
      error_message = "type = \"domino\" requires the domino{} object to be set."
    }
  }
}

resource "random_id" "suffix" {
  byte_length = 4
}
