# Infrastructure Azure de Ricochet.
#
# Ce fichier décrit **ce qui est déployé**, et non un exemple générique : noms,
# région et réglages correspondent à la pile créée à la main en septembre 2026
# (voir `docs/deploiement_azure.md`, étape 5). Il est donc à la fois une
# définition pour créer un nouvel environnement et une description importable de
# l'environnement existant — voir `infra/README.md`.
#
# Trois ressources, pas quatre : il n'y a **pas** d'API dédiée devant le modèle.
# C'est l'« architecture 2 » — la Function lit Blob Storage elle-même. L'absence
# d'un quatrième composant est un choix, mesuré, pas un oubli.

terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
      # `azurerm_function_app_flex_consumption` n'existe qu'à partir de la v4.
      version = "~> 4.0"
    }
  }

  # État local par défaut : suffisant pour un projet à un seul opérateur. Dès
  # qu'une deuxième personne applique, il faut un état distant et verrouillé,
  # sinon deux `apply` concurrents se marchent dessus :
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

# ── Groupe de ressources ─────────────────────────────────────────────────────
resource "azurerm_resource_group" "ricochet" {
  name     = var.resource_group_name
  location = var.location

  tags = local.tags
}

# ── Compte de stockage ───────────────────────────────────────────────────────
# Un seul compte porte tout : les artefacts du modèle (blobs), le paquet de
# déploiement de la Function, et les clients inscrits (tables). C'est ce qui
# permet à Table Storage de ne coûter aucune ressource supplémentaire.
resource "azurerm_storage_account" "ricochet" {
  name                     = var.storage_account_name
  resource_group_name      = azurerm_resource_group.ricochet.name
  location                 = azurerm_resource_group.ricochet.location
  account_tier             = "Standard"
  account_replication_type = "LRS" # démonstration : pas de réplication géo

  # Les artefacts sont régénérables et ne contiennent aucune donnée personnelle,
  # mais rien ne justifie un accès anonyme : la Function s'authentifie.
  allow_nested_items_to_be_public = false
  min_tls_version                 = "TLS1_2"

  tags = local.tags
}

# Artefacts du modèle : 22 fichiers, ~253 Mo, lus par la Function.
resource "azurerm_storage_container" "models" {
  name                  = var.models_container_name
  storage_account_id    = azurerm_storage_account.ricochet.id
  container_access_type = "private"
}

# Paquet de déploiement de la Function. Conteneur **distinct** des artefacts :
# `func azure functionapp publish` y écrit à chaque déploiement, et le mélanger
# avec les artefacts du modèle ferait qu'un déploiement toucherait au même
# espace que les données du modèle.
resource "azurerm_storage_container" "deployments" {
  name                  = "deployments"
  storage_account_id    = azurerm_storage_account.ricochet.id
  container_access_type = "private"
}

# Clients inscrits dans l'application, et leurs lectures. Deux tables, dessinées
# pour la seule lecture dont l'application a besoin : l'historique d'un lecteur
# est une partition (cf. `src/user_store_azure.py`).
resource "azurerm_storage_table" "clients" {
  name               = "ricochetclients"
  storage_account_id = azurerm_storage_account.ricochet.id
}

resource "azurerm_storage_table" "reads" {
  name               = "ricochetreads"
  storage_account_id = azurerm_storage_account.ricochet.id
}

# ── Plan et Function ─────────────────────────────────────────────────────────
# Flex Consumption (`FC1`) et non Consumption : le plan Linux Consumption
# plafonne à Python 3.12 et son retrait est annoncé pour le 30 septembre 2028.
# Flex gère Python 3.13, donc les versions locale et distante coïncident.
# Contrainte à connaître : Flex n'existe pas dans toutes les régions —
# `az functionapp list-flexconsumption-locations`.
resource "azurerm_service_plan" "ricochet" {
  # Nom paramétré, et non déduit de celui de la Function : Azure en attribue un
  # automatiquement lorsqu'on crée la Function avec `az functionapp create`
  # (ici `ASP-rgricochet-d9cf`), et un nom déduit ne correspondrait pas à
  # l'existant — l'import échouerait ou créerait un plan en double.
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

  # 2 048 Mo : le démarrage à froid charge 253 Mo d'artefacts en mémoire, plus
  # numpy. 512 Mo ne suffisent pas.
  instance_memory_in_mb  = 2048
  maximum_instance_count = var.maximum_instance_count

  # La chaîne de connexion vient de l'attribut de la ressource, jamais d'une
  # valeur écrite dans ce fichier : le secret n'existe donc nulle part en clair.
  # C'est un gain réel de l'infrastructure décrite en code sur les commandes
  # `az` du tutoriel, où la chaîne circule dans le terminal.
  app_settings = {
    AZURE_STORAGE_CONNECTION_STRING = azurerm_storage_account.ricochet.primary_connection_string
    MODELS_CONTAINER                = azurerm_storage_container.models.name
  }

  site_config {}

  tags = local.tags
}

locals {
  tags = {
    projet      = "ricochet"
    environment = var.environment
    gere_par    = "terraform"
  }
}
