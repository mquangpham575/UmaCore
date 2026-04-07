# =============================================================================
# main.tf — Provider, Resource Group, VNet, Subnet
# =============================================================================

# ---------------------------------------------------------------------------
# Remote State — Azure Blob Storage backend
# Pre-requisites (run once):
#   az group create -n tfstate-rg -l "Southeast Asia"
#   az storage account create -n <UNIQUE_NAME> -g tfstate-rg --sku Standard_LRS
#   az storage container create -n tfstate --account-name <UNIQUE_NAME>
# Then update storage_account_name below and run `terraform init`.
# ---------------------------------------------------------------------------
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-umacore-tfstate"
    storage_account_name = "umacoretfstate6zx5iq"
    container_name       = "tfstate"
    key                  = "umacore/terraform.tfstate"
  }
}

# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------
terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
  required_version = ">= 1.3.0"
}

provider "azurerm" {
  skip_provider_registration = true
  features {}
}

# ---------------------------------------------------------------------------
# Resource Group
# ---------------------------------------------------------------------------
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location

  tags = {
    project     = var.project_name
    environment = "production"
    managed_by  = "terraform"
  }
}

# ---------------------------------------------------------------------------
# Virtual Network + Subnet
# ---------------------------------------------------------------------------
resource "azurerm_virtual_network" "main" {
  name                = "${var.project_name}-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  tags = { project = var.project_name }
}

resource "azurerm_subnet" "main" {
  name                 = "${var.project_name}-subnet"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.1.0/24"]
}
