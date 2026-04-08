# =============================================================================
# vm.tf — Public IP, NIC, and Linux VM for UmaCore bot
# =============================================================================

# ---------------------------------------------------------------------------
# cloud-init — installs Docker + Docker Compose on first boot
# ---------------------------------------------------------------------------
locals {
  cloud_init_script = base64encode(<<-CLOUDINIT
    #cloud-config
    package_update: true
    package_upgrade: false

    packages:
      - apt-transport-https
      - ca-certificates
      - curl
      - gnupg
      - lsb-release

    runcmd:
      # ---- Docker official apt repo ----
      - install -m 0755 -d /etc/apt/keyrings
      - curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
      - chmod a+r /etc/apt/keyrings/docker.asc
      - echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
      - apt-get update -qq
      - apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
      # ---- Post-install ----
      - systemctl enable docker
      - systemctl start docker
      - usermod -aG docker ${var.admin_username}
      # ---- Setup Swap (2GB) ----
      - fallocate -l 2G /swapfile
      - chmod 600 /swapfile
      - mkswap /swapfile
      - swapon /swapfile
      - echo '/swapfile none swap sw 0 0' | tee -a /etc/fstab
      # ---- Create app directory ----
      - mkdir -p /opt/umacore
      - chown ${var.admin_username}:${var.admin_username} /opt/umacore

    final_message: "umacore VM ready after $UPTIME seconds"
  CLOUDINIT
  )
}

# ---------------------------------------------------------------------------
# Public IP — static so it survives stop/start
# ---------------------------------------------------------------------------
resource "azurerm_public_ip" "main" {
  name                = "${var.project_name}-pip"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = { project = var.project_name }
}

# ---------------------------------------------------------------------------
# Network Interface
# ---------------------------------------------------------------------------
resource "azurerm_network_interface" "main" {
  name                = "${var.project_name}-nic"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.main.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.main.id
  }

  tags = { project = var.project_name }
}

# ---------------------------------------------------------------------------
# Associate NIC with NSG
# ---------------------------------------------------------------------------
resource "azurerm_network_interface_security_group_association" "main" {
  network_interface_id      = azurerm_network_interface.main.id
  network_security_group_id = azurerm_network_security_group.main.id
}

# ---------------------------------------------------------------------------
# Linux VM — Ubuntu 22.04 LTS (x86_64)
# ---------------------------------------------------------------------------
resource "azurerm_linux_virtual_machine" "main" {
  name                = "${var.project_name}-vm"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  size                = var.vm_size

  admin_username                  = var.admin_username
  disable_password_authentication = true

  admin_ssh_key {
    username   = var.admin_username
    public_key = file(var.ssh_public_key_path)
  }

  network_interface_ids = [azurerm_network_interface.main.id]

  os_disk {
    name                 = "${var.project_name}-osdisk"
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-arm64"
    version   = "latest"
  }

  custom_data = local.cloud_init_script

  tags = {
    project = var.project_name
    role    = "discord-bot"
  }
}
