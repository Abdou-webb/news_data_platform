variable "aws_region" {
  description = "AWS region to deploy resources into."
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Project name used to prefix all resource names."
  type        = string
  default     = "news-data-platform"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
  default     = "dev"
}

variable "ec2_instance_type" {
  description = "EC2 instance type for the application server."
  type        = string
  default     = "t3.small"
}

variable "key_pair_name" {
  description = "Name of the existing AWS key pair to use for SSH access."
  type        = string
}

variable "db_user" {
  description = "PostgreSQL master username."
  type        = string
  default     = "dw_user"
}

variable "db_password" {
  description = "PostgreSQL master password. Use a strong password in production."
  type        = string
  sensitive   = true
}

variable "allowed_cidr" {
  description = "CIDR allowed to access the EC2 instance (SSH, Airflow UI, Metabase UI). Use your public IP."
  type        = string
  default     = "0.0.0.0/0"  # Restrict this to your IP in production!
}
