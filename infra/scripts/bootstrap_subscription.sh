#!/bin/bash
set -euo pipefail

SUBSCRIPTION_ID="e56f284c-4b28-4a6a-a473-12e5eaea726e"

az account set --subscription "$SUBSCRIPTION_ID"

PROVIDERS=(
  "Microsoft.Storage"
  "Microsoft.ContainerService"
  "Microsoft.KeyVault"
  "Microsoft.DBforPostgreSQL"
  "Microsoft.ContainerRegistry"
  "Microsoft.Network"
  "Microsoft.Compute"
  "Microsoft.ManagedIdentity"
  "Microsoft.EventGrid"
  "Microsoft.Monitor"
  "Microsoft.OperationalInsights"
  "Microsoft.OperationsManagement"
)

for PROVIDER in "${PROVIDERS[@]}"; do
  echo "Registering $PROVIDER..."
  az provider register --namespace "$PROVIDER" --wait
  echo "$PROVIDER registered."
done

az provider list \
  --query "[?namespace=='Microsoft.Storage' || namespace=='Microsoft.ContainerService' || namespace=='Microsoft.KeyVault' || namespace=='Microsoft.DBforPostgreSQL' || namespace=='Microsoft.ContainerRegistry'].{Provider:namespace, State:registrationState}" \
  --output table

echo "Bootstrap complete."
