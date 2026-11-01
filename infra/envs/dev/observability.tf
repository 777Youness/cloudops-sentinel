# The workload's log group and its one alarm. Both survive an instance termination and are
# removed only by `terraform destroy` (ADR 0017, docs/cost.md).

resource "aws_cloudwatch_log_group" "access" {
  name              = "/cloudops-sentinel/${var.environment}/access"
  retention_in_days = var.log_retention_days

  tags = { Name = "${local.name}-access" }
}

# Named cloudops-sentinel-* so Sentinel's read-only policy (DescribeAlarms on that prefix)
# can read its state. No actions: there is no SNS in V1, and an alarm never acts on the
# instance. Billed by the hour while it exists ($0.10 per alarm-month in Paris).
resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name        = "${local.name}-cpu-high"
  alarm_description = "CPU at or above 90% for two 5-minute periods (same threshold as R-CPU-SAT)"

  namespace   = "AWS/EC2"
  metric_name = "CPUUtilization"
  dimensions  = { InstanceId = aws_instance.workload.id }
  statistic   = "Average"
  # Basic monitoring publishes EC2 metrics every 5 minutes, so the period is at least 300 s.
  period              = 300
  evaluation_periods  = 2
  threshold           = 90
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "missing"

  actions_enabled = false

  tags = { Name = "${local.name}-cpu-high" }
}
