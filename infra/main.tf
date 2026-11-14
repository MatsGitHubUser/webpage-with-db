terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Settings are passed with -backend-config by the workflow.
  backend "azurerm" {}
}

provider "azurerm" {
  features {}

  # The CI identity only has access to one resource group, so it cannot
  # register providers. scripts/bootstrap-azure.sh registers them instead.
  resource_provider_registrations = "none"
}

# Created by scripts/bootstrap-azure.sh, which also scopes CI access to it.
data "azurerm_resource_group" "main" {
  name = var.resource_group_name
}

# ---------------------------------------------------------------- database
# Kept on stop (the workflow only pauses it), so comments survive.

resource "random_password" "postgres" {
  length      = 32
  special     = false
  min_upper   = 2
  min_lower   = 2
  min_numeric = 2
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                          = var.postgres_server_name
  resource_group_name           = data.azurerm_resource_group.main.name
  location                      = data.azurerm_resource_group.main.location
  version                       = var.postgres_version
  sku_name                      = var.postgres_sku
  storage_mb                    = 32768
  backup_retention_days         = 7
  administrator_login           = "commentsadmin"
  administrator_password        = random_password.postgres.result
  public_network_access_enabled = true

  lifecycle {
    prevent_destroy = true
    # Azure picks the zone; don't try to move the server afterwards.
    ignore_changes = [zone]
  }
}

resource "azurerm_postgresql_flexible_server_database" "comments" {
  name      = "comments"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"

  lifecycle {
    prevent_destroy = true
  }
}

# Lets Azure services (the container app) reach the server. Connections still
# need the password and TLS.
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# ---------------------------------------------------------------- web app

# Kept while stopped: it is free and holds the app's stable domain.
resource "azurerm_container_app_environment" "main" {
  name                = "cae-${var.name}"
  location            = data.azurerm_resource_group.main.location
  resource_group_name = data.azurerm_resource_group.main.name
}

resource "azurerm_container_app" "web" {
  count = var.running ? 1 : 0

  name                         = "ca-${var.name}"
  resource_group_name          = data.azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  secret {
    name  = "pg-password"
    value = random_password.postgres.result
  }

  ingress {
    external_enabled = true
    target_port      = 8501

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = 1

    container {
      name   = "web"
      image  = var.image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "PGHOST"
        value = azurerm_postgresql_flexible_server.main.fqdn
      }
      env {
        name  = "PGUSER"
        value = azurerm_postgresql_flexible_server.main.administrator_login
      }
      env {
        name        = "PGPASSWORD"
        secret_name = "pg-password"
      }
      env {
        name  = "PGDATABASE"
        value = azurerm_postgresql_flexible_server_database.comments.name
      }
      env {
        name  = "PGSSLMODE"
        value = "require"
      }
    }
  }

  depends_on = [azurerm_postgresql_flexible_server_firewall_rule.azure_services]

  lifecycle {
    precondition {
      condition     = var.image != ""
      error_message = "image must be set when running = true."
    }
  }
}
