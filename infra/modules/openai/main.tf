resource "azurerm_cognitive_account" "openai" {
  name                = "llmops-openai-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location
  kind                = "OpenAI"
  sku_name            = "S0"

  # FIXED: removed network_acls block entirely
  # Cognitive accounts default to public access — restrict in Phase 10
  public_network_access_enabled = true

  tags = var.tags
}

resource "azurerm_cognitive_deployment" "gpt4o" {
  name                 = "gpt-4o-mini"
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = "gpt-4o-mini"
    version = "2024-07-18"
  }

  scale {
    type     = "Standard"
    capacity = 1
  }
}
resource "azurerm_cognitive_deployment" "embedding" {
  name                 = "text-embedding-3-small"
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = "text-embedding-3-small"
    version = "1"
  }

  scale {
    type     = "Standard"
    capacity = 10
  }
}

# Store API key in Key Vault — pods read it via CSI driver
# Never put API keys in deployment yamls or env vars directly
resource "azurerm_key_vault_secret" "openai_key" {
  name         = "azure-openai-key"
  key_vault_id = var.key_vault_id

  # Read key from OpenAI account at apply time
  value = azurerm_cognitive_account.openai.primary_access_key

  lifecycle {
    ignore_changes = [value]   # Don't rotate on every apply
  }

}

# Store endpoint in Key Vault too — cleaner than hardcoding in deployment yaml
resource "azurerm_key_vault_secret" "openai_endpoint" {
  name         = "azure-openai-endpoint"
  key_vault_id = var.key_vault_id
  value        = azurerm_cognitive_account.openai.endpoint

}

# Grant RAG API managed identity access to OpenAI
# rag-api-sa → mi-rag-api-prod → Cognitive Services User role
resource "azurerm_role_assignment" "rag_api_openai" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = var.rag_api_principal_id
}