data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "main" {
  name                          = "kv-llmops-${var.environment}"
  resource_group_name           = var.resource_group_name
  location                      = var.location
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  soft_delete_retention_days    = 90
  purge_protection_enabled      = true
  public_network_access_enabled = true

  network_acls {
    default_action             = "Allow"
    bypass                     = "AzureServices"
    virtual_network_subnet_ids = [var.aks_subnet_id]
    ip_rules                   = var.allowed_ip != "" ? [var.allowed_ip] : []
  }

  tags = var.tags
}

resource "azurerm_key_vault_secret" "postgresql_password" {
  name         = "postgresql-password"
  value        = var.postgresql_password
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_key_vault_access_policy.terraform_caller]
  lifecycle {
    ignore_changes = [value]
  }
}

resource "azurerm_key_vault_secret" "huggingface_token" {
  name         = "huggingface-token"
  value        = var.huggingface_token
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_key_vault_access_policy.terraform_caller]
  lifecycle {
    ignore_changes = [value]
  }
}

resource "azurerm_key_vault_secret" "langfuse_secret" {
  name         = "langfuse-secret-key"
  value        = var.langfuse_secret
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_key_vault_access_policy.terraform_caller]
  lifecycle {
    ignore_changes = [value]
  }
}



resource "azurerm_key_vault_access_policy" "terraform_caller" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = data.azurerm_client_config.current.object_id

  secret_permissions = [
    "Get", "Set", "Delete", "List", "Purge", "Recover"
  ]
}
