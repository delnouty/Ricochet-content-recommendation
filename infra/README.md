# Infrastructure as code — Ricochet sur Azure

Trois ressources décrivent tout le service : un groupe de ressources, un compte
de stockage (artefacts, paquet de déploiement, tables des clients) et une
Azure Function sur plan Flex Consumption. Il n'y a **pas** de quatrième
composant : pas d'API dédiée devant le modèle. C'est l'« architecture 2 », et
l'absence de ce composant est un choix mesuré (`docs/architecture.md` § 3.a).

## État de ce code

> **Non appliqué à ce jour.** Les ressources existantes ont été créées à la main
> (`docs/deploiement_azure.md`, étape 5) *avant* l'écriture de ces fichiers.
> Cette configuration décrit la même pile — mêmes noms, même région, mêmes
> réglages — mais elle n'a été ni `validate`, ni `plan`, ni `apply` : Terraform
> n'est pas installé sur le poste de développement.
>
> Elle n'est donc pas encore une source de vérité. Les deux commandes qui la
> rendraient telle sont en bas de page.

## Ce que l'infrastructure décrite en code apporte ici

Au-delà de la reproductibilité, deux gains concrets sur les commandes `az` du
tutoriel :

- **La chaîne de connexion n'existe plus en clair nulle part.** Elle est lue
  comme attribut de la ressource de stockage et injectée dans les réglages de
  l'application. Dans le tutoriel, elle transite par le terminal et par un
  copier-coller.
- **La contrainte de région devient explicite.** Flex Consumption n'existe pas
  partout ; le commentaire de la variable `location` porte la vérification à
  faire, au lieu d'un échec dont le message n'explique pas la cause.

## Créer un environnement neuf

Les deux noms globaux doivent changer — ils sont uniques dans tout Azure :

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

Terraform crée l'infrastructure, **pas** le contenu : il reste à téléverser les
artefacts et à déployer le code (étapes 6 et 8 du tutoriel).

## Adopter la pile existante, sans la recréer

Les valeurs par défaut correspondent à l'environnement en place. Un `apply`
direct échouerait — les noms sont déjà pris. Il faut d'abord **importer** :

```bash
cd infra
terraform init

SOUS=$(az account show --query id -o tsv)
RG="/subscriptions/$SOUS/resourceGroups/rg-ricochet"

terraform import azurerm_resource_group.ricochet "$RG"
terraform import azurerm_storage_account.ricochet \
  "$RG/providers/Microsoft.Storage/storageAccounts/stricochetdarya"
terraform import azurerm_service_plan.ricochet \
  "$RG/providers/Microsoft.Web/serverFarms/plan-func-ricochet-darya"
terraform import azurerm_function_app_flex_consumption.ricochet \
  "$RG/providers/Microsoft.Web/sites/func-ricochet-darya"
terraform plan   # doit annoncer « No changes » — sinon le code diverge du réel
```

Restent les conteneurs et les tables. Leur identifiant d'import a changé quand
le fournisseur est passé de `storage_account_name` à `storage_account_id` : ne
pas le recopier de mémoire, le relever dans la section *Import* de la
documentation de la version installée
(`terraform providers`, puis la page du fournisseur pour
`azurerm_storage_container` et `azurerm_storage_table`).

Ce dernier `plan` est le seul contrôle qui vaille : s'il propose des
modifications, c'est que cette configuration ne décrit pas fidèlement la pile,
et il faut corriger le code — pas l'infrastructure.

Deux écarts sont attendus, et normaux :

- **le nom du plan.** Créé par `az functionapp create`, il porte un nom
  attribué automatiquement, probablement différent de `plan-func-ricochet-darya`.
  Relever le vrai nom (`az functionapp show --query appServicePlanId`) et
  ajuster la ressource avant d'importer.
- **le conteneur `deployments`.** Il n'existe peut-être pas : `func publish`
  utilise le conteneur que la Function a reçu à sa création. Le relever, ou
  laisser Terraform le créer et reconfigurer la Function.

## État Terraform

L'état local (`terraform.tfstate`) **contient la chaîne de connexion en clair**.
Il est donc dans `.gitignore`, et le vérificateur de secrets le signalerait s'il
était indexé. Dès qu'une deuxième personne applique, il faut un état distant et
verrouillé : le bloc `backend "azurerm"` est préparé, en commentaire, dans
`main.tf`.

`.terraform.lock.hcl` est **versionné** au contraire : il épingle les empreintes
des fournisseurs, pour que deux machines n'appliquent pas avec des versions
différentes.

## Rendre ce code fiable

Il manque exactement deux choses, dans cet ordre :

```bash
winget install --id Hashicorp.Terraform    # non installé sur le poste
cd infra && terraform init && terraform validate
az login && terraform plan                  # nécessite une session Azure
```

Tant que ces commandes n'ont pas tourné, ce dossier est une **intention**
documentée, pas une infrastructure reproductible. La distinction mérite d'être
faite à l'oral plutôt que découverte par un relecteur.
