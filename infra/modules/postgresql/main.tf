resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "psql-llmops-${var.environment}"
  resource_group_name           = var.resource_group_name
  location                      = var.location
  version                       = "16"
  administrator_login           = "llmopsadmin"
  administrator_password        = var.postgresql_password
  sku_name                      = "B_Standard_B1ms"
  storage_mb                    = var.storage_mb
  backup_retention_days         = 7
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = false



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

resource "azurerm_postgresql_flexible_server_firewall_rule" "terraform_caller" {
  name             = "allow-terraform-caller"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = var.allowed_ip != "" ? var.allowed_ip : "0.0.0.0"
  end_ip_address   = var.allowed_ip != "" ? var.allowed_ip : "255.255.255.255"
}
