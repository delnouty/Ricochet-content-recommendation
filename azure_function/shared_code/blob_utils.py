"""Récupération des artefacts de modèle depuis Azure Blob Storage.

Architecture 2 (choisie pour le MVP) : la Function accède directement aux
fichiers/modèles stockés dans Blob Storage, sans API intermédiaire.

Plutôt que de re-télécharger à chaque invocation (~265 Mo), on télécharge une
seule fois au démarrage à froid vers un cache local, réutilisé ensuite par les
invocations à chaud.

Développement local : définir MODELS_DIR (ex. le dossier `models/` du dépôt) pour
court-circuiter Blob Storage.

Les trois artefacts de **fraîcheur** (23 Ko) arrivent en plus par *blob input
binding* à chaque invocation (voir `function_app.py`). Ils restent téléchargés ici
pour servir de repli : si une lecture du binding échoue, le moteur garde la fenêtre
du démarrage plutôt que de perdre la fraîcheur.

**Le téléchargement énumère le conteneur** au lieu de suivre une liste figée. Une
liste codée en dur a déjà causé un défaut silencieux : les artefacts de fraîcheur
(`popular_recent.npy`), les étoiles et les facteurs SVD, ajoutés après elle,
n'étaient pas récupérés. Le service répondait quand même — avec la popularité de
tout l'historique au lieu de celle de la dernière heure, soit un HitRate@5 de
0,0010 au lieu de 0,2525. Aucune erreur, juste de mauvaises recommandations.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Sans ces trois fichiers, `Recommender` ne peut pas s'initialiser.
REQUIRED = (
    "articles_embeddings_pca.npy",
    "user_clicks.pkl",
    "popular_articles.npy",
)

# Extensions des artefacts de modèle. Filtre volontaire : le conteneur peut aussi
# recevoir des fichiers étrangers au service (rapports, sauvegardes).
EXTENSIONS = (".npy", ".pkl", ".json")

# Artefacts de fraîcheur : livrés à chaque invocation par un **blob input binding**
# (voir function_app.py), mais **aussi téléchargés ici**. Ce n'est pas un doublon
# inutile : 23 Ko au démarrage donnent une valeur de repli si une lecture du binding
# échoue. La copie ne masque rien, puisque le binding s'applique après
# l'initialisation du moteur, à chaque appel.
PAR_BINDING = ("popular_recent.npy", "candidates_recent.npy", "recent_window.json")


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

    disponibles = []
    for blob in client.list_blobs():
        nom = blob.name
        # Un artefact dans un sous-dossier casserait le chemin attendu : on ignore.
        if "/" in nom or not nom.endswith(EXTENSIONS):
            continue
        disponibles.append(nom)

        dest = cache / nom
        if dest.exists() and dest.stat().st_size == blob.size:
            continue  # déjà en cache et complet (invocation à chaud)
        with open(dest, "wb") as f:
            f.write(client.get_blob_client(nom).download_blob().readall())

    manquants = [nom for nom in REQUIRED if nom not in disponibles]
    if manquants:
        raise FileNotFoundError(
            f"Artefacts requis absents du conteneur « {container} » : "
            f"{', '.join(manquants)}. Publier `models/` avec "
            "`az storage blob upload-batch`."
        )

    return cache
