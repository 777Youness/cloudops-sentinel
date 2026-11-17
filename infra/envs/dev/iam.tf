# The workload instance's role (ADR 0017). Separate from:
#   - Sentinel's read-only role (infra/policies/sentinel-readonly.json, a later PR, D10);
#   - the operator's Terraform permissions (infra/policies/operator-terraform.json, by hand).

resource "aws_iam_role" "workload" {
  name        = "${local.name}-workload"
  description = "CloudOps Sentinel workload instance: SSM agent and CloudWatch agent"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Session Manager (shells without SSH) and Run Command (fault scripts, Day 4c). AWS documents
# this managed policy as the instance permission Session Manager needs.
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.workload.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Inline instead of the managed CloudWatchAgentServerPolicy (D6): that policy allows
# logs:CreateLogGroup and logs:PutRetentionPolicy on "*", so the agent could create log
# groups that Terraform does not manage and that never expire. Here the agent can only
# write to the one log group Terraform created, and publish metrics in the CWAgent namespace.
resource "aws_iam_role_policy" "cloudwatch_agent" {
  name = "cloudwatch-agent-scoped"
  role = aws_iam_role.workload.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "PublishAgentMetricsOnly"
        Effect   = "Allow"
        Action   = ["cloudwatch:PutMetricData"]
        Resource = "*" # PutMetricData has no resource type; the namespace condition limits it
        Condition = {
          StringEquals = { "cloudwatch:namespace" = "CWAgent" }
        }
      },
      {
        Sid    = "ShipTheAccessLog"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams",
        ]
        Resource = [
          aws_cloudwatch_log_group.access.arn,
          "${aws_cloudwatch_log_group.access.arn}:*",
        ]
      },
    ]
  })
}

resource "aws_iam_instance_profile" "workload" {
  name = "${local.name}-workload"
  role = aws_iam_role.workload.name
}

# --- Sentinel's read-only role (Day 5, ADR 0018) --------------------------------------------
# The identity the Sentinel backend uses (profile "sentinel"). Its only permission is the
# tested template infra/policies/sentinel-readonly.json: ten read actions, region-pinned,
# with an explicit Deny on every write. Only var.sentinel_reader_arn may assume it, and only
# with an identity policy of its own (infra/policies/operator-assume-sentinel.json).

data "aws_caller_identity" "current" {} # needs no permission

resource "aws_iam_role" "sentinel_readonly" {
  name                 = "${local.name}-readonly"
  description          = "CloudOps Sentinel collector: read-only telemetry access"
  max_session_duration = 3600

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = var.sentinel_reader_arn }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "sentinel_readonly" {
  name = "sentinel-readonly"
  role = aws_iam_role.sentinel_readonly.id

  policy = templatefile("${path.module}/../../policies/sentinel-readonly.json", {
    region         = var.aws_region
    account_id     = data.aws_caller_identity.current.account_id
    log_group_name = aws_cloudwatch_log_group.access.name
  })
}
