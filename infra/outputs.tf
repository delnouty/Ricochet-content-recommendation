output "endpoint" {
  description = "URL of the recommendation endpoint."
  value       = "https://${azurerm_function_app_flex_consumption.ricochet.default_hostname}/api/recommend"
}

output "function_app_name" {
  description = "Function name, for `func azure functionapp publish`."
  value       = azurerm_function_app_flex_consumption.ricochet.name
}

output "storage_account_name" {
  description = "Storage account, for `az storage blob upload-batch`."
  value       = azurerm_storage_account.ricochet.name
}

output "models_container_name" {
  description = "Container the 22 artifacts are uploaded to."
  value       = azurerm_storage_container.models.name
}

# The connection string is a secret: marked `sensitive`, it does not appear in
# the output of `terraform apply`. To read it deliberately:
#   terraform output -raw storage_connection_string
# Remember that it stays in clear text in the state file, which is one reason to
# move to an encrypted remote state as soon as this leaves demonstration.
output "storage_connection_string" {
  description = "Connection string of the storage account (secret)."
  value       = azurerm_storage_account.ricochet.primary_connection_string
  sensitive   = true
}
