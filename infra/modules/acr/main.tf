resource "azurerm_container_registry" "main" {
  name                = "acrllmops${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "Premium"
  admin_enabled       = false

  # Geo-replication for pulling images faster from multiple regions
  georeplications {
    location                = "westus2"
    zone_redundancy_enabled = true
  }

  tags = var.tags
}
