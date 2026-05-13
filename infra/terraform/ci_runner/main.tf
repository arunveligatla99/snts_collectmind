# T129 — self-hosted GitHub Actions runner with GPU for the nightly soak.
#
# Single-node EC2 g5.2xlarge running the runner agent; registered to the
# org with the [self-hosted, gpu] labels that workflows reference.

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

variable "private_subnet_id" {
  type    = string
  default = ""
}

variable "runner_security_group_id" {
  type    = string
  default = ""
}

# tflint-ignore: terraform_unused_declarations
variable "github_runner_token_secret_arn" {
  type        = string
  description = "Secrets Manager ARN holding the GitHub runner registration token. Reserved for the workflow_dispatch runner-registration wiring (T120 follow-up); declared here so the root module wiring can be added without a module signature change."
  default     = ""
}

variable "tags" {
  type = map(string)
  default = {
    Project = "collectmind"
    Feature = "001-policy-loop-vertical-slice"
  }
}

data "aws_ami" "amzn_linux_gpu" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["amzn2-ami-graphics-hvm-*-x86_64-ebs"]
  }
}

resource "aws_iam_role" "runner" {
  name = "collectmind-ci-runner"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "runner_ssm" {
  role       = aws_iam_role.runner.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "runner" {
  name = "collectmind-ci-runner"
  role = aws_iam_role.runner.name
}

resource "aws_instance" "runner" {
  ami                    = data.aws_ami.amzn_linux_gpu.id
  instance_type          = "g5.2xlarge"
  subnet_id              = var.private_subnet_id
  iam_instance_profile   = aws_iam_instance_profile.runner.name
  vpc_security_group_ids = var.runner_security_group_id != "" ? [var.runner_security_group_id] : []

  user_data = <<-EOT
    #!/bin/bash
    set -euo pipefail
    # Bootstrap the GitHub runner. The registration token comes from
    # Secrets Manager; this user-data fetches it via the instance profile
    # and registers with the [self-hosted, gpu] labels referenced by
    # ci-workflow-dispatch.yaml and nightly.yaml.
    yum install -y docker jq awscli
    systemctl enable --now docker
    # The actual runner bootstrap is delegated to a managed script in S3
    # so it can be rotated without re-applying Terraform.
    aws s3 cp s3://collectmind-build-artifacts/ci-runner-bootstrap.sh /tmp/bootstrap.sh
    bash /tmp/bootstrap.sh
  EOT

  tags = merge(var.tags, { Name = "collectmind-ci-runner" })

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }
}

output "runner_instance_id" { value = aws_instance.runner.id }
