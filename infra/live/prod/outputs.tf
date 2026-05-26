output "aks_cluster_name" {
  value = module.aks.cluster_name
}

output "aks_oidc_issuer_url" {
  value = module.aks.oidc_issuer_url
}

output "acr_login_server" {
  value = module.acr.login_server
}

output "storage_account_name" {
  value = module.storage.storage_account_name
}

output "key_vault_uri" {
  value = module.keyvault.vault_uri
}

output "postgresql_fqdn" {
  value     = module.postgresql.fqdn
  sensitive = true
}

output "rag_api_client_id" {
  description = "Annotate rag-api-sa Kubernetes ServiceAccount with this"
  value       = module.workload_identity.rag_api_client_id
}

output "vllm_client_id" {
  description = "Annotate vllm-sa Kubernetes ServiceAccount with this"
  value       = module.workload_identity.vllm_client_id
}

output "openai_endpoint" {
  value = module.openai.openai_endpoint
}