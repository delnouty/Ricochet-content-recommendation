"""Ricochet — application complète adossée à l'API Azure.

Même interface que la solution locale et que le Space Hugging Face : elle vient de
`ui.py` (copie générée depuis `src/app_ui.py`). La différence est ailleurs — **le
classement n'est pas calculé ici**, il est demandé à l'Azure Function.

    interface (ui.py)  ->  ApiRecommender  --HTTP-->  Azure Function  ->  Blob
                             (36 Mo d'artefacts, pour l'affichage seulement)

Trois applications coexistent volontairement dans ce dépôt côté Azure :

  - `app/streamlit_app.py` : client minimal — preuve de déploiement, montre la
    requête, la latence et la réponse brute ;
  - `app/app_full.py`      : **celle-ci**, l'application complète (étoiles,
    catalogue, inscription de clients) servie par le cloud ;
  - `local/app.py`         : la même interface, mais modèle embarqué.

Un client inscrit ici est inconnu du service : son historique de lecture part donc
dans la requête (paramètre `history` de l'API), ce qui permet au service, sans état,
de le recommander comme n'importe quel lecteur.

Les clients inscrits sont conservés dans **Azure Table Storage** lorsque
`AZURE_STORAGE_CONNECTION_STRING` est définie — ils survivent alors aux redémarrages
et sont visibles depuis n'importe quel appareil. Sinon, repli sur SQLite local.

Lancement :
    $env:FUNCTION_URL = "https://<app>.azurewebsites.net/api/recommend"
    $env:FUNCTION_KEY = "<clé de fonction>"
    streamlit run app/app_full.py

Sans variables, l'application interroge le serveur local (`scripts/serve_local.py`)
sur http://localhost:7071 — pratique pour tester l'interface sans Azure.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
# `ui.py` et `user_store.py` vivent dans `local/` (copies générées) : on les réutilise
# au lieu d'en faire une troisième copie qui divergerait.
sys.path.insert(0, str(RACINE / "local"))
sys.path.insert(0, str(RACINE / "app"))

import ui  # noqa: E402
from api_client import ApiRecommender  # noqa: E402

URL = os.environ.get("FUNCTION_URL", "http://localhost:7071/api/recommend")
CLE = os.environ.get("FUNCTION_KEY", "")


def resolve_models_dir() -> Path:
    """Artefacts légers pour l'affichage (le calcul est distant)."""
    if env := os.environ.get("MODELS_DIR"):
        return Path(env)
    return RACINE / "models"


if __name__ == "__main__":
    distant = "azurewebsites.net" in URL
    banniere = (f"Recommandations calculées par **l'Azure Function** "
                f"(`{URL.split('/api/')[0]}`). Cette application n'embarque aucun "
                "modèle : elle n'affiche que ce que le service renvoie."
                if distant else
                f"Mode local : le service interrogé est `{URL}`. "
                "Lancez `python scripts/serve_local.py` s'il ne répond pas.")

    models_dir = resolve_models_dir()
    clients_db = os.environ.get("CLIENTS_DB", RACINE / "app" / "clients.db")

    # Magasin de clients : Azure Table Storage si une chaîne de connexion est
    # fournie, SQLite sinon. Le même compte de stockage héberge déjà les artefacts,
    # donc aucune ressource supplémentaire n'est nécessaire.
    sys.path.insert(0, str(RACINE))
    from src.user_store_azure import open_store
    store = open_store(clients_db)

    ui.run(models_dir, clients_db, banniere=banniere,
           recommender=ApiRecommender(models_dir, URL, CLE),
           store=store)
