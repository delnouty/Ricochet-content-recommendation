"""Chargement des artefacts de modèle pour le Space Hugging Face.

Solution HF : les artefacts sont stockés dans un **dépôt de modèle HF Hub**
(l'équivalent HF d'Azure Blob Storage). Le Space les télécharge au démarrage.

Variables d'environnement / secrets du Space :
  - HF_MODEL_REPO : id du dépôt de modèle (ex. "mon-org/my-content-models")
  - HF_TOKEN      : jeton HF si le dépôt est privé (optionnel si public)
  - MODELS_DIR    : dossier local (dev) ; court-circuite le téléchargement HF Hub
"""

from __future__ import annotations

import os
from pathlib import Path


def ensure_models() -> Path:
    """Renvoie un dossier local contenant tous les artefacts du modèle."""
    local = os.environ.get("MODELS_DIR")
    if local and Path(local).exists():
        return Path(local)

    repo_id = os.environ.get("HF_MODEL_REPO")
    if not repo_id:
        raise RuntimeError(
            "Aucune source de modèle : définir MODELS_DIR (local) ou "
            "HF_MODEL_REPO (dépôt de modèle HF Hub)."
        )

    from huggingface_hub import snapshot_download

    path = snapshot_download(
        repo_id=repo_id,
        repo_type="model",
        token=os.environ.get("HF_TOKEN"),
        # `recent_window.json` fait partie des artefacts : sans lui, l'interface
        # ne sait pas de quand date le vivier de fraîcheur.
        allow_patterns=["*.npy", "*.pkl", "recent_window.json"],
    )
    return Path(path)
