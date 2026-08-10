# Optional: create the Domino API key secret in Secrets Manager from Terraform.
#
# Enabled by setting domino_api_key in your tfvars (NOT in a committed file).
# The value is wrapped in JSON under the "apiKey" key, so pair it with
# api_key_secret_json_key = "apiKey" in the domino{} block.
#
# count = 0 when domino_api_key is empty (the default) — nothing is created,
# and you can create the secret out-of-band (console / create-secret workflow).

resource "aws_secretsmanager_secret" "domino_api_key" {
  count = var.domino_api_key != "" ? 1 : 0
  name  = var.domino_secret_name
}

resource "aws_secretsmanager_secret_version" "domino_api_key" {
  count         = var.domino_api_key != "" ? 1 : 0
  secret_id     = aws_secretsmanager_secret.domino_api_key[0].id
  secret_string = jsonencode({ apiKey = var.domino_api_key })
}
