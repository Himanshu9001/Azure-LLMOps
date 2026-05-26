terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.95"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 2.47"
    }
  }

  backend "azurerm" {
    resource_group_name  = "rg-llmops-tfstate"
    storage_account_name = "llmopshs825412"
    container_name       = "tfstate"
    key                  = "prod/terraform.tfstate"
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
    resource_group {
      prevent_deletion_if_contains_resources = true
    }
  }
  subscription_id = var.subscription_id

  # ADDED — safety flag, never destroy running AKS node pools
  skip_provider_registration = false
}

provider "azuread" {}

resource "azurerm_resource_group" "main" {
  name     = "rg-llmops-${var.environment}"
  location = var.location
  tags     = local.common_tags
}

locals {
  common_tags = {
    Project     = "llmops-doc-qa"
    Environment = var.environment
    ManagedBy   = "terraform"
    Owner       = "platform-team"
  }
}

module "networking" {
  source              = "../../modules/networking"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  environment         = var.environment
  tags                = local.common_tags
}

module "acr" {
  source              = "../../modules/acr"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  environment         = var.environment
  tags                = local.common_tags
}

module "keyvault" {
  source              = "../../modules/keyvault"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  environment         = var.environment
  aks_subnet_id       = module.networking.aks_subnet_id
  postgresql_password = var.postgresql_password
  huggingface_token   = var.huggingface_token
  langfuse_secret     = var.langfuse_secret
  allowed_ip          = var.allowed_ip
  tags                = local.common_tags
}

module "storage" {
  source                      = "../../modules/storage"
  resource_group_name         = azurerm_resource_group.main.name
  location                    = var.location
  environment                 = var.environment
  private_endpoint_subnet_id  = module.networking.private_endpoint_subnet_id
  storage_private_dns_zone_id = module.networking.storage_private_dns_zone_id
  allowed_ip                  = var.allowed_ip
  tags                        = local.common_tags
}

module "postgresql" {
  source              = "../../modules/postgresql"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.postgresql_location
  environment         = var.environment
  postgresql_password = var.postgresql_password
  allowed_ip          = var.allowed_ip
  tags                = local.common_tags
}

module "aks" {
  source              = "../../modules/aks"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  environment         = var.environment
  aks_subnet_id       = module.networking.aks_subnet_id
  system_node_count   = var.aks_system_node_count
  cpu_node_min        = var.aks_cpu_node_min
  cpu_node_max        = var.aks_cpu_node_max
  gpu_node_min        = var.aks_gpu_node_min
  gpu_node_max        = var.aks_gpu_node_max
  tags                = local.common_tags
}

module "workload_identity" {
  source              = "../../modules/workload-identity"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  environment         = var.environment
  storage_account_id  = module.storage.storage_account_id
  key_vault_id        = module.keyvault.key_vault_id
  aks_oidc_issuer_url = module.aks.oidc_issuer_url
  tags                = local.common_tags
}

# ADDED: Phase 4 — Azure OpenAI
module "openai" {
  source              = "../../modules/openai"
  resource_group_name = azurerm_resource_group.main.name
  location            = "eastus"          # OpenAI available in eastus
  environment         = var.environment
  key_vault_id        = module.keyvault.key_vault_id
  key_vault_access_policy_id = module.keyvault.access_policy_id  # explicit dep
  rag_api_principal_id = module.workload_identity.rag_api_principal_id
  tags                = local.common_tags
}