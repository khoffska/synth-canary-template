output "canary_id" {
  description = "ID of the synthetics canary."
  value       = module.canary.canary_id
}

output "canary_arn" {
  description = "ARN of the synthetics canary."
  value       = module.canary.canary_arn
}

output "alarm_arn" {
  description = "ARN of the CloudWatch metric alarm."
  value       = module.canary.alarm_arn
}

output "sns_topic_arn" {
  description = "ARN of the alarm SNS topic."
  value       = module.canary.sns_topic_arn
}

output "artifact_bucket" {
  description = "Name of the artifact S3 bucket."
  value       = module.canary.artifact_bucket
}

output "execution_role_arn" {
  description = "ARN of the canary execution role."
  value       = module.canary.execution_role_arn
}
