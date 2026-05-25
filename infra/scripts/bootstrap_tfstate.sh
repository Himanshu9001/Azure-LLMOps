#!/bin/bash
set -euo pipefail

SUBSCRIPTION_ID="e56f284c-4b28-4a6a-a473-12e5eaea726e"
RESOURCE_GROUP="rg-llmops-tfstate"
STORAGE_ACCOUNT="llmopshs825412"
CONTAINER="tfstate"
LOCATION="eastus"

az account set --subscription "$SUBSCRIPTION_ID"

echo "Creating tfstate resource group..."
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --tags Project=llmops-doc-qa ManagedBy=bootstrap Environment=shared

echo "Creating tfstate storage account..."
az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --allow-blob-public-access false \
  --min-tls-version TLS1_2 \
  --tags Project=llmops-doc-qa ManagedBy=bootstrap

echo "Enabling versioning and soft delete..."
az storage account blob-service-properties update \
  --account-name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --enable-versioning true \
  --enable-delete-retention true \
  --delete-retention-days 30

echo "Creating tfstate container..."
az storage container create \
  --name "$CONTAINER" \
  --account-name "$STORAGE_ACCOUNT" \
  --auth-mode login

echo "Locking tfstate resource group..."
az group lock create \
  --name "tfstate-delete-lock" \
  --resource-group "$RESOURCE_GROUP" \
  --lock-type CanNotDelete \
  --notes "Terraform state - do not delete"

echo "Done. Backend details:"
echo "  storage_account_name = $STORAGE_ACCOUNT"
echo "  container_name       = $CONTAINER"
echo "  resource_group_name  = $RESOURCE_GROUP"
