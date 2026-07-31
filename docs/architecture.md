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
nouveautés en continu** sans tout recalculer. Proposition d'évolution :

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
   Nouvel article ─▶ calcul embedding + ACP ─▶ ajout au catalogue (Blob)
                                                    │
                                                    ▼
   API de recommandation dédiée (Archi 1) ◀── modèles + profils à jour
        │  (mise à l'échelle, cache, versionnage des modèles)
        ▼
     Applications clientes
```

Décisions clés pour la cible :

- **Nouvel article** → géré nativement par le *content-based* : il suffit de
  calculer son embedding (+ ACP) et de l'ajouter au catalogue. Disponible
  immédiatement, sans ré-entraînement.
- **Nouvel utilisateur** → *content-based* dès le 1ᵉʳ clic ; *popularité* avant.
  Son profil s'enrichit en continu via l'ingestion événementielle.
- **Modèle collaboratif** → ré-entraînement **planifié** (batch) car l'ALS n'est
  pas incrémental ; les nouveaux users/articles absents des facteurs retombent
  proprement sur le content-based/popularité entre deux ré-entraînements.
- **Passage à l'Architecture 1 (API dédiée)** quand le trafic croît : découplage
  application ↔ modèle, mise à l'échelle indépendante, cache, A/B testing et
  **versionnage** des modèles.
- **Suivi** : Application Insights (latence, taux d'erreur) + métriques métier
  (CTR sur les recommandations) pour piloter les itérations.

## 5. Limites connues & prochaines étapes

- Évaluation encore basique (HitRate@5 en leave-last-out) → ajouter
  MAP@k / couverture / diversité.
- Pas encore de gestion de la fraîcheur des articles (récence).
- Sécurité : clé de fonction pour le MVP → passer à une vraie auth à terme.
