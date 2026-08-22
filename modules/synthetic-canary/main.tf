resource "aws_synthetics_canary" "this" {
  name                 = var.name
  artifact_s3_location = "s3://${aws_s3_bucket.canary_output.id}/"
  execution_role_arn   = aws_iam_role.canary.arn
  zip_file             = data.archive_file.canary.output_path
  handler              = local.handler
  runtime_version      = var.runtime_version
  delete_lambda        = var.delete_lambda

  schedule {
    expression = var.schedule_expression
  }

  dynamic "run_config" {
    for_each = length(local.environment_variables) > 0 ? [1] : []
    content {
      environment_variables = local.environment_variables
      timeout_in_seconds    = var.timeout_in_seconds
    }
  }

  start_canary = var.start_canary

  dynamic "vpc_config" {
    for_each = var.vpc_config != null ? [1] : []
    content {
      subnet_ids         = local.subnet_ids
      security_group_ids = local.security_group_ids
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "this" {
  alarm_name                = var.name
  comparison_operator       = var.alarm_comparison_operator
  evaluation_periods        = var.alarm_evaluation_periods
  metric_name               = "SuccessPercent"
  namespace                 = "CloudWatchSynthetics"
  threshold                 = var.alarm_threshold
  statistic                 = "Average"
  period                    = var.alarm_period
  alarm_description         = "This alarm fires if the canary fails"
  insufficient_data_actions = []
  alarm_actions             = [aws_sns_topic.this.arn]

  dimensions = {
    CanaryName = var.name
  }
}

resource "aws_sns_topic" "this" {
  name = var.name
}

resource "aws_sns_topic_subscription" "this" {
  topic_arn = aws_sns_topic.this.arn
  protocol  = "email"
  endpoint  = var.sns_topic_email

  depends_on = [aws_sns_topic.this]
}
