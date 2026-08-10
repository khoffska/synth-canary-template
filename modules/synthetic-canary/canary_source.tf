# Zip the canary source at plan time so the .py is the single source of truth.
# The Synthetics Python runtime loads the handler module from a top-level
# "python/" folder inside the zip, so the .py must live at python/<stem>.py —
# which is what we write, so the handler (derived from the filename) always matches.
#
# aws_synthetics_canary only diffs the zip_file *path*, not its contents, so the
# source hash is baked into output_path — any edit to the .py yields a new path
# and forces the canary to re-upload its code on the next apply.
locals {
  source_file = coalesce(var.source_file, "${path.module}/src/my-canary.py")
  handler     = "${trimsuffix(basename(local.source_file), ".py")}.handler"
  source_stem = trimsuffix(basename(local.source_file), ".py")
  bucket_name = coalesce(var.artifact_bucket_name, "synthcan-${lower(var.name)}-${random_id.suffix.hex}")
}

data "archive_file" "canary" {
  type        = "zip"
  output_path = "${path.module}/build/${var.name}-${filemd5(local.source_file)}.zip"

  source {
    content  = file(local.source_file)
    filename = "python/${basename(local.source_file)}"
  }
}

resource "random_id" "suffix" {
  byte_length = 4
}
