#!/bin/bash
set -euo pipefail

helm repo add apache-airflow https://airflow.apache.org
helm repo update

helm upgrade --install airflow apache-airflow/airflow \
  --namespace llmops \
  --values infra/k8s/airflow/values.yaml \
  --version 1.13.1 \
  --timeout 20m \
  --wait
