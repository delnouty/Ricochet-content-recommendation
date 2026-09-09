# Les valeurs par défaut sont celles de l'environnement existant, pour que
# `terraform plan` sans variables décrive la pile réelle. Pour créer un second
# environnement, il faut changer au moins `storage_account_name` et
# `function_app_name` : ces deux noms sont **uniques dans tout Azure**, pas
# seulement dans la souscription.

variable "resource_group_name" {
  description = "Groupe de ressources"
  type        = string
  default     = "rg-ricochet"
}

variable "location" {
  description = <<-EOT
    Région Azure. Flex Consumption n'est pas disponible partout : au moment de
    l'écriture, `francecentral` n'y figure pas, `westeurope` et `northeurope`
    oui. Vérifier avec `az functionapp list-flexconsumption-locations`, sinon la
    création du plan échoue avec un message qui n'explique pas la cause.
  EOT
  type        = string
  default     = "westeurope"
}

variable "storage_account_name" {
  description = <<-EOT
    Compte de stockage : artefacts du modèle, paquet de déploiement et tables
    des clients. Minuscules et chiffres uniquement, 3 à 24 caractères, unique
    dans tout Azure.
  EOT
  type        = string
  default     = "stricochetdarya"

  validation {
    condition     = can(regex("^[a-z0-9]{3,24}$", var.storage_account_name))
    error_message = "Minuscules et chiffres seulement, 3 à 24 caractères — pas de tiret."
  }
}

variable "function_app_name" {
  description = <<-EOT
    Nom de la Function. Devient le sous-domaine public
    (`<nom>.azurewebsites.net`), donc unique dans tout Azure.
  EOT
  type        = string
  default     = "func-ricochet-darya"
}

variable "models_container_name" {
  description = "Conteneur des artefacts de modèle, lu par la Function."
  type        = string
  default     = "models"
}

variable "maximum_instance_count" {
  description = <<-EOT
    Plafond d'instances simultanées. 40 est le défaut d'Azure ; pour une
    démonstration, une valeur basse borne aussi la facture en cas d'appels
    répétés. Chaque instance retélécharge 253 Mo à son démarrage à froid.
  EOT
  type        = number
  default     = 40

  validation {
    condition     = var.maximum_instance_count >= 1 && var.maximum_instance_count <= 1000
    error_message = "Entre 1 et 1000."
  }
}

variable "environment" {
  description = "Étiquette d'environnement, portée par les tags."
  type        = string
  default     = "mvp"
}
