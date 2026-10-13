terraform {
  # 1.10+ as required by CLAUDE.md (it also adds native S3 state locking, the migration
  # path described in ADR 0016).
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Major version 6; the exact version is pinned in .terraform.lock.hcl, which is
      # committed after the first `terraform init`.
      version = "~> 6.0"
    }
  }

  # No backend block on purpose: state is local (terraform.tfstate in this directory,
  # gitignored). One operator, disposable environment, destroyed after each session.
  # See ADR 0016 for the trade-off and the migration to an S3 backend.
}
