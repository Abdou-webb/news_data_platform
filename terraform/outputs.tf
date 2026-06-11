output "ec2_public_ip" {
  description = "Public IP of the application server."
  value       = aws_instance.app_server.public_ip
}

output "ec2_public_dns" {
  description = "Public DNS of the application server."
  value       = aws_instance.app_server.public_dns
}

output "airflow_url" {
  description = "Airflow web UI URL."
  value       = "http://${aws_instance.app_server.public_dns}:8080"
}

output "metabase_url" {
  description = "Metabase dashboard URL."
  value       = "http://${aws_instance.app_server.public_dns}:3000"
}

output "s3_bucket_name" {
  description = "Name of the S3 data lake bucket."
  value       = aws_s3_bucket.data_lake.bucket
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (internal, accessible from EC2)."
  value       = aws_db_instance.postgres.address
}
