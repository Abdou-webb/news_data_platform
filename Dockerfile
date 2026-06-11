FROM apache/airflow:2.7.2-python3.11

# Copy pre-downloaded Linux wheels (avoids needing DNS/internet inside the build)
COPY docker_packages/ /tmp/packages/

RUN pip install --no-index --find-links /tmp/packages \
    minio \
    beautifulsoup4 \
    kafka-python \
    psycopg2-binary \
    python-dotenv \
    lxml \
    dbt-postgres \
    boto3
