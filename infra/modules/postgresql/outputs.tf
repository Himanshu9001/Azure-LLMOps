output "fqdn" {
  value     = azurerm_postgresql_flexible_server.main.fqdn
  sensitive = true
}

output "server_name" {
  value = azurerm_postgresql_flexible_server.main.name
}
