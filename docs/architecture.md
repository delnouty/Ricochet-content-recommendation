# My Content — Note de synthèse (pour Samia)

> Objet : architecture technique & fonctionnelle du MVP de recommandation, et
> architecture cible pour absorber l'arrivée de nouveaux utilisateurs / articles.

---

## 1. Description fonctionnelle (à date)

**User story MVP** : « En tant qu'utilisateur, je reçois une sélection de
5 articles. »

Parcours actuel :

1. L'utilisateur (ou nous, via l'app de démo) choisit un `user_id`.
2. L'application appelle un endpoint HTTP (Azure Function).
3. La Function calcule 5 recommandations et les renvoie.
4. L'app affiche les 5 articles.

## 2. Le système de recommandation

Trois stratégies, exposées via un même service :

| Stratégie | Principe | Force | Limite |
|-----------|----------|-------|--------|
| **Content-based** | Profil utilisateur = moyenne des *embeddings* des articles lus ; cosinus vers le catalogue | Fonctionne dès le 1ᵉʳ clic ; gère un **nouvel article** immédiatement (il a un embedding) | N'exploite pas l'intelligence collective |
| **Collaborative (ALS)** | Factorisation de la matrice utilisateur×article (feedback implicite) | Capte les goûts « latents », effet de surprise | **Cold start** : inefficace pour un nouvel utilisateur/article |
| **Hybride** *(défaut)* | Mélange normalisé des deux scores | Combine les forces, dégrade proprement | Deux modèles à maintenir |

**Cold start** : si l'utilisateur n'a pas d'historique exploitable, on renvoie les
**articles les plus populaires**. C'est le filet de sécurité du MVP.

**Astuce prod (Julien)** : les *embeddings* (250 dim) sont réduits par **ACP**
(~50 dim) hors-ligne pour tenir dans les quotas gratuits Azure.

## 3. Architecture technique retenue — deux solutions indépendantes

Le même cœur de reco (`src/recommender.py`) et les mêmes artefacts alimentent
**deux solutions de déploiement autonomes**, chacune complète en elle-même.

### 3.a — Solution Azure (serverless, « industrialisable »)

Architecture 2 de Julien : *serverless sans API dédiée*, la Function accède
directement aux modèles dans Blob Storage.

```
┌──────────────┐   HTTP GET /recommend?user_id=..   ┌───────────────────────┐
│  App         │ ─────────────────────────────────▶ │   Azure Function       │
│ (Streamlit)  │ ◀───────── 5 article_id ────────── │  (Python, serverless)  │
└──────────────┘                                     │  Recommender (numpy)   │
                                                     └───────────┬───────────┘
                          (démarrage à froid : téléchargement 1x) │
                                                     ┌───────────▼───────────┐
                                                     │  Azure Blob Storage    │
                                                     │  artefacts de modèle   │
                                                     └────────────────────────┘
```

### 3.b — Solution Hugging Face (démo publique, auto-suffisante)

Un Space Streamlit **embarque** le Recommender et calcule les recos sur place ;
il charge les artefacts depuis un dépôt de modèle HF Hub (équivalent HF de Blob
Storage). Aucun appel à Azure : les deux solutions sont indépendantes.

```
┌───────────────────────────────┐   charge   ┌────────────────────────┐
│  HF Space (Streamlit +        │ ─────────▶ │  HF Hub                │
│  Recommender, numpy)          │            │  dépôt de modèle       │
│  calcule les 5 articles       │            │  (artefacts)           │
└───────────────────────────────┘            └────────────────────────┘
```

**Pourquoi deux solutions** : Azure porte l'argument *industrialisable /
serverless* ; Hugging Face porte la *démo publique* facile à partager. Toutes
deux partent des mêmes artefacts produits hors-ligne par `src/prepare_model.py`
(données brutes → ACP + ALS → artefacts). L'inférence ne dépend que de numpy.

### Composants du dépôt

| Dossier | Rôle |
|---------|------|
| `src/` | cœur de reco + préparation des artefacts (source de vérité) |
| `notebooks/` | exploration & comparaison des modèles |
| `azure_function/` | **solution Azure** : service serverless (Archi 2) |
| `app/` | app Streamlit locale appelant l'Azure Function |
| `spaces/` | **solution Hugging Face** : Space Streamlit auto-suffisant |
| `models/` | artefacts générés (poussés vers Blob **et** HF Hub) |

## 4. Architecture cible (nouveaux utilisateurs / nouveaux articles)

Le MVP recalcule tout hors-ligne par lots. À l'échelle, il faut **intégrer les
nouveautés en continu** sans tout recalculer. C'est le point déterminant du
produit : un portail d'actualité publie en permanence, et l'essentiel de son
audience est composé de visiteurs peu ou pas connus.

### 4.a — Ce que coûte chaque nouveauté

| Événement | Ce qu'il faut recalculer | Latence atteignable | Ré-entraînement ? |
|---|---|---|---|
| **Nouvel article** | son embedding, sa projection ACP, ajout au catalogue | minutes | **non** |
| **Nouveau clic** (utilisateur connu) | son profil = moyenne des embeddings lus (calcul à la demande) | temps réel | **non** |
| **Nouvel utilisateur** | rien avant le 1ᵉʳ clic (popularité), profil de contenu ensuite | temps réel | **non** |
| Couverture *collaborative* d'un nouvel utilisateur | ses facteurs latents | heures (fold-in) à un jour (lot) | oui, partiel ou complet |
| Dérive du catalogue (thèmes nouveaux) | ré-ajustement de l'ACP + recalcul de tout le catalogue | planifié (p. ex. mensuel) | oui, complet |

La lecture importante de ce tableau : **seule la partie collaborative impose un
ré-entraînement**. Les deux besoins immédiats (nouvel article visible tout de
suite, nouvel utilisateur servi dès son premier clic) sont couverts par le
content-based, à condition que deux prérequis soient satisfaits — c'est l'objet
des deux sous-sections suivantes.

### 4.b — Prérequis 1 : la projection ACP doit être persistée

Le catalogue est réduit de 250 à 50 dimensions par ACP. Un nouvel article arrive
avec un embedding de 250 dimensions : pour le comparer aux autres, il faut le
placer dans **la même base**. Or une ACP ré-ajustée produit une base *différente* :
tous les vecteurs déjà stockés deviendraient incomparables et devraient être
recalculés (364 k articles), ainsi que tout index construit dessus.

`src/prepare_model.py` sérialise donc la projection elle-même, à côté du
catalogue réduit :

| Artefact | Contenu | Taille |
|---|---|---|
| `articles_embeddings_pca.npy` | catalogue réduit (lu à l'inférence) | ~73 Mo |
| `pca_mean.npy` + `pca_components.npy` | **la projection** (moyenne + axes) | ~51 Ko |

Intégrer un article devient alors une opération locale, sans ré-entraînement. Le
dépôt fournit le chemin complet :

```bash
python scripts/add_articles.py --embeddings nouveaux.npy --dry-run   # contrôle
python scripts/add_articles.py --embeddings nouveaux.npy             # intégration
```

Le script projette les embeddings, les ajoute au catalogue par **écriture
atomique** et affiche les `article_id` attribués (les identifiants sont les
indices de ligne du catalogue). Un garde-fou refuse un ajout déjà effectué
(empreintes de lignes), afin qu'une relance n'introduise pas de doublons.

En bibliothèque, la projection seule :

```python
from src.prepare_model import project_embeddings
vecteur = project_embeddings(embedding_brut, models_dir)   # (1, 50), numpy seul
```

Vérification faite sur le catalogue réel : 3 articles ajoutés reçoivent les
identifiants 364047–364049 et **entrent immédiatement dans le top-5** d'un
utilisateur dont ils sont proches, sans qu'aucun modèle n'ait été ré-entraîné.

Ces 51 Ko sont ce qui distingue « nouvel article intégrable en minutes » de
« nouvel article nécessitant un recalcul complet du catalogue ». La contrepartie
est réelle : la base ACP reste celle du corpus d'origine. Des thématiques
nouvelles y sont donc de moins en moins bien représentées (aujourd'hui 50
composantes = 94,5 % de variance expliquée) — d'où le **ré-ajustement planifié**
de la dernière ligne du tableau 4.a, avec versionnage de l'artefact et bascule
atomique.

### 4.c — Prérequis 2 : les profils sortent des artefacts

Aujourd'hui `user_clicks.pkl` est une **photo d'un lot**, en lecture seule et
chargée en mémoire dans chaque instance. Ce choix ne survit pas à la cible, pour
deux raisons indépendantes : il n'existe aucun chemin d'écriture pour un clic qui
vient d'avoir lieu, et l'historique de tous les utilisateurs ne peut pas résider
dans le processus d'inférence.

En cible, le profil devient une **lecture indexée** dans un store (Cosmos DB ou
Table Storage) : les clics récents d'un utilisateur (une fenêtre de N articles
suffit pour un profil de contenu), écrits par l'ingestion événementielle, lus par
le service de recommandation. Conséquences :

- `user_clicks.pkl` disparaît des artefacts de service ;
- `popular_articles.npy` est recalculé sur **fenêtre glissante** et non sur tout
  l'historique — le repli cold start devient « populaire *en ce moment* », ce qui
  est la seule définition utile pour de l'actualité ;
- les facteurs `cf_*` restent des artefacts versionnés, produits par lot.

### 4.d — Modèle collaboratif : fold-in puis lot

L'ALS n'est pas incrémental *au sens strict*, mais les facteurs d'un utilisateur
peuvent être résolus contre les facteurs articles existants sans tout réapprendre
(`partial_fit_users` de la bibliothèque `implicit`). Cela donne une gradation :

1. **temps réel** — content-based, dès le 1ᵉʳ clic ;
2. **quelques heures** — fold-in ALS : l'utilisateur entre dans le collaboratif
   sans ré-entraînement complet ;
3. **planifié** — ré-entraînement complet, qui recale l'ensemble des facteurs.

Entre deux ré-entraînements, tout utilisateur ou article absent des facteurs
retombe proprement sur le content-based, puis sur la popularité : la dégradation
est explicite et déjà implémentée dans `recommend()`.

### 4.e — Flux cible

```
   Événements de clic ─▶ Event Hub / Queue ─▶ Function (ingestion)
                                                    │
                                                    ▼
                          ┌─────────────────────────────────────┐
                          │  Feature store / base des profils    │
                          │  (Cosmos DB : clics récents par user) │
                          └───────────────────┬───────────────────┘
   Ré-entraînement ALS planifié (batch) ──────┘
   (Azure ML / Function timer)
                                                    │
   Nouvel article ─▶ embedding ─▶ projection ACP persistée ─▶ catalogue (Blob)
                                  (pca_mean + pca_components, cf. 4.b)
                                                    │
                                                    ▼
   API de recommandation dédiée (Archi 1) ◀── modèles + profils à jour
        │  (mise à l'échelle, cache, versionnage des modèles)
        ▼
     Applications clientes
```

### 4.f — Cadences et responsabilités

| Traitement | Déclencheur | Composant | Artefact touché |
|---|---|---|---|
| Projection d'un nouvel article | publication | Function d'ingestion | `articles_embeddings_pca.npy` |
| Écriture d'un clic | événement | Event Hub → Function | store de profils |
| Popularité glissante | horaire | Function timer | `popular_articles.npy` |
| Fold-in ALS | horaire | Function timer | facteurs utilisateurs |
| Ré-entraînement ALS complet | quotidien | Azure ML / lot | `cf_*.npy` versionnés |
| Ré-ajustement ACP | mensuel + surveillance de la variance expliquée | Azure ML / lot | catalogue + projection, versionnés |

Autres décisions de cible :

- **Passage à l'Architecture 1 (API dédiée)** quand le trafic croît : découplage
  application ↔ modèle, mise à l'échelle indépendante, cache, A/B testing et
  **versionnage** des modèles.
- **Génération de candidats** : le MVP score le catalogue entier à chaque appel
  (364 k produits scalaires). En cible, un index de similarité (ANN) restreint à
  quelques centaines de candidats avant le classement.
- **Récence** : pondération par l'âge de l'article, absente du MVP et pourtant
  structurante pour de l'actualité.
- **Suivi** : Application Insights (latence, taux d'erreur) + métriques métier
  (CTR sur les recommandations) pour piloter les itérations.

### 4.g — Ce qui est réellement implémenté à ce stade

Pour éviter toute ambiguïté sur le périmètre du MVP :

| Élément de la cible | État |
|---|---|
| Projection ACP persistée + fonction de projection | **implémenté** (`project_embeddings`, testé) |
| **Intégration d'un nouvel article** (projection + ajout au catalogue) | **implémenté en lot** (`scripts/add_articles.py`, testé) |
| Dégradation collaboratif → contenu → popularité | **implémenté** (`recommend()`) |
| Déclenchement *événementiel* de cette intégration (Event Hub → Function) | conçu, non implémenté |
| Store de profils, écriture des clics | conçu, non implémenté |
| Fold-in ALS, ré-entraînements planifiés | conçu, non implémenté |
| Index ANN, récence, versionnage des modèles | conçu, non implémenté |

Le MVP est un **démonstrateur du moteur de recommandation**, pas un service de
production : il en implémente la fonction de classement et documente la chaîne
qui resterait à construire.

## 5. Limites connues & prochaines étapes

- Évaluation encore basique (HitRate@5 en leave-last-out) → ajouter
  MAP@k / couverture / diversité.
- Pas encore de gestion de la fraîcheur des articles (récence).
- Sécurité : clé de fonction pour le MVP → passer à une vraie auth à terme.
