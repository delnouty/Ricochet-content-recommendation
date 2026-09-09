# Infrastructure as code — Ricochet on Azure

Three resources describe the whole service: a resource group, a storage account
(artifacts, deployment package, reader tables) and an Azure Function on a Flex
Consumption plan. There is **no** fourth component: no dedicated API in front of
the model. That is "architecture 2", and the absence of that component is a
measured choice (`docs/architecture.md` § 3.a).

## State of this code

> **Not applied to date.** The existing resources were created by hand
> (`docs/deploiement_azure.md`, step 5) *before* these files were written. This
> configuration describes the same stack — same names, same region, same
> settings — but it has never been through `plan` or `apply`: Terraform is not
> installed on the development machine. `terraform validate` does run, in CI.
>
> So it is not yet a source of truth. The two commands that would make it one
> are at the bottom of this page.

## What describing the infrastructure in code buys here

Beyond reproducibility, two concrete gains over the tutorial's `az` commands:

- **The connection string no longer exists in clear text anywhere.** It is read
  as an attribute of the storage resource and injected into the application
  settings. In the tutorial it travels through the terminal and through a
  copy-paste.
- **The region constraint becomes explicit.** Flex Consumption does not exist
  everywhere; the comment on the `location` variable carries the check to
  perform, instead of a failure whose message does not explain the cause.

## Creating a fresh environment

Both global names have to change — they are unique across all of Azure:

```bash
cd infra
terraform init
terraform plan  -var 'storage_account_name=stricochetdev' \
                -var 'function_app_name=func-ricochet-dev' \
                -var 'resource_group_name=rg-ricochet-dev' \
                -var 'environment=dev'
terraform apply -var 'storage_account_name=stricochetdev' \
                -var 'function_app_name=func-ricochet-dev' \
                -var 'resource_group_name=rg-ricochet-dev' \
                -var 'environment=dev'
```

Terraform creates the infrastructure, **not** the content: the artifacts still
have to be uploaded and the code deployed (steps 6 and 8 of the tutorial).

## Adopting the existing stack without recreating it

The default values match the environment already in place. A direct `apply`
would fail, because the names are taken. The resources have to be **imported**
first:

```bash
cd infra
terraform init

SUB=$(az account show --query id -o tsv)
RG="/subscriptions/$SUB/resourceGroups/rg-ricochet"

terraform import azurerm_resource_group.ricochet "$RG"
terraform import azurerm_storage_account.ricochet \
  "$RG/providers/Microsoft.Storage/storageAccounts/stricochetdarya"
terraform import azurerm_service_plan.ricochet \
  "$RG/providers/Microsoft.Web/serverFarms/plan-func-ricochet-darya"
terraform import azurerm_function_app_flex_consumption.ricochet \
  "$RG/providers/Microsoft.Web/sites/func-ricochet-darya"
terraform plan   # must report "No changes" — otherwise the code has drifted
```

The containers and the tables remain. Their import identifier changed when the
provider moved from `storage_account_name` to `storage_account_id`: do not copy
it from memory, take it from the *Import* section of the documentation for the
installed version (`terraform providers`, then the provider page for
`azurerm_storage_container` and `azurerm_storage_table`).

That final `plan` is the only check worth anything: if it proposes changes, this
configuration does not faithfully describe the stack, and it is the code that
needs fixing — not the infrastructure.

Two values were read off the real environment and are now the defaults; neither
would have been guessed correctly:

| Variable | Value | How it was found |
|---|---|---|
| `service_plan_name` | `ASP-rgricochet-d9cf` | `az functionapp create` assigns an automatic name; a name derived from the Function's would have created a duplicate plan |
| `maximum_instance_count` | 100 | the assumed default (40) was wrong |

One divergence is still expected: **the `deployments` container** may not exist —
`func publish` uses the container the Function was given at creation time. Either
read that name off, or let Terraform create the container and reconfigure the
Function.

### Reading the real configuration

⚠️ `az functionapp show --query "{state:state}"` returns **`null`** for an app on
a Flex Consumption plan: the properties live under `functionAppConfig`, which
that path does not traverse. Go through the generic API instead:

```bash
az appservice plan list -g rg-ricochet \
  --query "[].{name:name, sku:sku.name, tier:sku.tier}" -o table

az resource show -g rg-ricochet -n func-ricochet-darya \
  --resource-type "Microsoft.Web/sites" \
  --query "{state:properties.state, runtime:properties.functionAppConfig.runtime, \
            memory:properties.functionAppConfig.scaleAndConcurrency.instanceMemoryMB, \
            maxInstances:properties.functionAppConfig.scaleAndConcurrency.maximumInstanceCount}"
```

Reading of 9 September 2026: `FC1` / `FlexConsumption`, `python 3.13`, 2048 MB
per instance, at most 100 instances, state `Running`.

## Terraform state

The local state (`terraform.tfstate`) **contains the connection string in clear
text**. It is therefore in `.gitignore`, and the secret checker would flag it if
it were ever staged. As soon as a second person applies, the state has to be
remote and locked: the `backend "azurerm"` block is prepared, commented out, in
`main.tf`.

`.terraform.lock.hcl`, by contrast, **is versioned**: it pins the provider
checksums, so that two machines cannot apply with different versions.

## Making this code trustworthy

Exactly two things are missing, in this order:

```bash
winget install --id Hashicorp.Terraform    # not installed on this machine
cd infra && terraform init && terraform validate
az login && terraform plan                  # needs an Azure session
```

Until those commands have run, this directory is a documented **intention**, not
reproducible infrastructure. The distinction is worth stating out loud rather
than leaving a reviewer to discover it.
