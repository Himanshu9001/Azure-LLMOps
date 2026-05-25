output "aks_subnet_id" {
  value = azurerm_subnet.aks.id
}

output "private_endpoint_subnet_id" {
  value = azurerm_subnet.private_endpoints.id
}

output "postgresql_private_dns_zone_id" {
  value = azurerm_private_dns_zone.postgres.id
}

output "storage_private_dns_zone_id" {
  value = azurerm_private_dns_zone.storage.id
}

output "vnet_id" {
  value = azurerm_virtual_network.main.id
}

output "postgresql_subnet_id" {
  value = azurerm_subnet.postgresql.id
}
