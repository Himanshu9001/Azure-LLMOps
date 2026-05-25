resource "azurerm_log_analytics_workspace" "main" {
  name                = "law-llmops-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = var.tags
}

resource "azurerm_user_assigned_identity" "aks_control_plane" {
  name                = "mi-aks-controlplane-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location
}

resource "azurerm_kubernetes_cluster" "main" {
  name                = "aks-llmops-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location
  dns_prefix          = "llmops-${var.environment}"
  

  default_node_pool {
    name                         = "system"
    node_count                   = var.system_node_count
    vm_size                      = "Standard_DC2s_v3"
    vnet_subnet_id               = var.aks_subnet_id
    type                         = "VirtualMachineScaleSets"
    only_critical_addons_enabled = true
    os_disk_size_gb              = 128
    os_disk_type                 = "Managed"

    upgrade_settings {
      max_surge = "33%"
    }
  }

  workload_identity_enabled = true
  oidc_issuer_enabled       = true

  network_profile {
    network_plugin    = "azure"
    network_policy    = "calico"
    load_balancer_sku = "standard"
    outbound_type     = "loadBalancer"
    service_cidr      = "10.3.0.0/16"
    dns_service_ip    = "10.3.0.10"
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.aks_control_plane.id]
  }

  monitor_metrics {}

  oms_agent {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  }

  key_vault_secrets_provider {
    secret_rotation_enabled  = true
    secret_rotation_interval = "2m"
  }

  tags = var.tags
}

resource "azurerm_kubernetes_cluster_node_pool" "cpu" {
  name                  = "cpu"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size               = "Standard_DC4s_v3"
  vnet_subnet_id        = var.aks_subnet_id
  enable_auto_scaling   = true
  min_count             = 0
  max_count             = var.cpu_node_max
  os_disk_size_gb       = 128
  os_disk_type          = "Managed"

  node_labels = {
    "node-type" = "cpu"
    "workload"  = "rag-serving"
  }

  tags = var.tags
}

resource "azurerm_kubernetes_cluster_node_pool" "gpu" {
  name                  = "gpu"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size               = "Standard_NC24ads_A100_v4"
  vnet_subnet_id        = var.aks_subnet_id
  enable_auto_scaling   = true
  min_count             = var.gpu_node_min
  max_count             = var.gpu_node_max
  os_disk_size_gb       = 256
  os_disk_type          = "Managed"

  node_labels = {
    "node-type"      = "gpu"
    "nvidia.com/gpu" = "true"
    "workload"       = "llm"
  }

  node_taints = [
    "nvidia.com/gpu=true:NoSchedule"
  ]

  upgrade_settings {
    max_surge = "1"
  }

  tags = var.tags
}
