resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "psql-llmops-${var.environment}"
  resource_group_name           = var.resource_group_name
  location                      = var.location
  version                       = "16"
  administrator_login           = "llmopsadmin"
  administrator_password        = var.postgresql_password
  sku_name                      = var.sku_name
  storage_mb                    = var.storage_mb
  delegated_subnet_id           = var.postgresql_subnet_id
  private_dns_zone_id           = var.postgresql_private_dns_zone_id
  backup_retention_days         = 30
  geo_redundant_backup_enabled  = true

  high_availability {
    mode = "ZoneRedundant"
  }

  tags = var.tags
}

resource "azurerm_postgresql_flexible_server_configuration" "pgvector" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "VECTOR"
}

resource "azurerm_postgresql_flexible_server_database" "mlflow" {
  name      = "mlflow"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "utf8"
}

resource "azurerm_postgresql_flexible_server_database" "vectorstore" {
  name      = "vectorstore"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "utf8"
}
