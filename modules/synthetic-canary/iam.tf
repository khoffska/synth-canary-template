# Shared execution role assumed by the canary when it runs (created by the module).
resource "aws_iam_role" "canary" {
  name        = "synth-canary-${var.name}"
  description = "Role used to provide permissions for the canary to run."
  managed_policy_arns = concat(
    [aws_iam_policy.canary_put_object.arn, aws_iam_policy.canary_permissions.arn],
    length(local.domino_secret_arns) > 0 ? [aws_iam_policy.canary_secrets[0].arn] : [],
  )
  assume_role_policy = file("${path.module}/policies/assume_role.json")
}

resource "aws_iam_policy" "canary_put_object" {
  name = "policy-618033-${var.name}"

  policy = templatefile("${path.module}/policies/canary_put_object.json.tftpl", {
    bucket_arn = aws_s3_bucket.canary_output.arn
  })
}

resource "aws_iam_policy" "canary_permissions" {
  name = "policy-6180332-${var.name}"

  policy = templatefile("${path.module}/policies/canary_permissions.json.tftpl", {
    bucket_arn = aws_s3_bucket.canary_output.arn
  })
}

# Scoped Secrets Manager read access for Domino canaries that resolve their API
# key from a secret at runtime. Only created when domino.api_key_secret_arn is set.
resource "aws_iam_policy" "canary_secrets" {
  count = length(local.domino_secret_arns) > 0 ? 1 : 0
  name  = "policy-6180333-${var.name}"

  policy = templatefile("${path.module}/policies/canary_secrets.json.tftpl", {
    secret_arns = jsonencode(local.domino_secret_arns)
  })
}
