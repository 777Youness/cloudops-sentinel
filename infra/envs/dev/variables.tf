variable "aws_region" {
  description = "The single AWS region of V1 (CLAUDE.md)."
  type        = string
  default     = "eu-west-3"

  validation {
    condition     = var.aws_region == "eu-west-3"
    error_message = "V1 is single-region: aws_region must be eu-west-3."
  }
}

variable "environment" {
  description = "Environment name, used in tags and resource names."
  type        = string
  default     = "dev"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,15}$", var.environment))
    error_message = "environment must be lowercase letters, digits or dashes (2-16 characters)."
  }
}

variable "operator_cidr" {
  description = "Your public IPv4 address as a /32. The only source allowed to reach the app port. Set it in terraform.tfvars (gitignored), never in a commit."
  type        = string
  # No default on purpose: a plan without it fails instead of opening the port to anyone.

  validation {
    condition = (
      can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/32$", var.operator_cidr))
      && can(cidrhost(var.operator_cidr, 0))
    )
    error_message = "operator_cidr must be a single IPv4 address with /32, for example 203.0.113.10/32."
  }
}

variable "app_port" {
  description = "TCP port of the workload app, open only to operator_cidr."
  type        = number
  default     = 8080

  validation {
    # Above 1023 so the app runs as an unprivileged user; never 22 (no SSH anywhere).
    condition     = var.app_port >= 1024 && var.app_port <= 65535
    error_message = "app_port must be between 1024 and 65535."
  }
}

variable "availability_zone" {
  description = "Availability Zone of the single public subnet."
  type        = string
  default     = "eu-west-3a"

  validation {
    condition     = can(regex("^eu-west-3[a-c]$", var.availability_zone))
    error_message = "availability_zone must be eu-west-3a, eu-west-3b or eu-west-3c."
  }
}

variable "safety_timer_minutes" {
  description = "Minutes after boot at which the instance powers itself off; with shutdown behaviour terminate, it is then terminated (ADR 0017, UNTESTED on real EC2). Use 15 only for the termination test."
  type        = number
  default     = 240

  validation {
    condition     = var.safety_timer_minutes >= 15 && var.safety_timer_minutes <= 480 && floor(var.safety_timer_minutes) == var.safety_timer_minutes
    error_message = "safety_timer_minutes must be a whole number between 15 and 480."
  }
}

variable "log_retention_days" {
  description = "Retention of the workload log group (CLAUDE.md: every log group has one; default 3 days)."
  type        = number
  default     = 3

  validation {
    condition     = contains([1, 3], var.log_retention_days)
    error_message = "log_retention_days must be 1 or 3."
  }
}
