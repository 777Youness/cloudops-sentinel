# One public subnet behind an internet gateway (ADR 0016 decision 1). No NAT gateway and no
# VPC endpoints: both are forbidden and billed per hour. VPC, subnet, IGW and route tables
# have no price entry in the AWS Price List (believed free; see docs/cost.md).

resource "aws_vpc" "main" {
  cidr_block           = local.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = local.name }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = { Name = local.name }
}

resource "aws_subnet" "public" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = local.subnet_cidr
  availability_zone = var.availability_zone
  # The instance asks for its public IPv4 address itself (compute.tf); nothing else launched
  # here gets one by accident.
  map_public_ip_on_launch = false

  tags = { Name = "${local.name}-public" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  tags = { Name = "${local.name}-public" }
}

resource "aws_route" "internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.main.id
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# Every VPC comes with a default security group that allows all traffic between its members
# and all egress. Managing it with no rules removes them, so nothing can use it by mistake.
resource "aws_default_security_group" "main" {
  vpc_id = aws_vpc.main.id

  tags = { Name = "${local.name}-default-unused" }
}
