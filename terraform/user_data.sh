#!/bin/bash
# ============================================================
# EC2 User Data Bootstrap Script
# Runs once at instance launch to set up the full stack
# ============================================================
set -euo pipefail

# ── System updates ────────────────────────────────────────────
yum update -y
yum install -y docker git

# ── Docker ────────────────────────────────────────────────────
systemctl enable docker
systemctl start docker
usermod -aG docker ec2-user

# ── Docker Compose v2 ─────────────────────────────────────────
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# ── Clone project ─────────────────────────────────────────────
git clone https://github.com/talib-adnane/news-data-platform.git /opt/news-data-platform
cd /opt/news-data-platform

# ── Write .env file (values injected by Terraform templatefile) ──
cat > .env << EOF
STORAGE_BACKEND=s3
AWS_REGION=${aws_region}
AWS_S3_BUCKET=${s3_bucket}

PG_HOST=${db_host}
PG_PORT=5432
PG_USER=${db_user}
PG_PASSWORD=${db_password}
PG_DB=${db_name}

MINIO_ENDPOINT=
MINIO_ACCESS_KEY=
MINIO_SECRET_KEY=

METABASE_DB_USER=metabase_user
METABASE_DB_PASSWORD=MetabasePwd!2024

KAFKA_BROKER=kafka:29092
KAFKA_TOPIC=news_articles_raw

AIRFLOW_ADMIN_USER=admin
AIRFLOW_ADMIN_PASSWORD=AirflowAdmin!2024
EOF

# ── Start the stack (without MinIO since we use S3) ──────────
docker compose up -d \
  postgres-airflow postgres-metabase postgres-dw \
  zookeeper kafka \
  airflow-init

# Wait for Airflow init to complete
sleep 60

docker compose up -d airflow-webserver airflow-scheduler metabase

echo "Bootstrap complete. Services starting..."
echo "Airflow: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8080"
echo "Metabase: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):3000"
