-- Script d'initialisation de la base de données analytique (Data Warehouse)
-- Cette table est la couche Gold du pipeline Medallion.
-- Elle est aussi créée dans silver_to_gold.py via IF NOT EXISTS (au cas où).

CREATE TABLE IF NOT EXISTS articles_gold (
    id           VARCHAR(255) PRIMARY KEY,
    title        TEXT         NOT NULL,
    author       VARCHAR(255),
    category     VARCHAR(100),
    content      TEXT,
    source       VARCHAR(100),
    url          TEXT,
    date         TIMESTAMP,
    processed_at TIMESTAMP,
    processed_by VARCHAR(100)
);
