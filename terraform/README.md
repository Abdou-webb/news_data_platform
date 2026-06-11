# Deploying to AWS with Terraform

This guide walks you through deploying the full News Data Platform stack
to AWS using Terraform. The entire infrastructure is provisioned in ~10 minutes.

## Resources Created

| Resource | Type | Cost (approx.) |
|---|---|---|
| S3 Bucket | Data lake (Bronze/Silver/Gold) | ~$0.02/GB/month |
| RDS PostgreSQL | `db.t3.micro` — Free Tier eligible | $0 for 12 months |
| EC2 Instance | `t3.small` (Airflow + Metabase) | ~$15/month |
| IAM Role | EC2 → S3 access (no credentials needed) | Free |
| VPC + Security Groups | Networking | Free |

> **Total estimated cost: ~$15/month** (or free for 12 months with AWS Free Tier on a new account)

---

## Prerequisites

1. [Terraform](https://developer.hashicorp.com/terraform/install) ≥ 1.5 installed
2. [AWS CLI](https://aws.amazon.com/cli/) configured (`aws configure`)
3. An existing **EC2 Key Pair** in your target region (for SSH access)
4. The project pushed to a **public GitHub repository**

---

## Step 1 — Update the GitHub URL in user_data.sh

Edit [`user_data.sh`](user_data.sh) and replace the placeholder with your repo:

```bash
git clone https://github.com/YOUR-USERNAME/news-data-platform.git /opt/news-data-platform
```

---

## Step 2 — Create a terraform.tfvars file

```bash
cd terraform/
cat > terraform.tfvars << EOF
aws_region        = "eu-west-1"
key_pair_name     = "your-key-pair-name"
db_password       = "YourStrongPassword123!"
allowed_cidr      = "YOUR.PUBLIC.IP.ADDRESS/32"
EOF
```

> ⚠️ `terraform.tfvars` is in `.gitignore` — it will never be committed.

---

## Step 3 — Deploy

```bash
terraform init      # download AWS provider
terraform plan      # preview resources to create
terraform apply     # provision (takes ~8-10 minutes)
```

After `terraform apply` finishes, you'll see the output URLs:

```
airflow_url  = "http://ec2-xx-xx-xx-xx.eu-west-1.compute.amazonaws.com:8080"
metabase_url = "http://ec2-xx-xx-xx-xx.eu-west-1.compute.amazonaws.com:3000"
s3_bucket    = "news-data-platform-data-lake-a1b2c3d4"
```

---

## Step 4 — Wait for services to start

The EC2 instance runs a bootstrap script that installs Docker and starts the
stack. Allow **5-10 minutes** after `terraform apply` before accessing the UIs.

Monitor progress via SSH:
```bash
ssh -i ~/.ssh/your-key.pem ec2-user@<EC2_PUBLIC_IP>
tail -f /var/log/cloud-init-output.log
```

---

## Step 5 — Run the pipeline

1. Open **Airflow** at the URL shown in Terraform output
2. Login: `admin` / `AirflowAdmin!2024`
3. Enable `news_pipeline_dag` → **Trigger DAG**

Data flows to **S3** (Bronze → Silver) then **RDS PostgreSQL** (Gold).

---

## Tear Down

```bash
terraform destroy   # removes ALL resources — stops billing immediately
```

---

## Architecture on AWS

```
Internet → EC2 (t3.small)
               ├── Airflow (port 8080)
               ├── Metabase (port 3000)
               ├── Kafka + Zookeeper
               └── PostgreSQL (Airflow metadata + Metabase)
                       │
                       ├── S3 (Bronze / Silver / Gold buckets)
                       │   via IAM Role — no credentials in code
                       │
                       └── RDS PostgreSQL (db.t3.micro)
                           Data Warehouse — Gold Layer
```
