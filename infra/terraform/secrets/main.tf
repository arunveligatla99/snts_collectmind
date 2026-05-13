# T128 / ADR-0005 — secrets module.
#
# AWS Secrets Manager entries for runtime secrets + IAM roles with least
# privilege. Highest-blast-radius file in the IaC set: every IAM policy
# here is reviewed line-by-line before any apply.
#
# Constitution Principle IX: secrets supplied via Secrets Manager in
# deployed environments; no secrets in git, ever.

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

variable "weights_bucket_arn" {
  type        = string
  description = "ARN of the S3 weights bucket (from storage module)."
  default     = ""
}

variable "tags" {
  type = map(string)
  default = {
    Project = "collectmind"
    Feature = "001-policy-loop-vertical-slice"
  }
}

# Placeholders for runtime secrets. Values are populated out-of-band via
# the AWS console or a separate secrets-pinning workflow; the IaC never
# stores cleartext.
resource "aws_secretsmanager_secret" "oauth2_client_secret" {
  name = "collectmind/oauth2-client-secret"
  tags = var.tags
}

resource "aws_secretsmanager_secret" "policy_signing_key" {
  name = "collectmind/policy-signing-key"
  tags = var.tags
}

resource "aws_secretsmanager_secret" "postgres_password" {
  name = "collectmind/postgres-password"
  tags = var.tags
}

# Task role for the orchestration-api Fargate task. Scope-tight:
# - read three named secrets above
# - get/put to the weights bucket prefix only
# - publish OTel via a private endpoint (handled at the security-group layer)
resource "aws_iam_role" "orchestration_api_task" {
  name = "collectmind-orchestration-api-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

data "aws_iam_policy_document" "orchestration_api_task" {
  statement {
    sid     = "ReadSecretsOnly"
    effect  = "Allow"
    actions = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = [
      aws_secretsmanager_secret.oauth2_client_secret.arn,
      aws_secretsmanager_secret.policy_signing_key.arn,
      aws_secretsmanager_secret.postgres_password.arn,
    ]
  }

  dynamic "statement" {
    for_each = var.weights_bucket_arn == "" ? [] : [1]
    content {
      sid     = "WeightsBucketReadOnly"
      effect  = "Allow"
      actions = ["s3:GetObject", "s3:ListBucket"]
      resources = [
        var.weights_bucket_arn,
        "${var.weights_bucket_arn}/*",
      ]
    }
  }
}

resource "aws_iam_policy" "orchestration_api_task" {
  name   = "collectmind-orchestration-api-task"
  policy = data.aws_iam_policy_document.orchestration_api_task.json
}

resource "aws_iam_role_policy_attachment" "orchestration_api_task" {
  role       = aws_iam_role.orchestration_api_task.name
  policy_arn = aws_iam_policy.orchestration_api_task.arn
}

# Execution role for ECS to pull images from ECR and write to CloudWatch.
resource "aws_iam_role" "ecs_execution" {
  name = "collectmind-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

output "orchestration_api_task_role_arn" { value = aws_iam_role.orchestration_api_task.arn }
output "ecs_execution_role_arn" { value = aws_iam_role.ecs_execution.arn }
output "oauth2_client_secret_arn" { value = aws_secretsmanager_secret.oauth2_client_secret.arn }
output "policy_signing_key_arn" { value = aws_secretsmanager_secret.policy_signing_key.arn }
output "postgres_password_arn" { value = aws_secretsmanager_secret.postgres_password.arn }
