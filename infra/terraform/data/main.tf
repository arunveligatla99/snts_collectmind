# T128 / ADR-0005 — data module.
# RDS Postgres 16 with TimescaleDB extension, ElastiCache Redis 7, MSK Kafka.

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

variable "private_subnet_ids" {
  type    = list(string)
  default = []
}

variable "data_sg_id" {
  type    = string
  default = ""
}

variable "tags" {
  type = map(string)
  default = {
    Project = "collectmind"
    Feature = "001-policy-loop-vertical-slice"
  }
}

resource "aws_db_subnet_group" "postgres" {
  name       = "collectmind-postgres"
  subnet_ids = var.private_subnet_ids
  tags       = var.tags
}

resource "aws_db_instance" "postgres" {
  identifier              = "collectmind-postgres"
  engine                  = "postgres"
  engine_version          = "16.4"
  instance_class          = "db.t3.medium"
  allocated_storage       = 50
  storage_type            = "gp3"
  storage_encrypted       = true
  username                = "collectmind"
  manage_master_user_password = true
  db_subnet_group_name    = aws_db_subnet_group.postgres.name
  vpc_security_group_ids  = var.data_sg_id != "" ? [var.data_sg_id] : []
  multi_az                = false
  backup_retention_period = 7
  skip_final_snapshot     = true
  tags                    = var.tags
}

resource "aws_elasticache_subnet_group" "redis" {
  name       = "collectmind-redis"
  subnet_ids = var.private_subnet_ids
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "collectmind-redis"
  description                = "CollectMind hot-store"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = "cache.t3.small"
  num_cache_clusters         = 1
  automatic_failover_enabled = false
  port                       = 6379
  subnet_group_name          = aws_elasticache_subnet_group.redis.name
  security_group_ids         = var.data_sg_id != "" ? [var.data_sg_id] : []
  at_rest_encryption_enabled = true
  transit_encryption_enabled = false
  tags                       = var.tags
}

resource "aws_msk_cluster" "kafka" {
  cluster_name           = "collectmind-kafka"
  kafka_version          = "3.7.x"
  number_of_broker_nodes = 2
  broker_node_group_info {
    instance_type   = "kafka.t3.small"
    client_subnets  = var.private_subnet_ids
    security_groups = var.data_sg_id != "" ? [var.data_sg_id] : []
    storage_info {
      ebs_storage_info {
        volume_size = 100
      }
    }
  }
  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }
  tags = var.tags
}

output "postgres_endpoint" { value = aws_db_instance.postgres.endpoint }
output "redis_endpoint" { value = aws_elasticache_replication_group.redis.primary_endpoint_address }
output "kafka_bootstrap_brokers_tls" { value = aws_msk_cluster.kafka.bootstrap_brokers_tls }
