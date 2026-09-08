# Spécification Fonctionnelle (FS)

| Champ | Valeur |
|-------|--------|
| ID document | MC-FS-001 |
| Version | 0.2 |
| Statut | DRAFT — pour revue AQ |
| Système | My Content — système de recommandation d'articles |
| Date d'émission | 2026-09-08 |
| Remplace | Version 0.1 du 2026-07-20 |

> **Support assistif — à réviser et approuver par l'AQ/CSV avant usage.**

## Tableau d'approbation

| Rôle | Nom | Signature | Date |
|------|-----|-----------|------|
| Auteur (technique) | | | |
| Revue Qualité / AQ | | | |

## 1. Architecture logicielle (rappel)

Un cœur de recommandation unique, `Recommender` (`src/recommender.py`, **numpy
seul** à l'inférence), alimenté par des artefacts pré-calculés hors-ligne et
exposé par **trois solutions de déploiement indépendantes**. Les copies déployées
du cœur sont **générées** depuis `src/`, jamais éditées à la main.

Aucune bibliothèque d'apprentissage n'est requise à l'inférence : scikit-learn
(ACP), `implicit` (ALS) et `surprise` (SVD) ne servent qu'à la production des
artefacts.

Références : `docs/architecture.md` (statique), `docs/sequences.md` (dynamique —
diagrammes de séquence des trois solutions).

## 2. Spécifications fonctionnelles

| ID | Couvre (URS) | Spécification |
|----|--------------|---------------|
| FS-001 | URS-001, URS-002 | `Recommender.recommend(user_id, n=5, method)` renvoie une liste d'au plus `n` `article_id`, jamais plus, et jamais de doublon. `n` est exposé par l'API et l'interface, défaut **5**, plage 1–10 dans l'interface. |
| FS-002 | URS-003 | Méthode `content` : profil = moyenne des embeddings (réduits par ACP) des articles lus ; score = similarité cosinus au catalogue ; tri décroissant. |
| FS-003 | URS-004 | Méthode `collab` : score = produit des facteurs latents lecteur × article (ALS pré-entraîné, artefacts `cf_*`). |
| FS-004 | URS-005 | Le paramètre `method` sélectionne la stratégie parmi **`mix`, `content`, `collab`, `svd`, `hybrid`**. Valeur par défaut : **`mix`** (stratégie servie en production, cf. FS-017). `hybrid` combine contenu et collaboratif par normalisation min-max. Toute autre valeur est refusée (cf. FS-015). |
| FS-005 | URS-006, URS-019 | **Cascade de repli** pour un lecteur sans profil exploitable, dans cet ordre : (1) popularité de sa région croisée avec la fenêtre de fraîcheur, (2) fenêtre de fraîcheur seule, (3) popularité de sa région seule, (4) popularité sur tout l'historique. Une liste partielle est complétée par le niveau suivant. **Aucune requête ne renvoie de liste vide.** |
| FS-006 | URS-007 | Les `article_id` présents dans l'historique du lecteur sont exclus de tous les résultats (score forcé à `-inf`, puis filtrage des scores non finis). L'exclusion s'applique à toutes les stratégies, y compris aux places de popularité de `mix`. |
| FS-007 | URS-008 | La projection ACP (`pca_mean.npy`, `pca_components.npy`) est **sérialisée avec le catalogue**. Un nouvel article disposant d'un embedding est projeté et ajouté au catalogue, et devient recommandable par la voie contenu **sans ré-ajustement de l'ACP** et sans ré-entraînement. |
| FS-008 | URS-009, URS-018 | Interface Streamlit à trois onglets : **Recommandations** (choix du lecteur, de la stratégie, du nombre d'articles, case de fraîcheur, marquage « Lu »), **Parcourir les articles** (catalogue complet, quatre tris, filtre par note, masquage des articles lus), **Nouveau client** (inscription). Chaque ligne affiche identifiant, note en étoiles, nombre de lecteurs, catégorie, longueur et date. |
| FS-009 | URS-010 | Trois solutions indépendantes : **Azure** — `azure_function/function_app.py`, `GET/POST /api/recommend`, artefacts lus dans Blob Storage ; **Hugging Face** — `spaces/app.py`, Space **SDK Docker**, `Recommender` embarqué, artefacts chargés depuis un dépôt de modèle HF Hub ; **locale** — `local/app.py`, artefacts sur disque, **aucun accès réseau**. |
| FS-010 | URS-011 | Les artefacts sont chargés **une seule fois** par instance (variable globale `_recommender` côté Azure, `st.cache_resource` côté interfaces) puis réutilisés. L'inférence est vectorielle (numpy). |
| FS-011 | URS-012, URS-013 | `src/prepare_model.py` produit des artefacts nommés et déterministes (`random_state=42` pour l'ACP et l'ALS) ; `src/collaborative_surprise.py` produit les artefacts SVD. Les 22 artefacts sont publiés vers Blob Storage et HF Hub. |
| FS-012 | URS-014 | Dépôt Git ; `.gitignore` exclut données brutes, artefacts volumineux et secrets. Les deux relevés de mesure (`models/baseline_metrics.json`, `models/freshness_sweep.json`) sont **explicitement versionnés** : ils servent de référence. |
| FS-013 | URS-015 | **Protocole d'évaluation** : découpage **temporel 60 / 20 / 20** sur l'horodatage des clics. Les réglages sont choisis sur la validation, la période de test ne sert qu'à la mesure finale. Quatre métriques sont produites : HitRate@5, Recall@5, couverture du catalogue, personnalisation. Le vivier de candidats et les modèles collaboratifs sont recalculés à partir de **tout ce qui précède** la période évaluée. Commande : `python -m src.evaluate --split test`. |
| FS-014 | URS-016 | Ré-entraînement reproductible par `prepare_model.py` / `collaborative_surprise.py`. Chaque essai est enregistré dans **MLflow** (paramètres, métriques, commit git) et les artefacts sont versionnés dans le registre de modèles, permettant un retour arrière. |
| FS-015 | URS-001 | Validation des entrées : `user_id` et `n` entiers ; `region` entier ou absent ; `history` liste d'entiers séparés par des virgules ; `method` appartenant à l'ensemble de FS-004. Toute entrée invalide produit une erreur explicite (`ValueError` en interne, **HTTP 400** via l'API) sans interruption du service. |
| FS-016 | URS-017 | Les entrées et sorties sont des **identifiants numériques anonymes**. Aucune donnée personnelle ni sensible n'est traitée ni stockée. Le nom saisi à l'inscription est une étiquette d'affichage, et l'interface avertit de ne pas y saisir de donnée personnelle. |
| **FS-017** | URS-019 | **Stratégie servie en production (`mix`)** : sur cinq places, **quatre** sont attribuées aux articles les plus lus de la **fenêtre d'une heure**, et **une** à la voie contenu choisie dans le **vivier de six heures**. Justification mesurée : la place accordée au contenu ne coûte pas de justesse significative et multiplie par 38 la part de catalogue exposée. |
| **FS-018** | URS-019 | **Artefacts de fraîcheur**, produits par `prepare_model` : `popular_recent.npy` (classement par popularité sur la fenêtre de classement), `candidates_recent.npy` (vivier de candidats sur la fenêtre plus large), `recent_window.json` (métadonnées de la fenêtre : durées demandée et effective, bornes, effectifs). L'ancre temporelle est le **quantile 0,999** des horodatages, afin qu'un horodatage aberrant ne déplace pas la fenêtre. Si la fenêtre contient moins de `min_articles` articles, elle est **élargie automatiquement** et la durée effective est reportée dans les métadonnées. |
| **FS-019** | URS-019 | Le paramètre **`fresh_only`** (défaut **vrai**) restreint toutes les stratégies au vivier récent. Sa désactivation élargit au catalogue entier ; elle est exposée dans l'interface et l'API à des fins de comparaison, et n'est pas la configuration de production. |
| **FS-020** | URS-018 | **Inscription d'un lecteur** : nom obligatoire et unique, **région optionnelle**, profil initial optionnel (articles déjà lus). Les identifiants sont attribués séquentiellement à partir de **1 000 000**, ce qui les distingue sans ambiguïté des lecteurs du jeu de données. Un nom vide ou déjà utilisé est refusé avec un message explicite. Le lecteur inscrit reçoit des recommandations **immédiatement**. |
| **FS-021** | URS-018 | Le paramètre **`history`** de l'API transmet le profil du lecteur dans la requête. Il est **prioritaire** sur les artefacts et permet à un service **sans état** de recommander un lecteur qu'il ne connaît pas. La surcharge est locale à la requête et ne modifie pas l'état partagé du moteur. |
| **FS-022** | URS-022 | **Magasin de clients** : SQLite pour la solution locale ; **Azure Table Storage** dès qu'une chaîne de connexion est disponible (déploiement partagé ou éphémère), avec repli sur SQLite en cas d'indisponibilité, annoncé dans les journaux. Les lectures sont horodatées à la **microseconde**, afin que leur ordre soit préservé. Lorsque la persistance n'est pas assurée (Space Hugging Face sans stockage adossé), l'interface l'affiche en bannière. |
| **FS-023** | URS-020 | **Deux accès à Blob Storage selon la cadence de changement.** Les trois artefacts de fraîcheur (23 Ko) arrivent par ***blob input binding*** et sont relus **à chaque invocation** : une nouvelle fenêtre devient effective sans redémarrage. Les artefacts lourds (253 Mo) sont téléchargés par le **SDK** au démarrage à froid puis mis en cache. Une lecture de binding en échec est journalisée et le moteur **conserve la fenêtre du démarrage** : le service se dégrade, il ne s'interrompt pas. |
| **FS-024** | URS-012, URS-020 | La validité du cache local d'artefacts est jugée sur **la taille *et* la date** du blob. Un artefact reconstruit de taille identique est donc retéléchargé. |
| **FS-025** | URS-021 | **Garde-fou de non-régression** : `scripts/check_metrics.py` compare les métriques d'un entraînement à `models/baseline_metrics.json` et **sort en erreur** si HitRate@5 ou Recall@5 baisse au-delà de la tolérance (défaut 10 %), ce qui bloque la publication dans la CI. La référence n'est mise à jour que délibérément (`--promote`). |
| **FS-026** | URS-010 | Les copies déployées du cœur et de l'interface (`azure_function/`, `spaces/`, `local/`) sont **générées** depuis `src/` par `scripts/sync_recommender.py`. `--check` vérifie qu'elles sont à jour et est exécuté par la CI. |
| **FS-028** | URS-010, URS-011 | **Contraintes d'exécution.** Azure Function : **Python 3.13** sur plan **Flex Consumption** — le plan Linux Consumption plafonne à Python 3.12 et son retrait est annoncé, et Flex Consumption n'est pas disponible dans toutes les régions. Space Hugging Face : image `python:3.13-slim`, conteneur exécuté sous l'UID 1000, application servie sur le port 7860. Environnement local : Python ≥ 3.11. À l'inférence, seules **numpy** et la bibliothèque standard sont requises. |
| **FS-027** | URS-004 | Méthode `svd` : notes **binaires avec négatifs échantillonnés** (4 négatifs par positif), la seule variante qui classe. La variante fondée sur les étoiles de l'article est conservée pour comparaison uniquement : sa note ne dépendant que de l'article, elle ne peut pas classer pour un lecteur donné. |

## 3. Interfaces

### 3.1 API (solution Azure) — `GET/POST /api/recommend`

Paramètres acceptés en chaîne de requête ou dans le corps JSON.

| Paramètre | Type | Défaut | Obligatoire | Rôle |
|-----------|------|--------|-------------|------|
| `user_id` | int | — | **oui** | lecteur à recommander |
| `n` | int | 5 | non | nombre d'articles |
| `method` | str | **`mix`** | non | stratégie (cf. FS-004) |
| `region` | int | — | non | code de région ; n'affecte que le cold start |
| `fresh_only` | bool | **vrai** | non | restreindre aux articles récents (cf. FS-019) |
| `history` | str | — | non | `article_id` séparés par des virgules (cf. FS-021) |
| `code` | str | — | **oui** | clé de fonction (niveau d'autorisation `FUNCTION`) |

Réponse `200` : `{"user_id": int, "method": str, "recommendations": [article_id, …]}`

Erreurs : **400** (paramètre manquant, type invalide, `method` inconnue),
**401** (clé absente ou incorrecte), **500** (erreur interne, journalisée).

### 3.2 Artefacts (contrat de données)

22 fichiers, 253 Mo, produits hors-ligne et publiés vers Blob Storage et HF Hub.

| Groupe | Fichiers | Rôle |
|--------|----------|------|
| Requis pour démarrer | `articles_embeddings_pca.npy`, `user_clicks.pkl`, `popular_articles.npy` | leur absence lève une erreur explicite |
| Fraîcheur | `popular_recent.npy`, `candidates_recent.npy`, `recent_window.json` | cf. FS-018, FS-023 |
| Projection | `pca_mean.npy`, `pca_components.npy` | cf. FS-007 |
| Collaboratif ALS | `cf_user_factors.npy`, `cf_item_factors.npy`, `cf_item_ids.npy`, `cf_user_index.pkl` | cf. FS-003 |
| Collaboratif SVD | `svd_*` (7 fichiers) | cf. FS-027 |
| Affichage et cold start | `article_stars.npy`, `article_clicks.npy`, `popular_by_region.pkl` | notes, effectifs, repli régional |

Les artefacts absents mais optionnels (fraîcheur, régions, étoiles, SVD)
n'empêchent pas le démarrage : la fonction correspondante est simplement
indisponible, et l'interface l'indique.

### 3.3 Magasin de clients

| Table / fichier | Clé | Contenu |
|-----------------|-----|---------|
| `ricochetclients` (Table Storage) | PartitionKey `client`, RowKey `user_id` | nom, date de création, région |
| `ricochetreads` (Table Storage) | PartitionKey `user_id`, RowKey `article_id` | horodatage de lecture |
| `clients.db` (SQLite) | — | équivalent local, même interface |

## 4. Comportement en cas de défaillance

La règle est constante : **se dégrader en le disant, plutôt que s'interrompre.**

| Défaillance | Comportement spécifié |
|-------------|-----------------------|
| Artefacts de fraîcheur illisibles par binding | avertissement journalisé, fenêtre du démarrage conservée (FS-023) |
| Artefact optionnel absent | fonction indisponible, signalée dans l'interface |
| Artefact requis absent | erreur explicite nommant le fichier et la commande de publication |
| Table Storage indisponible | repli sur SQLite, message journalisé (FS-022) |
| Aucune source d'artefacts configurée (Space) | erreur explicite, pas de dépôt deviné |
| Lecteur inconnu, aucun profil | cascade de repli, jamais de liste vide (FS-005) |
| `method` inconnue | HTTP 400 avec le message d'erreur (FS-015) |

## 5. Historique des révisions

| Version | Date | Modifications | Motif |
|---------|------|---------------|-------|
| 0.1 | 2026-07-20 | Émission initiale (FS-001 à FS-016). | — |
| 0.2 | 2026-09-08 | **Corrigés** : FS-004 (ensemble des stratégies et valeur par défaut), FS-005 (cascade à quatre niveaux au lieu d'un repli simple), FS-008 (interface à trois onglets), FS-009 (trois solutions ; SDK Docker pour le Space), FS-013 (protocole d'évaluation : découpage temporel et quatre métriques, en remplacement du *leave-last-out*), FS-014 (MLflow et registre). **Ajoutés** : FS-017 à FS-027. **Ajoutés** : § 3.2 contrat d'artefacts, § 3.3 magasin de clients, § 4 comportement en cas de défaillance. | La v0.1 décrivait un système sans notion de fraîcheur, sans inscription de lecteur et avec un protocole d'évaluation depuis invalidé (le *leave-last-out* sur données complètes surestime la justesse d'un facteur 5,8, mesuré). Elle ne pouvait donc plus servir de base à l'OQ. |

> **Note de méthode.** Les identifiants FS-001 à FS-016 sont conservés : lorsqu'une
> spécification décrivait la même fonction de façon devenue inexacte, elle a été
> corrigée sous son identifiant d'origine. Les fonctions nouvelles reçoivent des
> identifiants neufs. Aucun identifiant n'a été réattribué à une autre fonction.
