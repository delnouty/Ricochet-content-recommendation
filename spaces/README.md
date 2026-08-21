---
title: Ricochet - Recommandation d'articles
emoji: 🎯
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.60.0
app_file: app.py
pinned: false
---

# Ricochet — démonstration publique (Hugging Face Space)

Solution **autonome**, indépendante de la solution Azure : l'application embarque le
moteur de recommandation et calcule elle-même les suggestions. Les artefacts sont
téléchargés au démarrage depuis un **dépôt de modèle HF Hub**.

```
HF Space (Streamlit + Recommender)  ──charge──▶  HF Hub (dépôt de modèle)
        calcule les recommandations sur place
```

L'interface est **la même que la solution locale** : elle vient de `ui.py`, copie
générée depuis `src/app_ui.py` par `scripts/sync_recommender.py`. Les deux solutions
ne peuvent donc pas diverger, et la CI le vérifie (`--check`).

## Ce que la démo expose

| Onglet | Contenu |
|---|---|
| Recommandations | 4 stratégies (contenu, ALS, **SVD Surprise**, hybride), filtre de fraîcheur, étoiles |
| Parcourir les articles | catalogue complet, 4 tris, filtre par note |
| Nouveau client | inscription, région, profil initial |

## Deux limites propres à l'hébergement

**Les clients inscrits sont temporaires.** Un Space est éphémère : la base SQLite vit
dans `/tmp`, elle est perdue à chaque redémarrage et **partagée entre tous les
visiteurs**. L'application l'affiche en bannière. N'y saisir aucune donnée personnelle.

**Les artefacts de fraîcheur périment.** Le vivier d'articles récents est figé au
moment de la publication. Sur des données réelles il faudrait le republier
régulièrement (voir `docs/architecture.md` §4.f) ; ici les données sont statiques, la
démonstration reste donc représentative.

## Publier / mettre à jour

```bash
# 1. générer les artefacts (depuis le dépôt principal)
python -m src.prepare_model --data-dir data/news-portal-user --out-dir models
python -m src.collaborative_surprise --data-dir data/news-portal-user --out-dir models

# 2. publier les artefacts sur le HF Hub (~254 Mo)
huggingface-cli login
python spaces/upload_artifacts.py --repo <org>/ricochet-models --models-dir models

# 3. pousser le Space
huggingface-cli upload <org>/ricochet spaces/ . --repo-type space
```

## Secrets et variables du Space

*Settings → Variables and secrets*

| Nom | Type | Rôle |
|-----|------|------|
| `HF_MODEL_REPO` | variable | id du dépôt de modèle (ex. `<org>/ricochet-models`) |
| `HF_TOKEN` | secret | requis uniquement si le dépôt de modèle est privé |
| `CLIENTS_DB` | variable | facultatif : chemin de la base clients (défaut `/tmp/clients.db`) |

## Tester en local, sans passer par le Hub

```bash
pip install -r spaces/requirements.txt
MODELS_DIR=models streamlit run spaces/app.py
```

## Fichiers

| Fichier | Rôle |
|---|---|
| `app.py` | point d'entrée : télécharge les artefacts, appelle `ui.run()` |
| `ui.py` | **généré** — interface commune (source : `src/app_ui.py`) |
| `recommender.py` | **généré** — cœur de reco (source : `src/recommender.py`) |
| `user_store.py` | **généré** — clients inscrits (source : `src/user_store.py`) |
| `model_loader.py` | téléchargement des artefacts depuis le HF Hub |
| `upload_artifacts.py` | publication des artefacts vers le HF Hub |

Les fichiers marqués **généré** ne doivent pas être édités : lancer
`python scripts/sync_recommender.py` après toute modification de `src/`.
