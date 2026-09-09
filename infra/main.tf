# Azure infrastructure for Ricochet.
#
# This file describes **what is deployed**, not a generic example: names, region
# and settings match the stack created by hand in September 2026 (see
# `docs/deploiement_azure.md`, step 5). It is therefore both a definition for
# creating a new environment and an importable description of the existing one —
# see `infra/README.md`.
#
# Three resources, not four: there is **no** dedicated API in front of the
# model. This is "architecture 2" — the Function reads Blob Storage itself. The
# absence of that fourth component is a measured choice, not an omission.

terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
      # `azurerm_function_app_flex_consumption` only exists from v4 onwards.
      version = "~> 4.0"
    }
  }

  # Local state by default: enough for a single-operator project. As soon as a
  # second person applies, the state has to be remote and locked, otherwise two
  # concurrent `apply` runs will tread on each other:
  #
  # backend "azurerm" {
  #   resource_group_name  = "rg-ricochet-tfstate"
  #   storage_account_name = "stricochettfstate"
  #   container_name       = "tfstate"
  #   key                  = "ricochet.tfstate"
  # }
}

provider "azurerm" {
  features {}
}

# ── Resource group ───────────────────────────────────────────────────────────
resource "azurerm_resource_group" "ricochet" {
  name     = var.resource_group_name
  location = var.location

  tags = local.tags
}

# ── Storage account ──────────────────────────────────────────────────────────
# A single account carries everything: the model artifacts (blobs), the
# Function's deployment package, and the registered readers (tables). That is
# what lets Table Storage cost no additional resource.
resource "azurerm_storage_account" "ricochet" {
  name                     = var.storage_account_name
  resource_group_name      = azurerm_resource_group.ricochet.name
  location                 = azurerm_resource_group.ricochet.location
  account_tier             = "Standard"
  account_replication_type = "LRS" # a demonstration: no geo-replication

  # The artifacts are regenerable and contain no personal data, but nothing
  # justifies anonymous access either: the Function authenticates.
  allow_nested_items_to_be_public = false
  min_tls_version                 = "TLS1_2"

  tags = local.tags
}

# Model artifacts: 22 files, about 253 MB, read by the Function.
resource "azurerm_storage_container" "models" {
  name                  = var.models_container_name
  storage_account_id    = azurerm_storage_account.ricochet.id
  container_access_type = "private"
}

# The Function's deployment package. A container **separate** from the
# artifacts: `func azure functionapp publish` writes to it on every deployment,
# and mixing it with the model artifacts would mean a deployment touching the
# same space as the model data.
resource "azurerm_storage_container" "deployments" {
  name                  = "deployments"
  storage_account_id    = azurerm_storage_account.ricochet.id
  container_access_type = "private"
}

# Readers registered in the application, and their reads. Two tables, shaped for
# the only read the application needs: one reader's history is one partition
# (see `src/user_store_azure.py`).
resource "azurerm_storage_table" "clients" {
  name               = "ricochetclients"
  storage_account_id = azurerm_storage_account.ricochet.id
}

resource "azurerm_storage_table" "reads" {
  name               = "ricochetreads"
  storage_account_id = azurerm_storage_account.ricochet.id
}

# ── Plan and Function ────────────────────────────────────────────────────────
# Flex Consumption (`FC1`) rather than Consumption: the Linux Consumption plan
# caps at Python 3.12 and its retirement is announced for 30 September 2028.
# Flex handles Python 3.13, so the local and remote versions coincide.
# One constraint to know: Flex does not exist in every region —
# `az functionapp list-flexconsumption-locations`.
resource "azurerm_service_plan" "ricochet" {
  # The name is a parameter rather than derived from the Function's: Azure
  # assigns one automatically when the Function is created with
  # `az functionapp create` (here `ASP-rgricochet-d9cf`), and a derived name
  # would not match what exists — the import would fail, or would create a
  # duplicate plan.
  name                = var.service_plan_name
  resource_group_name = azurerm_resource_group.ricochet.name
  location            = azurerm_resource_group.ricochet.location
  os_type             = "Linux"
  sku_name            = "FC1"

  tags = local.tags
}

resource "azurerm_function_app_flex_consumption" "ricochet" {
  name                = var.function_app_name
  resource_group_name = azurerm_resource_group.ricochet.name
  location            = azurerm_resource_group.ricochet.location
  service_plan_id     = azurerm_service_plan.ricochet.id

  storage_container_type      = "blobContainer"
  storage_container_endpoint  = "${azurerm_storage_account.ricochet.primary_blob_endpoint}${azurerm_storage_container.deployments.name}"
  storage_authentication_type = "StorageAccountConnectionString"
  storage_access_key          = azurerm_storage_account.ricochet.primary_access_key

  runtime_name    = "python"
  runtime_version = "3.13"

  # 2048 MB: the cold start loads 253 MB of artifacts into memory, plus numpy.
  # 512 MB is not enough.
  instance_memory_in_mb  = 2048
  maximum_instance_count = var.maximum_instance_count

  # The connection string comes from the resource attribute, never from a value
  # written into this file: the secret therefore exists nowhere in clear text.
  # This is a real gain of infrastructure-as-code over the tutorial's `az`
  # commands, where the string travels through the terminal.
  app_settings = {
    AZURE_STORAGE_CONNECTION_STRING = azurerm_storage_account.ricochet.primary_connection_string
    MODELS_CONTAINER                = azurerm_storage_container.models.name
  }

  site_config {}

  tags = local.tags
}

locals {
  tags = {
    project     = "ricochet"
    environment = var.environment
    managed_by  = "terraform"
  }
}
