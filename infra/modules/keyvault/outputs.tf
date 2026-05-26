output "key_vault_id" {
  value = azurerm_key_vault.main.id
}

output "vault_uri" {
  value = azurerm_key_vault.main.vault_uri
}

output "access_policy_id" {
  value = azurerm_key_vault_access_policy.terraform_caller.id
}