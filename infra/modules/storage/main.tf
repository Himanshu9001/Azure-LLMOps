resource "azurerm_storage_account" "main" {
  name                            = "stllmops${var.environment}"
  resource_group_name             = var.resource_group_name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "ZRS"
  is_hns_enabled                  = true
  public_network_access_enabled   = true
  allow_nested_items_to_be_public = false

  blob_properties {
    delete_retention_policy {
      days = 30
    }
    container_delete_retention_policy {
      days = 30
    }
  }

  tags = var.tags
}

resource "azurerm_storage_container" "raw_documents" {
  name                  = "raw-documents"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
  depends_on            = [azurerm_storage_account_network_rules.main]
}

resource "azurerm_storage_container" "processed_chunks" {
  name                  = "processed-chunks"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
  depends_on            = [azurerm_storage_account_network_rules.main]
}

resource "azurerm_storage_container" "model_artifacts" {
  name                  = "model-artifacts"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
  depends_on            = [azurerm_storage_account_network_rules.main]
}

resource "azurerm_storage_container" "training_data" {
  name                  = "training-data"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
  depends_on            = [azurerm_storage_account_network_rules.main]
}

resource "azurerm_storage_container" "eval_datasets" {
  name                  = "eval-datasets"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
  depends_on            = [azurerm_storage_account_network_rules.main]
}

resource "azurerm_private_endpoint" "storage" {
  name                = "pe-storage-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "storage-connection"
    private_connection_resource_id = azurerm_storage_account.main.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "storage-dns"
    private_dns_zone_ids = [var.storage_private_dns_zone_id]
  }
}

resource "azurerm_storage_account_network_rules" "main" {
  storage_account_id = azurerm_storage_account.main.id
  default_action     = "Allow"
  bypass             = ["AzureServices"]
  ip_rules           = var.allowed_ip != "" ? [var.allowed_ip] : []
}

locals {
  storage_containers = [
    "raw-documents",
    "processed-chunks",
    "model-artifacts",
    "training-data",
    "eval-datasets"
  ]
}
