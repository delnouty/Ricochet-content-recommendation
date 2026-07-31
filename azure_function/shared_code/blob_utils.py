"""Récupération des artefacts de modèle depuis Azure Blob Storage.

Architecture 2 (choisie pour le MVP) : la Function accède directement aux
fichiers/modèles stockés dans Blob Storage, sans API intermédiaire.

En pratique, plutôt que de re-télécharger les artefacts à chaque invocation
(coûteux pour ~70 Mo d'embeddings), on les télécharge une seule fois au démarrage
à froid vers un cache local, puis on les réutilise sur les invocations à chaud.

Développement local : définir MODELS_DIR (ex. le dossier `models/` du dépôt)
pour court-circuiter Blob Storage.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Artefacts attendus par Recommender (cf_* optionnels si pas de collaboratif).
ARTIFACTS = [
    "articles_embeddings_pca.npy",
    "user_clicks.pkl",
    "popular_articles.npy",
    "cf_user_factors.npy",
    "cf_item_factors.npy",
    "cf_item_ids.npy",
    "cf_user_index.pkl",
]
REQUIRED = ARTIFACTS[:3]  # les 3 premiers sont indispensables


def ensure_models() -> Path:
    """Garantit la présence locale des artefacts et renvoie leur dossier.

    - Si MODELS_DIR est défini (dev local), on l'utilise directement.
    - Sinon, on télécharge depuis Blob Storage vers un cache local (une fois).
    """
    local = os.environ.get("MODELS_DIR")
    if local:
        return Path(local)

    conn = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
    container = os.environ.get("MODELS_CONTAINER", "models")

    cache = Path(tempfile.gettempdir()) / "recsys_models"
    cache.mkdir(parents=True, exist_ok=True)

    from azure.storage.blob import BlobServiceClient

    service = BlobServiceClient.from_connection_string(conn)
    client = service.get_container_client(container)

    for name in ARTIFACTS:
        dest = cache / name
        if dest.exists():
            continue  # déjà en cache (invocation à chaud)
        blob = client.get_blob_client(name)
        if not blob.exists():
            if name in REQUIRED:
                raise FileNotFoundError(f"Artefact requis manquant dans Blob : {name}")
            continue  # artefact optionnel (ex. collaboratif absent)
        with open(dest, "wb") as f:
            f.write(blob.download_blob().readall())

    return cache
