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
