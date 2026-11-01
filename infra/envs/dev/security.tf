# The workload's only security group (CLAUDE.md section 6: no port 22 anywhere; the app
# port only from var.operator_cidr). Rules are separate resources so each one is reviewable.
#
# Terraform removes the allow-all egress rule AWS adds to a new security group, so the only
# egress is the HTTPS rule below. HTTPS is enough (ADR 0017): SSM (ssm, ssmmessages,
# ec2messages), CloudWatch and the AL2023 package repositories are all reached on 443, and
# DNS, instance metadata and time sync are not filtered by security groups.

resource "aws_security_group" "workload" {
  name        = "${local.name}-workload"
  description = "CloudOps Sentinel workload: app port from the operator only, HTTPS out"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${local.name}-workload" }
}

resource "aws_vpc_security_group_ingress_rule" "app_from_operator" {
  security_group_id = aws_security_group.workload.id
  description       = "Workload app from the operator's /32 only"
  ip_protocol       = "tcp"
  from_port         = var.app_port
  to_port           = var.app_port
  cidr_ipv4         = var.operator_cidr
}

resource "aws_vpc_security_group_egress_rule" "https_out" {
  security_group_id = aws_security_group.workload.id
  description       = "HTTPS to SSM, CloudWatch and the AL2023 package repositories"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}
