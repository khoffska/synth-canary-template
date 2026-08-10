# Domino API key secret — starter version.
#
# Creates the secret with a dummy value so the plumbing (IAM read policy,
# canary env var, ARN reference) works end to end. The real key is set
# out-of-band (console or the create-secret workflow) via put-secret-value —
# ignore_changes stops Terraform from reverting it on the next apply.

resource "aws_secretsmanager_secret" "domino_api_key" {
  name = var.domino_secret_name
}

resource "aws_secretsmanager_secret_version" "domino_api_key" {
  secret_id     = aws_secretsmanager_secret.domino_api_key.id
  secret_string = jsonencode({ apiKey = "foo bar" }) # placeholder — replace out-of-band

  lifecycle {
    ignore_changes = [secret_string]
  }
}
