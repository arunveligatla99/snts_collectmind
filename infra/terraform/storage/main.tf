# T128 / ADR-0005 — storage module.
# S3 buckets: SLM weight cache (immutable, versioned, SSE), build artifacts,
# and SBOM uploads. Each bucket is versioned and server-side encrypted.

terraform {
  required_version = ">= 1.9.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "tags" {
  type = map(string)
  default = {
    Project = "collectmind"
    Feature = "001-policy-loop-vertical-slice"
  }
}

resource "aws_s3_bucket" "weights" {
  bucket = "collectmind-slm-weights"
  tags   = var.tags
}

resource "aws_s3_bucket_versioning" "weights" {
  bucket = aws_s3_bucket.weights.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "weights" {
  bucket = aws_s3_bucket.weights.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "weights" {
  bucket                  = aws_s3_bucket.weights.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "artifacts" {
  bucket = "collectmind-build-artifacts"
  tags   = var.tags
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "sbom" {
  bucket = "collectmind-sbom"
  tags   = var.tags
}

resource "aws_s3_bucket_versioning" "sbom" {
  bucket = aws_s3_bucket.sbom.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "sbom" {
  bucket = aws_s3_bucket.sbom.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "sbom" {
  bucket                  = aws_s3_bucket.sbom.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "weights_bucket" { value = aws_s3_bucket.weights.bucket }
output "artifacts_bucket" { value = aws_s3_bucket.artifacts.bucket }
output "sbom_bucket" { value = aws_s3_bucket.sbom.bucket }
