# T128 / ADR-0005 — observability module.
# ADOT collector (CloudWatch + X-Ray) + a managed Grafana workspace.
# Locally the Compose stack runs Tempo / Loki / Prometheus / Grafana; in
# AWS those four are replaced by ADOT + CloudWatch + AMP + AMG.

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

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/collectmind-app"
  retention_in_days = 30
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "slm" {
  name              = "/ecs/collectmind-slm"
  retention_in_days = 30
  tags              = var.tags
}

resource "aws_prometheus_workspace" "main" {
  alias = "collectmind"
  tags  = var.tags
}

resource "aws_grafana_workspace" "main" {
  name                     = "collectmind"
  account_access_type      = "CURRENT_ACCOUNT"
  authentication_providers = ["AWS_SSO"]
  permission_type          = "SERVICE_MANAGED"
  data_sources             = ["PROMETHEUS", "CLOUDWATCH"]
  tags                     = var.tags
}

output "amp_workspace_id" { value = aws_prometheus_workspace.main.id }
output "amg_workspace_id" { value = aws_grafana_workspace.main.id }
output "app_log_group" { value = aws_cloudwatch_log_group.app.name }
output "slm_log_group" { value = aws_cloudwatch_log_group.slm.name }
