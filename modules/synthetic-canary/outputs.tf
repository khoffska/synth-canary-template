output "canary_id" {
  description = "ID of the synthetics canary."
  value       = aws_synthetics_canary.this.id
}

output "canary_arn" {
  description = "ARN of the synthetics canary."
  value       = aws_synthetics_canary.this.arn
}

output "sns_topic_arn" {
  description = "ARN of the alarm SNS topic."
  value       = aws_sns_topic.this.arn
}

output "alarm_arn" {
  description = "ARN of the CloudWatch metric alarm."
  value       = aws_cloudwatch_metric_alarm.this.arn
}

output "artifact_bucket" {
  description = "Name of the artifact S3 bucket."
  value       = aws_s3_bucket.canary_output.bucket
}

output "execution_role_arn" {
  description = "ARN of the canary execution role."
  value       = aws_iam_role.canary.arn
}
