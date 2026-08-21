"""Ricochet — solution LOCALE autonome (aucun cloud, aucun appel réseau).

Point d'entrée mince : toute l'interface vit dans `ui.py` (copie générée depuis
`src/app_ui.py`), partagée avec la solution Hugging Face pour qu'elles ne divergent
pas.

Lancement, depuis la racine du dépôt :
    streamlit run local/app.py

Configuration optionnelle :
    MODELS_DIR : dossier des artefacts (défaut : ../models puis ./models)
    DATA_DIR   : dossier de articles_metadata.csv, pour l'affichage enrichi
    CLIENTS_DB : base des clients          (défaut : local/clients.db)
"""

from __future__ import annotations

import os
from pathlib import Path

import ui

HERE = Path(__file__).resolve().parent


def resolve_models_dir() -> Path:
    """Premier dossier d'artefacts trouvé : $MODELS_DIR, ../models, ./models."""
    candidates = []
    if env := os.environ.get("MODELS_DIR"):
        candidates.append(Path(env))
    candidates += [HERE.parent / "models", Path.cwd() / "models"]
    for path in candidates:
        if (path / "articles_embeddings_pca.npy").exists():
            return path
    raise FileNotFoundError(
        "Artefacts introuvables. Cherché dans : "
        + ", ".join(str(c) for c in candidates)
        + ". Générez-les : python -m src.prepare_model "
          "--data-dir data/news-portal-user --out-dir models"
    )


if __name__ == "__main__":
    # En local, la base clients est persistante : elle survit aux redémarrages.
    ui.run(resolve_models_dir(),
           os.environ.get("CLIENTS_DB", HERE / "clients.db"))
