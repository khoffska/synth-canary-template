# Domino API key parameter — starter version.
#
# Creates an SSM Parameter Store SecureString with a dummy value so the
# plumbing (IAM read policy, canary env var) works end to end. The real key is
# set out-of-band (console or the create-secret workflow) via put-parameter —
# ignore_changes stops Terraform from reverting it on the next apply.

resource "aws_ssm_parameter" "domino_api_key" {
  name  = var.domino_parameter_name
  type  = "SecureString"
  value = "foo bar" # placeholder — replace out-of-band

  lifecycle {
    ignore_changes = [value]
  }
}
