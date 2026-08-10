# Scoped SSM Parameter Store read access for Domino canaries that resolve their
# API key from a SecureString parameter at runtime. Only created when
# domino.api_key_ssm_name is set.
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  domino_parameter_arns = [
    for name in local.domino_ssm_names :
    "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/${name}"
  ]
}

resource "aws_iam_policy" "canary_ssm" {
  count = length(local.domino_ssm_names) > 0 ? 1 : 0
  name  = "policy-6180333-${var.name}"

  policy = templatefile("${path.module}/policies/canary_ssm.json.tftpl", {
    parameter_arns = jsonencode(local.domino_parameter_arns)
  })
}

# Shared execution role assumed by the canary when it runs (created by the module).
resource "aws_iam_role" "canary" {
  name        = "synth-canary-${var.name}"
  description = "Role used to provide permissions for the canary to run."
  managed_policy_arns = concat(
    [aws_iam_policy.canary_put_object.arn, aws_iam_policy.canary_permissions.arn],
    length(local.domino_ssm_names) > 0 ? [aws_iam_policy.canary_ssm[0].arn] : [],
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
