variable "resource_group_name" { type = string }
variable "location"            { type = string }
variable "environment"         { type = string }
variable "aks_subnet_id"       { type = string }
variable "postgresql_password" {
  type      = string
  sensitive = true
}
variable "huggingface_token" {
  type      = string
  sensitive = true
}
variable "langfuse_secret" {
  type      = string
  sensitive = true
}
variable "tags" { type = map(string) }
variable "allowed_ip" {
  description = "Local IP for Terraform bootstrap access"
  type        = string
  default     = ""
}
