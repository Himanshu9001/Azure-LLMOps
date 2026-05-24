variable "resource_group_name"            { type = string }
variable "location"                       { type = string }
variable "environment"                    { type = string }
variable "postgresql_subnet_id"           { type = string }
variable "postgresql_private_dns_zone_id" { type = string }
variable "sku_name" {
  type    = string
  default = "GP_Standard_D2s_v3"
}
variable "storage_mb" {
  type    = number
  default = 32768
}
variable "postgresql_password" {
  type      = string
  sensitive = true
}
variable "tags" { type = map(string) }
