output "rag_api_client_id" {
  value = azurerm_user_assigned_identity.rag_api.client_id
}

output "vllm_client_id" {
  value = azurerm_user_assigned_identity.vllm.client_id
}

output "fine_tuning_client_id" {
  value = azurerm_user_assigned_identity.fine_tuning.client_id
}

output "ingestion_client_id" {
  value = azurerm_user_assigned_identity.ingestion.client_id
}

output "rag_api_principal_id" {
  value = azurerm_user_assigned_identity.rag_api.principal_id
}
