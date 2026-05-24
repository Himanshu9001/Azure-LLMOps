variable "subscription_id" {
  description = "Azure Subscription ID"
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "prod"
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "eastus"
}

variable "postgresql_password" {
  description = "PostgreSQL admin password"
  type        = string
  sensitive   = true
}

variable "huggingface_token" {
  description = "HuggingFace API token for model downloads"
  type        = string
  sensitive   = true
}

variable "langfuse_secret" {
  description = "Langfuse secret key for LLM observability"
  type        = string
  sensitive   = true
}

variable "aks_system_node_count" {
  type    = number
  default = 2
}

variable "aks_cpu_node_min" {
  type    = number
  default = 1
}

variable "aks_cpu_node_max" {
  type    = number
  default = 5
}

variable "aks_gpu_node_min" {
  type    = number
  default = 0
}

variable "aks_gpu_node_max" {
  type    = number
  default = 2
}
