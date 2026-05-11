# T128 / ADR-0005 — compute module.
#
# Stateless app services run on ECS Fargate. The SLM inference container
# runs on ECS-on-EC2 with a Capacity Provider tied to an Auto Scaling
# Group of g5.2xlarge instances (default) or g6.xlarge (alternative).
#
# The EKS variant lives in `infra/terraform/eks/main.tf` behind a separate
# workspace; this module is the default cloud topology per ADR-0005.

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

variable "vpc_id" {
  type        = string
  description = "VPC ID from the networking module."
  default     = ""
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs from the networking module."
  default     = []
}

variable "app_sg_id" {
  type        = string
  description = "App security group ID from the networking module."
  default     = ""
}

variable "slm_sg_id" {
  type        = string
  description = "SLM security group ID from the networking module."
  default     = ""
}

variable "gpu_instance_type" {
  type        = string
  description = "GPU instance type for the SLM ASG. ADR-0005 default: g5.2xlarge."
  default     = "g5.2xlarge"
}

variable "slm_image_uri" {
  type        = string
  description = "Pinned vLLM image with weights baked; digest per ADR-0002."
  default     = "vllm/vllm-openai:v0.20.1@sha256:9eff9734a30b6713a8566217d36f8277630fd2d31cec7f0a0292835901a23aa4"
}

variable "tags" {
  type = map(string)
  default = {
    Project = "collectmind"
    Feature = "001-policy-loop-vertical-slice"
  }
}

# Fargate cluster for stateless app services.
resource "aws_ecs_cluster" "app" {
  name = "collectmind-app"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
  tags = var.tags
}

resource "aws_ecs_cluster_capacity_providers" "app" {
  cluster_name       = aws_ecs_cluster.app.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE"
  }
}

# ECS-on-EC2 cluster for the SLM.
resource "aws_ecs_cluster" "slm" {
  name = "collectmind-slm"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
  tags = var.tags
}

# AMI: Amazon ECS-optimized GPU AMI.
data "aws_ami" "ecs_gpu" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["amzn2-ami-ecs-gpu-hvm-*-x86_64-ebs"]
  }
}

resource "aws_iam_role" "ecs_instance" {
  name = "collectmind-slm-instance"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ecs_instance_managed" {
  role       = aws_iam_role.ecs_instance.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_instance_profile" "ecs_instance" {
  name = "collectmind-slm-instance"
  role = aws_iam_role.ecs_instance.name
}

resource "aws_launch_template" "slm" {
  name_prefix            = "collectmind-slm-"
  image_id               = data.aws_ami.ecs_gpu.id
  instance_type          = var.gpu_instance_type
  vpc_security_group_ids = var.slm_sg_id != "" ? [var.slm_sg_id] : []

  iam_instance_profile {
    arn = aws_iam_instance_profile.ecs_instance.arn
  }

  user_data = base64encode(<<-EOT
    #!/bin/bash
    echo "ECS_CLUSTER=${aws_ecs_cluster.slm.name}" >> /etc/ecs/ecs.config
    echo "ECS_ENABLE_GPU_SUPPORT=true" >> /etc/ecs/ecs.config
  EOT
  )

  tag_specifications {
    resource_type = "instance"
    tags          = merge(var.tags, { Name = "collectmind-slm-instance" })
  }
}

resource "aws_autoscaling_group" "slm" {
  name                = "collectmind-slm"
  min_size            = 1
  max_size            = 4
  desired_capacity    = 1
  vpc_zone_identifier = var.private_subnet_ids

  launch_template {
    id      = aws_launch_template.slm.id
    version = "$Latest"
  }

  tag {
    key                 = "AmazonECSManaged"
    value               = ""
    propagate_at_launch = true
  }
}

resource "aws_ecs_capacity_provider" "slm" {
  name = "collectmind-slm"
  auto_scaling_group_provider {
    auto_scaling_group_arn = aws_autoscaling_group.slm.arn
    managed_scaling {
      status                    = "ENABLED"
      target_capacity           = 80
      minimum_scaling_step_size = 1
      maximum_scaling_step_size = 2
    }
  }
}

resource "aws_ecs_cluster_capacity_providers" "slm" {
  cluster_name       = aws_ecs_cluster.slm.name
  capacity_providers = [aws_ecs_capacity_provider.slm.name]
  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = aws_ecs_capacity_provider.slm.name
  }
}

output "fargate_cluster_arn" { value = aws_ecs_cluster.app.arn }
output "slm_cluster_arn" { value = aws_ecs_cluster.slm.arn }
output "slm_asg_arn" { value = aws_autoscaling_group.slm.arn }
output "gpu_instance_type" { value = var.gpu_instance_type }
output "slm_image_uri" { value = var.slm_image_uri }
