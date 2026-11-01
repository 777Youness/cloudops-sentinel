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
