# Spécification Fonctionnelle (FS)

| Champ | Valeur |
|-------|--------|
| ID document | MC-FS-001 |
| Version | 0.1 |
| Statut | DRAFT — pour revue AQ |
| Système | My Content — système de recommandation d'articles |
| Date d'émission | 2026-07-20 |

> **Support assistif — à réviser et approuver par l'AQ/CSV avant usage.**

## Tableau d'approbation

| Rôle | Nom | Signature | Date |
|------|-----|-----------|------|
| Auteur (technique) | | | |
| Revue Qualité / AQ | | | |

## 1. Architecture logicielle (rappel)

Cœur de reco `Recommender` (numpy) alimenté par des artefacts pré-calculés
hors-ligne, exposé via deux solutions indépendantes (Azure Function ; Space HF).
Réf. `docs/architecture.md`.

## 2. Spécifications fonctionnelles

| ID | Couvre (URS) | Spécification |
|----|--------------|---------------|
| FS-001 | URS-001, URS-002 | `Recommender.recommend(user_id, n=5, method)` renvoie une liste de `n` `article_id`. Endpoint / interface exposent le paramètre `n` (défaut 5). |
| FS-002 | URS-003 | Méthode `content` : profil = moyenne des embeddings (ACP) des articles lus ; score = similarité cosinus au catalogue ; tri décroissant. |
| FS-003 | URS-004 | Méthode `collab` : score = produit facteurs latents utilisateur × articles (ALS pré-entraîné). |
| FS-004 | URS-005 | Méthode `hybrid` : combinaison min-max normalisée des scores content + collaboratif (pondération `alpha`). Paramètre `method ∈ {content, collab, hybrid}`. |
| FS-005 | URS-006 | En l'absence d'historique exploitable (ou modèle indisponible pour l'utilisateur), repli sur `popular_articles`. |
| FS-006 | URS-007 | Les `article_id` déjà présents dans l'historique de l'utilisateur sont exclus des résultats (score `-inf`, puis filtrage des scores non finis). |
| FS-007 | URS-008 | Un nouvel article disposant d'un embedding (+ ACP) devient recommandable par la voie content-based sans ré-entraînement. |
| FS-008 | URS-009 | Interface Streamlit : sélection d'un `user_id`, déclenchement, affichage des articles recommandés. |
| FS-009 | URS-010 | Solution Azure : `azure_function/function_app.py` expose `GET/POST /api/recommend` ; artefacts lus depuis Blob (`blob_utils.ensure_models`). Solution HF : `spaces/app.py` embarque le `Recommender`, artefacts chargés depuis HF Hub (`model_loader.ensure_models`). |
| FS-010 | URS-011 | Chargement des artefacts effectué une seule fois (mise en cache : `_recommender` global / `st.cache_resource`) ; inférence vectorielle numpy. |
| FS-011 | URS-012, URS-013 | `src/prepare_model.py` produit des artefacts nommés et déterministes (PCA `random_state=42`, ALS `random_state=42`) ; publiés vers Blob et HF Hub. |
| FS-012 | URS-014 | Dépôt Git ; `.gitignore` exclut données brutes, artefacts volumineux et secrets. |
| FS-013 | URS-015 | Évaluation HitRate@5 (leave-last-out) disponible dans le notebook. |
| FS-014 | URS-016 | Ré-entraînement ALS reproductible via `prepare_model.py` ; architecture cible prévoit le suivi de dérive (cf. `docs/architecture.md`). |
| FS-015 | URS-001 | Validation des entrées : `user_id`/`n` entiers ; `method` valide sinon erreur explicite (`ValueError` / HTTP 400). |
| FS-016 | URS-017 | Les entrées sont des identifiants numériques anonymes ; aucune donnée personnelle sensible n'est traitée ni stockée. |

## 3. Interfaces

**API (solution Azure)** — `GET/POST /api/recommend`

| Paramètre | Type | Défaut | Obligatoire |
|-----------|------|--------|-------------|
| `user_id` | int | — | oui |
| `n` | int | 5 | non |
| `method` | str | hybrid | non |

Réponse : `{"user_id", "method", "recommendations": [article_id, …]}` ;
erreurs : HTTP 400 (entrée invalide), 500 (erreur interne).
