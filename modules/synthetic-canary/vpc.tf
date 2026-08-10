# VPC wiring for canaries that need to reach internal endpoints.
#
# Provide vpc_id OR vpc_name, and subnet_ids OR subnet_names. A security group
# is created automatically (all egress) unless security_group_ids is given —
# AWS requires at least one SG in the canary's vpc_config.

data "aws_vpc" "by_id" {
  count = var.vpc_config != null && try(var.vpc_config.vpc_id, null) != null ? 1 : 0
  id    = var.vpc_config.vpc_id
}

data "aws_vpc" "by_name" {
  count = var.vpc_config != null && try(var.vpc_config.vpc_id, null) == null && try(var.vpc_config.vpc_name, null) != null ? 1 : 0

  filter {
    name   = "tag:Name"
    values = [var.vpc_config.vpc_name]
  }
}

data "aws_subnets" "by_name" {
  count = var.vpc_config != null && length(try(var.vpc_config.subnet_names, [])) > 0 ? 1 : 0

  filter {
    name   = "vpc-id"
    values = [local.vpc_id]
  }

  filter {
    name   = "tag:Name"
    values = var.vpc_config.subnet_names
  }
}

resource "aws_security_group" "canary" {
  count       = var.vpc_config != null && length(var.vpc_config.security_group_ids) == 0 ? 1 : 0
  name        = "synth-canary-${var.name}"
  description = "Synthetics canary egress (created by module)"
  vpc_id      = local.vpc_id

  # All egress: within a private subnet this only reaches the VPC CIDR, NAT,
  # and VPC endpoints per the route table. Pass security_group_ids for tighter control.
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

locals {
  vpc_id = var.vpc_config != null ? (
    var.vpc_config.vpc_id != null ? data.aws_vpc.by_id[0].id : data.aws_vpc.by_name[0].id
  ) : null

  subnet_ids = var.vpc_config != null ? (
    length(var.vpc_config.subnet_ids) > 0 ? var.vpc_config.subnet_ids : data.aws_subnets.by_name[0].ids
  ) : null

  security_group_ids = var.vpc_config != null ? (
    length(var.vpc_config.security_group_ids) > 0 ? var.vpc_config.security_group_ids : [aws_security_group.canary[0].id]
  ) : null
}
