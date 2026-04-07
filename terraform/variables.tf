# =============================================================================
# variables.tf — Input variables for UmaCore Azure infrastructure
# =============================================================================

variable "project_name" {
  description = "Project name used as prefix for all resource names"
  type        = string
  default     = "umacore"
}

variable "resource_group_name" {
  description = "Name of the Azure Resource Group"
  type        = string
  default     = "rg-umacore"
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "Southeast Asia"
}

variable "vm_size" {
  description = "Azure VM SKU — B2s is 2 vCPU / 4 GB RAM, enough for bot + postgres"
  type        = string
  default     = "Standard_B2s"
}

variable "admin_username" {
  description = "SSH admin user on the VM"
  type        = string
  default     = "umacore"
}

variable "ssh_public_key_path" {
  description = "Path to the SSH public key file (.pub) for VM auth"
  type        = string
  default     = "~/.ssh/umacore_key.pub"
}

variable "allowed_ssh_cidr" {
  description = "CIDR allowed to SSH into the VM. Set to your IP, e.g. '203.0.113.5/32'"
  type        = string
  default     = "0.0.0.0/0"
}
