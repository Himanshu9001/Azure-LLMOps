resource "azurerm_user_assigned_identity" "rag_api" {
  name                = "mi-rag-api-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location
}

resource "azurerm_user_assigned_identity" "vllm" {
  name                = "mi-vllm-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location
}

resource "azurerm_user_assigned_identity" "fine_tuning" {
  name                = "mi-finetuning-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location
}

resource "azurerm_user_assigned_identity" "ingestion" {
  name                = "mi-ingestion-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location
}

resource "azurerm_role_assignment" "rag_storage_reader" {
  scope                = var.storage_account_id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = azurerm_user_assigned_identity.rag_api.principal_id
}

resource "azurerm_role_assignment" "rag_keyvault_reader" {
  scope                = var.key_vault_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.rag_api.principal_id
}

resource "azurerm_role_assignment" "vllm_storage_reader" {
  scope                = var.storage_account_id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = azurerm_user_assigned_identity.vllm.principal_id
}

resource "azurerm_role_assignment" "finetuning_storage_contributor" {
  scope                = var.storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.fine_tuning.principal_id
}

resource "azurerm_role_assignment" "ingestion_storage_contributor" {
  scope                = var.storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.ingestion.principal_id
}

resource "azurerm_federated_identity_credential" "rag_api" {
  name                = "federated-rag-api"
  resource_group_name = var.resource_group_name
  audience            = ["api://AzureADTokenExchange"]
  issuer              = var.aks_oidc_issuer_url
  parent_id           = azurerm_user_assigned_identity.rag_api.id
  subject             = "system:serviceaccount:llmops:rag-api-sa"
}

resource "azurerm_federated_identity_credential" "vllm" {
  name                = "federated-vllm"
  resource_group_name = var.resource_group_name
  audience            = ["api://AzureADTokenExchange"]
  issuer              = var.aks_oidc_issuer_url
  parent_id           = azurerm_user_assigned_identity.vllm.id
  subject             = "system:serviceaccount:llmops:vllm-sa"
}
