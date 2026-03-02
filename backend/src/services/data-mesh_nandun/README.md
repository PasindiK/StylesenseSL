# Data Mesh Component for StyleSense SL

This repository contains the Data Mesh backbone for the StyleSense SL project, focused on decentralized, domain-oriented management of fashion-related data. It is designed for hyper-niche fashion discovery and agentic AI-powered personalization.

## Structure Overview

- `domains/` — Contains domain-specific data products (users, products, designers, interactions, trends).
- `governance/` — Data contracts, validation suites, and compliance policies.
- `feature-store/` — Feature definitions for ML and recommendation systems.
- `ml/` — Model code, training, and serving.
- `dashboard/` — Frontend dashboard for monitoring and data product visibility.
- `docs/` — Documentation, onboarding, and guidelines.
- `raw-data/` — Place all raw synthetic data files for initial ingestion and reference.

## Quickstart

1. Place your synthetic data in the appropriate `domains/<domain>/data/` folder.
2. Define schemas and contracts for each domain in their respective folders.
3. Use `transforms/` for ETL scripts and `tests/` for data quality checks.
4. Refer to `governance/` for compliance and validation.
5. Extend with ML models and dashboard as needed.

## Domains
- Users
- Products
- Designers
- Interactions
- Trends

## Governance
- Data contracts
- Validation suites
- PDPA compliance

## Feature Store
- Feature definitions for recommendation

## ML
- Model training and serving

## Dashboard
- Monitoring and analytics UI

## Docs
- Guidelines and onboarding

# Data Mesh Monitoring & AI-Powered Health System

This repository implements a real-time, AI-powered Data Mesh monitoring system for StyleSense SL, following academic and industry best practices.

## Why Domain Health Monitoring is Critical in Data Mesh
- Data Mesh architectures decentralize data ownership, making domain health visibility essential for reliability, trust, and governance.
- Continuous health monitoring (row count, nulls, duplicates, freshness, schema changes) enables proactive detection of issues and supports federated stewardship.

## Simulated Data & Lakehouse Pipeline Behavior
- Health metrics are generated for each domain using real CSVs, with random variations to simulate real-time pipeline changes and ingestion delays.
- Freshness and schema change flags are randomized to mimic dynamic lakehouse environments.
- All snapshots are appended to `lakehouse/monitoring/domain_health_history.csv` to create a time-series view of domain health.

## AI for Trust, Scalability, and Governance
- An Isolation Forest model is trained on health metrics to detect anomalies, supporting unsupervised, scalable anomaly detection across domains.
- ML outputs (anomaly scores, flags) are integrated into the dashboard, providing clear risk levels (Healthy, At Risk, Anomalous) and trend analysis.
- Automated alerting logic logs issues to `lakehouse/monitoring/alerts_log.csv`, enabling rapid response and governance.

## Folder Structure
```
data-mesh/
├── Data_Mesh_Domains/
├── lakehouse/
│   └── monitoring/
│       ├── domain_health_history.csv
│       └── alerts_log.csv
├── models/
│   └── domain_health_iforest.pkl
├── monitoring/
│   ├── snapshot_generator.py
│   ├── train_anomaly_model.py
│   └── predict_anomalies.py
├── dashboard/
│   └── (connect ML outputs here)
└── README.md
```

## How to Use
1. Run `monitoring/snapshot_generator.py` to generate and append domain health snapshots.
2. Run `monitoring/train_anomaly_model.py` to train the Isolation Forest and update anomaly flags.
3. Run `monitoring/predict_anomalies.py` to log alerts for anomalies and freshness violations.
4. Integrate outputs into the dashboard for real-time, AI-powered monitoring.

## Academic Rationale
- Modular, reusable code supports future real-time lakehouse integration.
- No hardcoded domain names; system auto-discovers domains.
- Clear comments and structure for academic evaluation and extension.

For further details, see code comments and scripts in the `monitoring/` folder.

---
For questions, see `docs/` or contact the project maintainer.
