"""Adaptateur : présente une API HTTP distante comme un `Recommender` local.

Permet à l'interface commune (`src/app_ui.py`, partagée par les solutions locale et
Hugging Face) de fonctionner **sans modèle embarqué** : le classement vient de
l'Azure Function, tout le reste vient d'artefacts légers lus sur le disque.

Ce que l'interface demande à un `Recommender` — et d'où cela vient ici :

| Attribut | Source |
|---|---|
| `recommend()` | **appel HTTP** vers l'Azure Function |
| `user_clicks` | `user_clicks.pkl` (historique des lecteurs du jeu de données) |
| `popular_recent`, `popular_articles`, `popular_by_region`, `recent_window` | artefacts |
| `n_articles` | taille de `article_stars.npy` |

Les **embeddings ne sont pas chargés** : l'interface ne les utilise jamais
directement, seul le service en a besoin pour calculer. D'où un client d'environ
36 Mo au lieu des 265 Mo du jeu complet.

Un client inscrit dans l'application est inconnu du service : son historique est
donc transmis dans la requête (paramètre `history`), ce qui permet au service, sans
état, de le recommander comme n'importe quel lecteur connu.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import requests

# Artefacts nécessaires à l'affichage. Volontairement sans embeddings ni facteurs.
LEGERS = ("user_clicks.pkl", "popular_articles.npy", "popular_recent.npy",
          "popular_by_region.pkl", "recent_window.json", "article_stars.npy")


class ApiRecommender:
    """Même surface que `Recommender`, mais le classement vient du réseau."""

    def __init__(self, models_dir: Path, url: str, key: str = "", timeout: int = 60):
        self.models_dir = Path(models_dir)
        self.url = url
        self.key = key
        self.timeout = timeout
        self.derniere_latence_ms: float | None = None
        self.derniere_erreur: str | None = None

        stars = self.models_dir / "article_stars.npy"
        if not stars.exists():
            raise FileNotFoundError(
                f"{stars} manquant. Ce client a besoin des artefacts légers "
                f"({', '.join(LEGERS)}) pour l'affichage — le calcul, lui, est "
                "fait par le service distant."
            )
        self.n_articles = int(np.load(stars).size)

        with open(self.models_dir / "user_clicks.pkl", "rb") as f:
            self.user_clicks: dict[int, np.ndarray] = pickle.load(f)

        self.popular_articles = np.load(self.models_dir / "popular_articles.npy")

        recent = self.models_dir / "popular_recent.npy"
        self.popular_recent = (np.load(recent) if recent.exists()
                               else np.array([], dtype=np.int64))

        fenetre = self.models_dir / "recent_window.json"
        self.recent_window: dict = (json.loads(fenetre.read_text(encoding="utf-8"))
                                    if fenetre.exists() else {})

        self.popular_by_region: dict[int, np.ndarray] = {}
        regions = self.models_dir / "popular_by_region.pkl"
        if regions.exists():
            with open(regions, "rb") as f:
                self.popular_by_region = pickle.load(f)

        # Disponibilité des modèles collaboratifs : c'est le service qui décide, le
        # client ne peut pas le savoir. On les déclare disponibles ; si le service
        # ne les a pas, il retombe proprement sur le contenu ou la popularité.
        self._has_cf = True
        self._has_svd = True

    # ------------------------------------------------------------------ réseau
    def recommend(self, user_id: int, n: int = 5, method: str = "mix",
                  region: int | None = None, fresh_only: bool = True,
                  history: list[int] | None = None) -> list[int]:
        """Interroge le service. Renvoie une liste vide en cas d'échec réseau.

        L'historique est transmis lorsque le lecteur peut être inconnu du service :
        les clients inscrits localement ont des identifiants à partir de 1 000 000,
        absents des artefacts déployés.
        """
        import time

        params: dict[str, object] = {"user_id": int(user_id), "n": int(n),
                                     "method": method}
        if region is not None:
            params["region"] = int(region)
        if not fresh_only:
            params["fresh_only"] = "0"
        if self.key:
            params["code"] = self.key

        if history is None:
            connu_du_service = int(user_id) < 1_000_000
            local = self.user_clicks.get(int(user_id))
            if not connu_du_service and local is not None and len(local):
                history = [int(a) for a in local]
        if history:
            params["history"] = ",".join(str(int(a)) for a in history)

        self.derniere_erreur = None
        debut = time.perf_counter()
        try:
            reponse = requests.get(self.url, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            self.derniere_latence_ms = None
            self.derniere_erreur = f"appel impossible : {exc}"
            return []
        self.derniere_latence_ms = (time.perf_counter() - debut) * 1000

        if reponse.status_code == 401:
            self.derniere_erreur = ("401 — clé de fonction absente ou invalide "
                                    "(variable FUNCTION_KEY)")
            return []
        try:
            charge = reponse.json()
        except ValueError:
            self.derniere_erreur = f"réponse non JSON ({reponse.status_code})"
            return []
        if reponse.status_code != 200:
            self.derniere_erreur = f"{reponse.status_code} — {charge.get('error', '')}"
            return []

        return [int(a) for a in charge.get("recommendations", [])]
