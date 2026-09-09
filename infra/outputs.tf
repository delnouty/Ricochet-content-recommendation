output "endpoint" {
  description = "URL de l'endpoint de recommandation."
  value       = "https://${azurerm_function_app_flex_consumption.ricochet.default_hostname}/api/recommend"
}

output "function_app_name" {
  description = "Nom de la Function, pour `func azure functionapp publish`."
  value       = azurerm_function_app_flex_consumption.ricochet.name
}

output "storage_account_name" {
  description = "Compte de stockage, pour `az storage blob upload-batch`."
  value       = azurerm_storage_account.ricochet.name
}

output "models_container_name" {
  description = "Conteneur où téléverser les 22 artefacts."
  value       = azurerm_storage_container.models.name
}

# La chaîne de connexion est un secret : marquée `sensitive`, elle n'apparaît
# pas dans la sortie de `terraform apply`. Pour la lire délibérément :
#   terraform output -raw storage_connection_string
# Rappel : elle reste en clair dans le fichier d'état, ce qui est une raison de
# passer à un état distant chiffré dès que le projet sort de la démonstration.
output "storage_connection_string" {
  description = "Chaîne de connexion du compte de stockage (secret)."
  value       = azurerm_storage_account.ricochet.primary_connection_string
  sensitive   = true
}
