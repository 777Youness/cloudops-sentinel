# Day 4a: structure only. This configuration creates no resources yet, so a plan is empty.
#
# Day 4b adds (ADR 0016): VPC, internet gateway, one public subnet and its route table,
# the default security group locked down, the workload security group (no inbound except
# the app port from var.operator_cidr), the workload instance role and profile, the log
# group (3-day retention), the t3.micro instance, and the read-only role for Sentinel,
# whose policy is ../../policies/sentinel-readonly.json (rendered with templatefile()).
