terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# S3 — data lake bucket (replaces MinIO in production)
# Bronze, Silver, and Gold prefixes live inside this single bucket.
resource "aws_s3_bucket" "data_lake" {
  bucket = "${var.project_name}-data-lake-${random_id.suffix.hex}"

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "random_id" "suffix" {
  byte_length = 4
}

# RDS PostgreSQL — Gold layer data warehouse
# db.t3.micro is free-tier eligible for the first 12 months.
resource "aws_db_instance" "postgres" {
  identifier        = "${var.project_name}-dw"
  engine            = "postgres"
  engine_version    = "15"
  instance_class    = "db.t3.micro"
  allocated_storage = 20

  db_name  = "datawarehouse"
  username = var.db_user
  password = var.db_password

  publicly_accessible    = false
  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name

  skip_final_snapshot = true

  tags = {
    Project   = var.project_name
    ManagedBy = "terraform"
  }
}

# EC2 — runs the full Docker Compose stack (Airflow + Metabase + Kafka)
# t3.small gives 2 vCPU / 2 GB RAM which is enough for a demo workload.
resource "aws_instance" "app_server" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.ec2_instance_type
  key_name               = var.key_pair_name
  vpc_security_group_ids = [aws_security_group.ec2.id]
  subnet_id              = aws_subnet.public.id
  iam_instance_profile   = aws_iam_instance_profile.ec2_s3.name

  user_data = templatefile("${path.module}/user_data.sh", {
    db_host     = aws_db_instance.postgres.address
    db_user     = var.db_user
    db_password = var.db_password
    db_name     = "datawarehouse"
    s3_bucket   = aws_s3_bucket.data_lake.bucket
    aws_region  = var.aws_region
  })

  tags = {
    Name      = "${var.project_name}-app-server"
    Project   = var.project_name
    ManagedBy = "terraform"
  }
}

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

# IAM — lets EC2 read/write S3 without hardcoded credentials
resource "aws_iam_role" "ec2_s3" {
  name = "${var.project_name}-ec2-s3-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "ec2_s3_access" {
  name = "s3-data-lake-access"
  role = aws_iam_role.ec2_s3.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:CopyObject"]
      Resource = [
        aws_s3_bucket.data_lake.arn,
        "${aws_s3_bucket.data_lake.arn}/*"
      ]
    }]
  })
}

resource "aws_iam_instance_profile" "ec2_s3" {
  name = "${var.project_name}-ec2-profile"
  role = aws_iam_role.ec2_s3.name
}

# Networking
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  tags = { Name = "${var.project_name}-vpc" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true
  availability_zone       = "${var.aws_region}a"
  tags = { Name = "${var.project_name}-public" }
}

resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "${var.aws_region}b"
  tags = { Name = "${var.project_name}-private" }
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = [aws_subnet.public.id, aws_subnet.private.id]
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# EC2 security group — SSH + Airflow (8080) + Metabase (3000)
resource "aws_security_group" "ec2" {
  name   = "${var.project_name}-ec2-sg"
  vpc_id = aws_vpc.main.id

  ingress {
    description = "SSH"
    from_port = 22; to_port = 22; protocol = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }
  ingress {
    description = "Airflow UI"
    from_port = 8080; to_port = 8080; protocol = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }
  ingress {
    description = "Metabase UI"
    from_port = 3000; to_port = 3000; protocol = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }
  egress {
    from_port = 0; to_port = 0; protocol = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# RDS security group — only reachable from the EC2 instance
resource "aws_security_group" "rds" {
  name   = "${var.project_name}-rds-sg"
  vpc_id = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from EC2"
    from_port = 5432; to_port = 5432; protocol = "tcp"
    security_groups = [aws_security_group.ec2.id]
  }
}
