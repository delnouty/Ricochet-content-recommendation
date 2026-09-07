"""Ricochet — Space Hugging Face (démo publique auto-suffisante).

Même interface que la solution locale : elle vient de `ui.py`, copie générée depuis
`src/app_ui.py`. Seules changent deux choses, propres à l'hébergement :

  - les artefacts sont téléchargés depuis un **dépôt de modèle HF Hub**
    (`model_loader.ensure_models`), et non lus dans le dépôt ;
  - la base des clients inscrits vit dans `/tmp` : un Space est **éphémère**, elle
    est perdue à chaque redémarrage et partagée entre tous les visiteurs. L'interface
    l'annonce, pour qu'un visiteur ne croie pas ses données conservées.

Test en local, sans passer par le Hub :
    MODELS_DIR=models streamlit run spaces/app.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import ui
from model_loader import ensure_models

BANNIERE_EPHEMERE = (
    "Démonstration publique : les clients inscrits ici sont **temporaires** "
    "(perdus au redémarrage du Space) et visibles par les autres visiteurs. "
    "N'y saisissez aucune donnée personnelle.")

BANNIERE_PERSISTANT = (
    "Démonstration publique : les clients inscrits sont **conservés** et visibles "
    "par tous les visiteurs. N'y saisissez aucune donnée personnelle.")

if __name__ == "__main__":
    clients_db = Path(os.environ.get("CLIENTS_DB",
                                     Path(tempfile.gettempdir()) / "clients.db"))

    # Si le Space reçoit une chaîne de connexion Azure en secret, les clients
    # inscrits survivent aux redémarrages ; sinon ils restent dans /tmp, donc
    # éphémères — et la bannière doit dire lequel des deux est vrai.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        from src.user_store_azure import open_store
        store = open_store(clients_db)
    except ImportError:
        store = None

    persistant = store is not None and getattr(store, "db_path", None) is None
    banniere = (BANNIERE_PERSISTANT if persistant else BANNIERE_EPHEMERE)
    ui.run(ensure_models(), clients_db, banniere=banniere, store=store)
