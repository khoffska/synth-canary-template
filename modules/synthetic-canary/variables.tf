variable "name" {
  type        = string
  description = "Name of the canary. Also used as the alarm name, SNS topic name, Lambda handler prefix (<name>.handler), IAM role name, and artifact bucket prefix."
}

variable "sns_topic_email" {
  type        = string
  description = "Email address subscribed to the canary's alarm SNS topic."
}

variable "source_file" {
  type        = string
  description = "Path to the canary source .py. The handler is derived from the filename (<stem>.handler). Leave null to use the example canary shipped inside the module (my-canary.py for type=browser, domino_canary.py for type=domino)."
  default     = null
}

variable "type" {
  type        = string
  description = "Canary type: \"browser\" (default, uses src/my-canary.py) or \"domino\" (uses src/domino_canary.py + the domino{} config)."
  default     = "browser"

  validation {
    condition     = contains(["browser", "domino"], var.type)
    error_message = "type must be \"browser\" or \"domino\"."
  }
}

variable "domino" {
  type = object({
    endpoint                = string                  # required: Domino host base URL, e.g. https://domino.example.com
    project_id              = string                  # required: target Domino project id
    action                  = optional(string, "job") # "job" | "workspace"
    run_command             = optional(string)        # job run command (default "main.py")
    cleanup                 = optional(bool, true)    # stop what we started so no paid compute is left running
    max_latency_ms          = optional(number)        # fail if start request exceeds this
    api_key_secret_arn      = optional(string)        # Secrets Manager secret id/ARN (preferred)
    api_key_secret_json_key = optional(string)        # if the secret is JSON, the key holding the api key
    api_key                 = optional(string)        # plaintext fallback — avoid for real secrets
  })
  description = "Domino Data Lab monitoring config. Required when type = \"domino\"."
  default     = null
}

variable "artifact_bucket_name" {
  type        = string
  description = "Explicit name for the artifact S3 bucket the module creates. Defaults to an auto-generated unique name."
  default     = null
}

variable "environment_variables" {
  type        = map(string)
  description = "Environment variables passed to the canary at runtime (e.g. the API endpoint for an API canary)."
  default     = {}
}

variable "runtime_version" {
  type        = string
  description = "Synthetics runtime version."
  default     = "syn-python-selenium-11.1"
}

variable "schedule_expression" {
  type        = string
  description = "Rate or cron expression controlling how often the canary runs."
  default     = "rate(5 minutes)"
}

variable "start_canary" {
  type        = bool
  description = "Whether to start the canary immediately after creation."
  default     = true
}

variable "delete_lambda" {
  type        = bool
  description = "Whether to delete the underlying Lambda when the canary is destroyed."
  default     = true
}

variable "alarm_comparison_operator" {
  type        = string
  description = "Comparison operator for the success-percent alarm."
  default     = "LessThanThreshold"
}

variable "alarm_threshold" {
  type        = number
  description = "SuccessPercent threshold below which the alarm fires."
  default     = 100
}

variable "alarm_evaluation_periods" {
  type        = number
  description = "Number of periods over which data is evaluated for the alarm."
  default     = 2
}

variable "alarm_period" {
  type        = number
  description = "Length in seconds of each alarm evaluation period."
  default     = 300
}
