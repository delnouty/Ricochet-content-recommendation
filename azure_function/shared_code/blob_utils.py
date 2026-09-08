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

**La fraîcheur du cache se juge sur la date, pas sur la taille** (voir `_a_jour`).
Deuxième défaut silencieux de la même famille : un SVD reconstruit avec une autre
définition de note produit des artefacts de taille identique, et les instances au
cache survivant ne les retéléchargeaient pas. Le service a servi deux modèles
différents selon l'instance touchée — mesuré : 6 réponses sur 10 avec le nouveau
modèle, 4 avec l'ancien.
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


def _a_jour(dest: Path, blob) -> bool:
    """Le fichier en cache correspond-il au blob **actuel** ?

    La taille seule ne suffit pas, et c'est un défaut qui s'est produit : le SVD
    a été reconstruit avec une autre définition de note, donc un modèle
    entièrement différent — mais le même nombre de lecteurs et de facteurs, donc
    des artefacts d'**exactement** la même taille. Les instances dont le cache
    local avait survécu ne les ont jamais retéléchargés, et le service a répondu
    avec deux modèles différents selon l'instance touchée, sans lever d'erreur.

    On compare donc aussi la date : un blob plus récent que la copie locale est
    retéléchargé. Le cas « fichier local plus récent » n'arrive pas, puisque
    l'horodatage local est aligné sur celui du blob après chaque téléchargement.
    """
    if not dest.exists() or dest.stat().st_size != blob.size:
        return False
    if blob.last_modified is None:
        return True  # le service ne datant pas le blob, la taille est tout ce qu'on a
    # Une seconde de tolérance : les systèmes de fichiers n'ont pas tous la
    # résolution des horodatages HTTP.
    return dest.stat().st_mtime + 1 >= blob.last_modified.timestamp()


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
        if _a_jour(dest, blob):
            continue  # déjà en cache, complet et pas plus vieux que le blob
        with open(dest, "wb") as f:
            f.write(client.get_blob_client(nom).download_blob().readall())
        # Aligner l'horodatage local sur celui du blob : c'est ce qui rend la
        # comparaison suivante fiable, y compris après un redéploiement.
        if blob.last_modified is not None:
            horodatage = blob.last_modified.timestamp()
            os.utime(dest, (horodatage, horodatage))

    manquants = [nom for nom in REQUIRED if nom not in disponibles]
    if manquants:
        raise FileNotFoundError(
            f"Artefacts requis absents du conteneur « {container} » : "
            f"{', '.join(manquants)}. Publier `models/` avec "
            "`az storage blob upload-batch`."
        )

    return cache
