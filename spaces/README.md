---
title: My Content - Recommandation d'articles
emoji: 📚
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.30.0
app_file: app.py
pinned: false
---

# My Content — Démo de recommandation (Hugging Face Space)

Solution de démonstration **autonome**, indépendante de la solution Azure.
L'app Streamlit embarque le système de recommandation et calcule elle-même le
top-5 ; elle charge les artefacts depuis un **dépôt de modèle HF Hub**.

```
HF Space (Streamlit + Recommender)  ──charge──▶  HF Hub (dépôt de modèle)
                └── calcule les 5 recommandations sur place
```

## Publier / mettre à jour

```bash
# 1. Générer les artefacts (depuis le dépôt principal)
python -m src.prepare_model --data-dir data/raw --out-dir models --pca 50

# 2. Publier les artefacts sur le HF Hub
huggingface-cli login
python spaces/upload_artifacts.py --repo <org>/my-content-models --models-dir models
```

## Secrets du Space (Settings → Variables and secrets)

| Nom | Rôle |
|-----|------|
| `HF_MODEL_REPO` | id du dépôt de modèle HF Hub (ex. `<org>/my-content-models`) |
| `HF_TOKEN` | requis seulement si le dépôt de modèle est privé |

## Test en local

```bash
pip install -r spaces/requirements.txt
# pointer directement sur les artefacts locaux :
MODELS_DIR=models streamlit run spaces/app.py
```

## Fichiers

- `app.py` — application Streamlit auto-suffisante.
- `recommender.py` — copie du cœur de reco (source : `src/recommender.py`).
- `model_loader.py` — chargement des artefacts (HF Hub ou `MODELS_DIR` local).
- `upload_artifacts.py` — publication des artefacts vers le HF Hub.
