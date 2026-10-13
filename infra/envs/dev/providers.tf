provider "aws" {
  region = var.aws_region

  # Credentials come from the standard chain: run Terraform with AWS_PROFILE set to your
  # own operator profile (see infra/README.md). Nothing about credentials lives here.

  default_tags {
    tags = {
      Project     = "cloudops-sentinel"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
