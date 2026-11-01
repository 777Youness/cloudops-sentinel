# Day 4b: the disposable workload that Sentinel monitors (ADR 0016, ADR 0017).
#
#   network.tf        VPC, internet gateway, one public subnet, route table, default SG locked down
#   security.tf       workload security group: app port from operator_cidr only, HTTPS out
#   iam.tf            instance role: SSM core + scoped CloudWatch permissions (no CreateLogGroup)
#   compute.tf        t3.micro, AL2023, IMDSv2, encrypted gp3 root, shutdown behaviour terminate
#   observability.tf  log group (retention) and one CPU alarm without actions
#
# Not here, on purpose: Sentinel's read-only role (separate PR after the termination test,
# D10) and the operator's own permissions (infra/policies/operator-terraform.json, attached
# by hand, never by Terraform).

locals {
  name = "cloudops-sentinel-${var.environment}"

  vpc_cidr    = "10.20.0.0/16"
  subnet_cidr = "10.20.1.0/24"

  # Workload paths on the instance. The access log is what the agent ships to CloudWatch.
  access_log_path = "/var/log/cloudops-workload/access.log"
}
