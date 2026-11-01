output "instance_id" {
  description = "The workload instance."
  value       = aws_instance.workload.id
}

output "public_ip" {
  description = "Auto-assigned public IPv4 address (changes with every new instance)."
  value       = aws_instance.workload.public_ip
}

output "app_url" {
  description = "The workload app, reachable only from operator_cidr."
  value       = "http://${aws_instance.workload.public_ip}:${var.app_port}/"
}

output "log_group_name" {
  description = "Where the CloudWatch agent ships the access log."
  value       = aws_cloudwatch_log_group.access.name
}

output "cpu_alarm_name" {
  description = "The one CPU alarm (no actions)."
  value       = aws_cloudwatch_metric_alarm.cpu_high.alarm_name
}

output "safety_timer_minutes" {
  description = "Minutes after boot at which the instance powers off and terminates (UNTESTED until the termination test passes)."
  value       = var.safety_timer_minutes
}

output "ssm_session_command" {
  description = "Open a shell on the instance (Session Manager plugin required)."
  value       = "aws ssm start-session --target ${aws_instance.workload.id} --region ${var.aws_region} --profile sentinel-admin"
}
