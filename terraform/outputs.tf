# =============================================================================
# outputs.tf — Values printed after `terraform apply`
# =============================================================================

output "public_ip" {
  description = "Public IP of the UmaCore VM"
  value       = azurerm_public_ip.main.ip_address
}

output "ssh_command" {
  description = "SSH command to connect to the VM"
  value       = "ssh ${var.admin_username}@${azurerm_public_ip.main.ip_address}"
}

output "resource_group_name" {
  description = "Azure Resource Group name"
  value       = azurerm_resource_group.main.name
}
