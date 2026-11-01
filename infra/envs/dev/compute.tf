# The workload instance (CLAUDE.md section 6, ADR 0016, ADR 0017).
#
# Safety timer: user_data installs a systemd timer FIRST, which runs `systemctl poweroff`
# safety_timer_minutes after boot. Because instance_initiated_shutdown_behavior is
# "terminate", an OS-initiated poweroff terminates the instance: compute billing stops, the
# root volume is deleted (delete_on_termination) and the public IPv4 address is released.
# STATUS: UNTESTED on a real EC2 instance. Do not rely on it until the termination test in
# infra/README.md has passed and its result is recorded.

# Latest Amazon Linux 2023 (standard AMI: the SSM agent is preinstalled), x86_64 for t3.
data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_instance" "workload" {
  # insecure_value: the AMI id is not a secret, and value would mark it sensitive.
  ami           = data.aws_ssm_parameter.al2023_ami.insecure_value
  instance_type = "t3.micro"

  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.workload.id]
  associate_public_ip_address = true # auto-assigned, released at stop/termination; not an EIP
  iam_instance_profile        = aws_iam_instance_profile.workload.name
  # No key_name: there is no SSH key pair and no port 22. Shell access is Session Manager.

  credit_specification {
    cpu_credits = "standard"
  }

  monitoring = false # no detailed monitoring (forbidden, billed)

  instance_initiated_shutdown_behavior = "terminate"
  disable_api_termination              = false

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }

  root_block_device {
    volume_type           = "gp3"
    encrypted             = true # AWS-managed key aws/ebs, not a customer-managed key
    delete_on_termination = true
    # No volume_size: the AMI's own size is used (not documented on the AL2023 page; see
    # docs/cost.md). No iops/throughput: gp3 defaults, no provisioned extras.
  }

  user_data = templatefile("${path.module}/templates/user_data.sh.tftpl", {
    safety_timer_minutes = var.safety_timer_minutes
    app_port             = var.app_port
    access_log_path      = local.access_log_path
    app_py               = file("${path.module}/../../../workload/app.py")
    agent_config = templatefile("${path.module}/templates/cloudwatch-agent.json.tftpl", {
      log_group_name  = aws_cloudwatch_log_group.access.name
      access_log_path = local.access_log_path
    })
  })
  # A changed timer, app or agent config gives a new instance instead of a silent no-op:
  # user_data runs only at first boot.
  user_data_replace_on_change = true

  tags = {
    Name                        = "${local.name}-workload"
    "cloudops-sentinel:monitor" = "true"
  }

  # The bootstrap installs packages, so the route to the internet must exist first.
  depends_on = [aws_route.internet, aws_route_table_association.public]

  lifecycle {
    # A new AL2023 release must not replace a running instance on the next plan.
    ignore_changes = [ami]
  }
}
