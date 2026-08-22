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
    endpoint         = string                  # required: Domino host base URL, e.g. https://domino.example.com
    project_id       = string                  # required: target Domino project id
    workspace_id     = optional(string)        # required when action = "workspace" — target workspace id
    action           = optional(string, "job") # "job" | "workspace"
    run_command      = optional(string)        # job run command (default "main.py")
    cleanup          = optional(bool, true)    # stop what we started so no paid compute is left running
    max_latency_ms   = optional(number)        # fail if start request exceeds this
    api_key_ssm_name = optional(string)        # SSM Parameter Store parameter name (SecureString, preferred)
    api_key          = optional(string)        # plaintext fallback — avoid for real secrets
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

variable "vpc_config" {
  type = object({
    vpc_id             = optional(string)       # VPC id (either vpc_id or vpc_name is required)
    vpc_name           = optional(string)       # VPC Name tag (alternative to vpc_id)
    subnet_ids         = optional(list(string)) # explicit subnet ids (either subnet_ids or subnet_names is required)
    subnet_names       = optional(list(string)) # subnet Name tags to look up in the VPC
    security_group_ids = optional(list(string)) # existing SGs; if omitted the module creates one (all egress)
  })
  description = "VPC configuration for the canary Lambda (required to reach internal/private endpoints). Leave null to run in the default Synthetics environment. The module creates a security group when security_group_ids is omitted."
  default     = null

  validation {
    condition = var.vpc_config == null || (
      (try(var.vpc_config.vpc_id, null) != null || try(var.vpc_config.vpc_name, null) != null) &&
      (try(length(var.vpc_config.subnet_ids), 0) > 0 || try(length(var.vpc_config.subnet_names), 0) > 0)
    )
    error_message = "vpc_config requires vpc_id or vpc_name, and subnet_ids or subnet_names."
  }
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

variable "timeout_in_seconds" {
  type        = number
  description = "Canary execution timeout in seconds. Must exceed the workspace poll timeout (DOMINO_WORKSPACE_POLL_TIMEOUT_SECONDS, default 240) plus start time, or the Lambda is killed mid-poll."
  default     = 600
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
