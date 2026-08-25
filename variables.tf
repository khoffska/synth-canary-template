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

variable "timeout_in_seconds" {
  type        = number
  description = "Canary execution timeout in seconds. AWS caps this at 300s for canaries on a <=5-minute schedule (the default rate(5 minutes)); domino workspace canaries on a rate(1 hour) schedule need 600 (poll timeout 240s + start time)."
  default     = 300
}

variable "environment" {
  type        = string
  description = "Deployment environment. Selects the domino config from local.domino_envs (prod/stage)."

  validation {
    condition     = contains(["prod", "stage"], var.environment)
    error_message = "environment must be \"prod\" or \"stage\" (add your env to local.domino_envs in main.tf first)."
  }
}

variable "domino_parameter_name" {
  type        = string
  description = "Name of the SSM Parameter Store parameter holding the Domino API key (created by secrets.tf with a placeholder value)."
  default     = "domino-api-key"
}
