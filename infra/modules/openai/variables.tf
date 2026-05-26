variable "resource_group_name"      { type = string }
variable "location"                 { type = string }
variable "environment"              { type = string }
variable "key_vault_id"             { type = string }
variable "key_vault_access_policy_id" {
  type        = string
  description = "Ensures access policy exists before writing secrets"
}
variable "rag_api_principal_id" {
  type        = string
  description = "Object ID of mi-rag-api-prod managed identity"
}
variable "tags"                     { type = map(string) }