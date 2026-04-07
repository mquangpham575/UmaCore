# =============================================================================
# nsg.tf — Network Security Group for UmaCore VM
#
# The bot only needs outbound internet (Discord API, scraping).
# Inbound is locked to SSH only.
# =============================================================================

resource "azurerm_network_security_group" "main" {
  name                = "${var.project_name}-nsg"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  # ---- SSH (port 22) -------------------------------------------------------
  security_rule {
    name                       = "allow-ssh"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.allowed_ssh_cidr
    destination_address_prefix = "*"
    description                = "SSH access — restrict via allowed_ssh_cidr variable"
  }

  # ---- Deny all inbound ----------------------------------------------------
  security_rule {
    name                       = "deny-all-inbound"
    priority                   = 4096
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
    description                = "Catch-all deny"
  }

  tags = { project = var.project_name }
}

# ---------------------------------------------------------------------------
# Associate NSG with subnet
# ---------------------------------------------------------------------------
resource "azurerm_subnet_network_security_group_association" "main" {
  subnet_id                 = azurerm_subnet.main.id
  network_security_group_id = azurerm_network_security_group.main.id
}
