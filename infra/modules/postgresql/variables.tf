variable "resource_group_name"            { type = string }
variable "location"                       { type = string }
variable "environment"                    { type = string }
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
variable "allowed_ip" {
  description = "Local IP for bootstrap access"
  type        = string
  default     = ""
}
