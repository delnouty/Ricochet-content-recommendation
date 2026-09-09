# The default values are those of the existing environment, so that a bare
# `terraform plan` describes the real stack. To create a second environment, at
# least `storage_account_name` and `function_app_name` must change: those two
# names are **unique across all of Azure**, not just within the subscription.

variable "resource_group_name" {
  description = "Resource group"
  type        = string
  default     = "rg-ricochet"
}

variable "location" {
  description = <<-EOT
    Azure region. Flex Consumption is not available everywhere: at the time of
    writing `francecentral` is not on the list, `westeurope` and `northeurope`
    are. Check with `az functionapp list-flexconsumption-locations`, otherwise
    creating the plan fails with a message that does not explain the cause.
  EOT
  type        = string
  default     = "westeurope"
}

variable "storage_account_name" {
  description = <<-EOT
    Storage account: model artifacts, deployment package and reader tables.
    Lowercase letters and digits only, 3 to 24 characters, unique across all of
    Azure.
  EOT
  type        = string
  default     = "stricochetdarya"

  validation {
    condition     = can(regex("^[a-z0-9]{3,24}$", var.storage_account_name))
    error_message = "Lowercase letters and digits only, 3 to 24 characters — no hyphen."
  }
}

variable "function_app_name" {
  description = <<-EOT
    Name of the Function. It becomes the public subdomain
    (`<name>.azurewebsites.net`), so it is unique across all of Azure.
  EOT
  type        = string
  default     = "func-ricochet-darya"
}

variable "models_container_name" {
  description = "Container holding the model artifacts, read by the Function."
  type        = string
  default     = "models"
}

variable "service_plan_name" {
  description = <<-EOT
    Plan name. The default is the one **actually in place**: `az functionapp
    create` assigns an automatic name (`ASP-<group>-<suffix>`) instead of the
    name one would have chosen. Read it off before any `terraform import`,
    otherwise the plan will propose creating a second plan alongside the
    existing one:

        az appservice plan list -g rg-ricochet --query "[].name" -o tsv
  EOT
  type        = string
  default     = "ASP-rgricochet-d9cf"
}

variable "maximum_instance_count" {
  description = <<-EOT
    Ceiling on concurrent instances. The default is the one of the environment
    in place, read off with:

        az resource show -g rg-ricochet -n func-ricochet-darya \
          --resource-type "Microsoft.Web/sites" \
          --query properties.functionAppConfig.scaleAndConcurrency

    Every instance re-downloads 253 MB on its cold start, so lowering this value
    also bounds the bill in case of repeated calls.
  EOT
  type        = number
  default     = 100

  validation {
    condition     = var.maximum_instance_count >= 1 && var.maximum_instance_count <= 1000
    error_message = "Between 1 and 1000."
  }
}

variable "environment" {
  description = "Environment label, carried by the tags."
  type        = string
  default     = "mvp"
}
