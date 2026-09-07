# Tutoriel — déployer Ricochet sur Azure, de zéro au service en ligne

Procédure complète et reproductible, écrite à partir d'un déploiement réel. Les
valeurs, durées et erreurs mentionnées ont toutes été observées.

**À l'arrivée** : un service HTTP de recommandation et deux applications qui
l'utilisent.

```
                        ┌──────────────────────────────┐
  app/app_full.py ─────▶│  Azure Function (Python)      │──▶ Blob Storage
  (interface complète)  │  /api/recommend               │    (artefacts du modèle)
  app/streamlit_app.py ▶└──────────────────────────────┘
  (client minimal : preuve de déploiement)
```

Durée totale : **une heure environ**, dont la moitié en attente (construction des
artefacts, téléversement, déploiement).

---

## Étape 0 — Ce qu'il faut avant de commencer

| Élément | Vérification | Si absent |
|---|---|---|
| Compte Azure **avec souscription** | `az account list --all -o table` doit montrer une ligne `Enabled` | <https://azure.microsoft.com/free> (carte bancaire exigée pour la vérification d'identité) |
| Azure CLI | `az version` | `winget install -e --id Microsoft.AzureCLI` |
| Functions Core Tools | `func --version` → `4.x` | `winget install -e --id Microsoft.Azure.FunctionsCoreTools` |
| Python 3.13 | `python --version` | doit correspondre au runtime choisi à l'étape 5 |
| Jeu de données Globo | `data/news-portal-user/clicks/` | voir `data/README.md` |

Après l'installation de Core Tools, **fermer et réouvrir le terminal** : le `PATH`
n'est pas rafraîchi dans une session déjà ouverte. C'est la cause la plus fréquente
d'un `func` introuvable juste après l'installation.

Toutes les commandes se lancent **depuis la racine du dépôt**, sauf mention contraire.

---

## Étape 1 — Construire les artefacts

Le service ne calcule rien à la demande : il lit des artefacts produits hors-ligne.

```powershell
pip install -r requirements.txt

python -m src.prepare_model --data-dir data/news-portal-user --out-dir models
python -m src.collaborative_surprise --data-dir data/news-portal-user --out-dir models
```

Compter environ **dix minutes** : ACP sur 364 047 articles, ALS sur 3 millions de
clics, puis SVD sur 12 millions d'exemples.

Résultat attendu — 22 fichiers, environ 265 Mo :

```powershell
Get-ChildItem models | Measure-Object -Property Length -Sum |
  ForEach-Object { "{0} fichiers, {1:N0} Mo" -f $_.Count, ($_.Sum / 1MB) }
```

Deux paramètres déterminent la qualité du service :

| Paramètre | Défaut | Rôle |
|---|---|---|
| `--window-hours` | 1 | fenêtre du classement par popularité. **Levier principal** : HitRate@5 de 0,2525 sur une heure contre 0,0010 sur tout l'historique |
| `--candidate-hours` | 6 | fenêtre du vivier de candidats des stratégies personnalisées |

---

## Étape 2 — Vérifier en local avant de toucher au cloud

Étape à ne pas sauter : elle sépare les erreurs de modèle des erreurs de déploiement.
Sans elle, un problème dans le cloud est indiscernable d'un problème d'artefacts.

```powershell
python -m pytest tests/ -q                  # 48 tests, aucune donnée requise
python scripts/sync_recommender.py --check   # copies déployées à jour
python scripts/serve_local.py                # service local, port 7071
```

Dans un second terminal :

```powershell
curl "http://127.0.0.1:7071/api/recommend?user_id=0&n=5"
```

**Noter cette réponse.** Elle sert de référence : le service Azure devra renvoyer
exactement la même. C'est le seul contrôle qui détecte des artefacts incomplets côté
cloud.

---

## Étape 3 — Se connecter à Azure

```powershell
az login
```

En cas d'échec :

| Erreur | Cause | Commande |
|---|---|---|
| `AADSTS50076` | authentification multifacteur exigée par le locataire | `az login --tenant <TENANT_ID>` |
| `No subscriptions found` | mauvais locataire, ou souscription absente | choisir le bon locataire, sinon en ouvrir une |
| le navigateur ne s'ouvre pas | environnement sans interface | `az login --tenant <ID> --use-device-code` |

Le message d'erreur d'`az login` **liste les locataires disponibles** avec leurs
identifiants : c'est là qu'on lit le `TENANT_ID`.

Contrôler ensuite :

```powershell
az account list --all --output table
az provider show --namespace Microsoft.Web --query registrationState -o tsv
az provider show --namespace Microsoft.Storage --query registrationState -o tsv
```

Les deux fournisseurs doivent être `Registered`.

---

## Étape 4 — Choisir la région (avant de créer quoi que ce soit)

Le plan **Flex Consumption** est nécessaire ici, et il n'existe pas partout :

```powershell
az functionapp list-flexconsumption-locations --query "[].name" -o tsv
```

Au moment de l'écriture, `francecentral` **n'y figure pas** ; `westeurope` et
`northeurope` oui. Créer les ressources dans une région absente de cette liste fait
échouer l'étape 5, avec un message qui n'explique pas la cause.

**Pourquoi Flex Consumption plutôt que Consumption** : le plan Linux Consumption
plafonne à **Python 3.12** et son retrait est annoncé pour le 30 septembre 2028. Flex
Consumption gère Python 3.13 en disponibilité générale : les versions locale et
distante coïncident, ce qui évite une classe entière de problèmes de dépendances.

---

## Étape 5 — Créer les ressources

Trois ressources, dans cet ordre. Les noms du stockage et de la Function doivent être
**uniques dans tout Azure**, pas seulement dans votre souscription.

```powershell
# 1. groupe de ressources — conteneur logique, gratuit
az group create --name rg-ricochet --location westeurope

# 2. compte de stockage — artefacts du modèle + fichiers de service de la Function
az storage account create `
  --name stricochetdarya `
  --resource-group rg-ricochet `
  --location westeurope `
  --sku Standard_LRS

# 3. la Function (environ une minute)
az functionapp create `
  --resource-group rg-ricochet `
  --name func-ricochet-darya `
  --storage-account stricochetdarya `
  --flexconsumption-location westeurope `
  --runtime python `
  --runtime-version 3.13
```

Contraintes de nommage : le compte de stockage n'accepte que **minuscules et
chiffres**, sans tiret. Le nom de la Function devient le sous-domaine public
(`func-ricochet-darya.azurewebsites.net`).

Vérifier :

```powershell
az functionapp list --resource-group rg-ricochet `
  --query "[].{nom:name, etat:state, hote:defaultHostName}" -o table
```

Configuration obtenue :

| Paramètre | Valeur |
|---|---|
| Plan | `FlexConsumption` |
| Runtime | `python 3.13` |
| Mémoire par instance | 2048 Mo |
| Instances maximum | 100 |
| Instances toujours prêtes | aucune |

---

## Étape 6 — Téléverser les artefacts dans Blob Storage

```powershell
$conn = az storage account show-connection-string --name stricochetdarya `
        --resource-group rg-ricochet --query connectionString -o tsv

az storage container create --name models --connection-string $conn

az storage blob upload-batch --destination models --source models `
  --connection-string $conn --pattern "*.npy" --overwrite
az storage blob upload-batch --destination models --source models `
  --connection-string $conn --pattern "*.pkl" --overwrite
az storage blob upload-batch --destination models --source models `
  --connection-string $conn --pattern "recent_window.json" --overwrite
```

La troisième commande n'est pas facultative : les deux premières ne prennent que
`.npy` et `.pkl`, et sans `recent_window.json` l'interface ne sait plus de quand date
la fenêtre de fraîcheur.

Contrôle — 22 fichiers attendus :

```powershell
az storage blob list --container-name models --connection-string $conn `
  --query "length(@)" -o tsv
```

---

## Étape 7 — Configurer la Function

```powershell
az functionapp config appsettings set `
  --name func-ricochet-darya --resource-group rg-ricochet `
  --settings AZURE_STORAGE_CONNECTION_STRING="$conn" MODELS_CONTAINER=models
```

**Ne jamais définir `MODELS_DIR` en production** : cette variable court-circuite Blob
Storage et sert uniquement au développement local. Présente, elle ferait chercher les
artefacts sur le disque éphémère de l'instance.

---

## Étape 8 — Déployer le code

```powershell
cd azure_function
func azure functionapp publish func-ricochet-darya
cd ..
```

Deux à quatre minutes : empaquetage, puis construction des dépendances
(`azure-functions`, `numpy`, `azure-storage-blob`) côté Azure.

Si la commande échoue sur `Uploading archive... (BadGateway)` — erreur 502 — c'est
transitoire : **relancer**. La version précédente continue de servir entre-temps, il
n'y a pas d'interruption.

---

## Étape 9 — Vérifier le service

L'endpoint est protégé (`AuthLevel.FUNCTION`) : sans clé il répond **401**, ce qui
n'est pas une panne. Récupérer la clé :

```powershell
$key = az functionapp function keys list --name func-ricochet-darya `
       --resource-group rg-ricochet --function-name recommend --query default -o tsv
```

```powershell
curl "https://func-ricochet-darya.azurewebsites.net/api/recommend?user_id=0&n=5&code=$key"
```

**Comparer avec la réponse notée à l'étape 2.** Si elle diffère, le service tourne
avec des artefacts différents — voir l'étape 12.

Contrôles à passer une fois (ajouter `&code=$key` à chacun) :

| Requête | Attendu |
|---|---|
| `?user_id=0&n=5` | 5 identifiants, identiques au local |
| `?user_id=0&method=svd` | classement différent (SVD Surprise) |
| `?user_id=0&fresh_only=0` | **liste différente** — fraîcheur désactivée |
| `?user_id=999999` | cold start : articles récents les plus lus |
| `?user_id=999999&region=25` | liste différente (région croisée avec la fraîcheur) |
| `?user_id=1000000&history=157541,68866` | recommandations personnalisées pour un lecteur **inconnu du service** |
| `?user_id=0` sans `&code` | `401` |
| sans `user_id` | `400` |
| `&method=nope` | `400` |

Pour ouvrir dans un navigateur, faire imprimer l'URL complète — elle contient la clé,
donc ne pas la diffuser ni la montrer à l'écran :

```powershell
"https://func-ricochet-darya.azurewebsites.net/api/recommend?user_id=0&n=5&code=$key"
```

### Paramètres de l'API

| Paramètre | Défaut | Effet |
|---|---|---|
| `user_id` | requis | identifiant du lecteur |
| `n` | 5 | nombre d'articles |
| `method` | `mix` | `mix` \| `content` \| `collab` \| `svd` \| `hybrid` |
| `region` | — | code de région ; n'agit qu'en cold start |
| `fresh_only` | vrai | `0` élargit à tout le catalogue |
| `history` | — | `article_id` séparés par des virgules ; profil transmis par l'appelant, prioritaire sur les artefacts |

`history` rend le service **sans état** : un lecteur créé à l'instant dans
l'application cliente est inconnu du service, mais l'appelant transmet ce qu'il sait
de lui. Sans ce paramètre, un nouveau lecteur ne pourrait recevoir que de la
popularité.

---

## Étape 10 — Lancer les applications

### Application complète — l'interface produit servie par le cloud

```powershell
$env:FUNCTION_URL = "https://func-ricochet-darya.azurewebsites.net/api/recommend"
$env:FUNCTION_KEY = $key
streamlit run app/app_full.py
```

Interface identique à celle de la solution locale — étoiles, catalogue de 364 047
articles, inscription de clients — mais le classement vient du réseau. Elle lit
localement ~36 Mo d'artefacts (étoiles, métadonnées, historiques) pour l'affichage
seulement : ni embeddings, ni facteurs, puisque c'est le service qui calcule.

### Client minimal — preuve de déploiement

```powershell
streamlit run app/streamlit_app.py --server.port 8502
```

Montre la requête, la latence et la réponse brute. C'est ce qu'on ouvre pour démontrer
que le service fonctionne, pas pour montrer le produit.

---

## Étape 11 — Mettre à jour

| Ce qui change | À faire |
|---|---|
| Artefacts (ré-entraînement, nouvelle fenêtre) | refaire l'étape 6, puis `az functionapp restart --name func-ricochet-darya --resource-group rg-ricochet` |
| Code de la Function | refaire l'étape 8 |
| Code partagé (`src/`) | `python scripts/sync_recommender.py` **avant** l'étape 8, sinon les copies déployées restent périmées |

Le redémarrage après un changement d'artefacts est obligatoire : les instances gardent
les fichiers téléchargés en cache local et ne les revérifient pas.

---

## Étape 12 — Erreurs rencontrées, et ce qu'elles signifient

| Symptôme | Cause | Correctif |
|---|---|---|
| `func` introuvable juste après installation | `PATH` non rafraîchi | fermer et réouvrir le terminal |
| `AADSTS50076` | MFA exigée | `az login --tenant <id>` |
| `No subscriptions found` | locataire sans souscription | changer de locataire, ou en ouvrir une |
| `az functionapp create` échoue | région hors Flex Consumption | étape 4 |
| `Uploading archive... (BadGateway)` | 502 transitoire côté Azure | relancer l'étape 8 |
| `401` dans le navigateur | clé absente de l'URL | ajouter `&code=<clé>` |
| `File does not exist: app\streamlit_app.py` | commande lancée depuis un sous-dossier | revenir à la racine du dépôt |
| **Réponses différentes du local, sans aucune erreur** | le chargeur d'artefacts suivait une **liste figée** : les fichiers ajoutés après elle (fraîcheur, étoiles, SVD) n'étaient pas téléchargés | corrigé — le chargeur **énumère** le conteneur ; trois fichiers seulement restent obligatoires, et leur absence lève une erreur explicite |
| Latence de 8 à 9 s par intermittence | démarrage à froid : instance libérée, 265 Mo retéléchargés | normal, voir étape 13 |

La ligne en gras est la plus instructive : **le service répondait correctement, sans
erreur ni avertissement**, tout en servant la popularité de tout l'historique au lieu
de celle de la dernière heure — HitRate@5 de 0,0010 au lieu de 0,2525. Un déploiement
qui « fonctionne » ne prouve pas qu'il sert le bon modèle. Seule la comparaison avec le
service local l'a révélé, d'où l'étape 2.

---

## Étape 13 — Performances et coûts

| Cas | Latence mesurée |
|---|---|
| Instance chaude | 0,13 – 0,26 s |
| Démarrage à froid | jusqu'à 9 s |

Avant une démonstration, « réchauffer » le service par un appel :

```powershell
curl "https://func-ricochet-darya.azurewebsites.net/api/recommend?user_id=0&code=$key"
```

Deux façons de réduire ce délai, chacune avec sa contrepartie :

- **réduire les artefacts à 110 Mo** en excluant `cf_*` et `svd_*` : la stratégie de
  production `mix` ne les utilise pas, mais `collab` et `svd` ne seraient plus
  démontrables par l'API ;
- **configurer une instance `alwaysReady`** : latence prévisible, mais le plan cesse
  d'être gratuit.

Flex Consumption facture à l'exécution, le stockage au volume. Pour tout supprimer :

```powershell
az group delete --name rg-ricochet --yes --no-wait
```

Cette commande détruit le groupe **et tout son contenu**, artefacts publiés compris.

---

## Étape 14 — Adapter à un autre projet

| À adapter | Où |
|---|---|
| Noms des ressources | étape 5 — uniques dans tout Azure |
| Région | étape 4 — vérifier Flex Consumption |
| Version de Python | étape 5, à faire correspondre au local |
| Artefacts obligatoires | `azure_function/shared_code/blob_utils.py`, constante `REQUIRED` |
| Contrat de l'endpoint | `azure_function/function_app.py` |
| Stratégie servie par défaut | `src/recommender.py`, paramètre `method` de `recommend()` |

Trois principes se transposent, quel que soit le modèle déployé :

1. **Séparer le hors-ligne de l'en-ligne.** Tout ce qui est coûteux (ACP,
   entraînements) produit des artefacts ; le service ne fait que lire et classer. Il
   n'embarque donc ni scikit-learn, ni `implicit`, ni Surprise — seulement `numpy`.
2. **Énumérer, ne pas lister.** Une liste d'artefacts codée en dur se périme
   silencieusement ; le chargeur doit découvrir ce qui est publié.
3. **Comparer au local après chaque déploiement.** Un service qui répond n'est pas un
   service qui répond juste.
