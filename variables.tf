variable "region" {
  type        = string
  description = "AWS region to deploy the canary into."
  default     = "us-east-1"
}

variable "canary_name" {
  type        = string
  description = "Name of the canary. Also used as the alarm name, SNS topic name, Lambda handler prefix, IAM role name, and artifact bucket prefix."
}

variable "sns_topic_email" {
  type        = string
  description = "Email address subscribed to the canary's alarm SNS topic."
}

variable "schedule_expression" {
  type        = string
  description = "Rate or cron expression controlling how often the canary runs."
  default     = "rate(5 minutes)"
}

variable "runtime_version" {
  type        = string
  description = "Synthetics runtime version."
  default     = "syn-python-selenium-11.1"
}

variable "domino_secret_name" {
  type        = string
  description = "Name of the Secrets Manager secret holding the Domino API key (created by secrets.tf when domino_api_key is set)."
  default     = "domino-api-key"
}

variable "domino_api_key" {
  type        = string
  description = "Domino API key. Override in tfvars to have secrets.tf create the secret (wrapped as {\"apiKey\": \"...\"}). Leave empty to manage the secret out-of-band."
  default     = ""
  sensitive   = true
}
