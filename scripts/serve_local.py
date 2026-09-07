"""Serveur de développement local — même contrat HTTP que l'Azure Function.

Pourquoi ce script : exécuter `azure_function/` réellement demande les *Azure
Functions Core Tools* (`func`). Ici on ne dépend que de la bibliothèque standard
+ `numpy` (la dépendance du cœur de reco), donc toute la pile tourne en local
avec le seul environnement virtuel du dépôt.

Le contrat est identique à `azure_function/function_app.py` :

    GET/POST /api/recommend?user_id=<int>&n=<int>&method=<mix|content|collab|svd|hybrid>
                           [&region=<int>][&fresh_only=<0|1>][&history=<id,id,...>]
    -> {"user_id": 0, "method": "hybrid", "recommendations": [id1, ..., id5]}

Mêmes codes d'erreur (400 sur paramètre manquant / non entier / méthode
inconnue, 500 sur échec interne) et même priorité query string > corps JSON, afin
que `app/streamlit_app.py` fonctionne sans modification.

⚠️  Outil de développement, pas une cible de déploiement : aucune authentification,
    aucun accès Blob, serveur mono-processus.

Usage :
    python scripts/serve_local.py                    # 127.0.0.1:7071, models/ du dépôt
    python scripts/serve_local.py --port 8000
    python scripts/serve_local.py --models-dir /autre/chemin
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.recommender import Recommender  # noqa: E402  (après ajustement de sys.path)

ROUTE = "/api/recommend"


class _Handler(BaseHTTPRequestHandler):
    """Route unique /api/recommend, calquée sur la Function Azure."""

    recommender: Recommender  # injecté par main()
    server_version = "RicochetLocal/1.0"

    # ------------------------------------------------------------------ sortie
    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        logging.info("%s - %s", self.address_string(), fmt % args)

    # ------------------------------------------------------------------ routes
    def do_GET(self) -> None:  # noqa: N802 (API de BaseHTTPRequestHandler)
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/":
            return self._json(200, {"service": "Ricochet (serveur local)",
                                    "route": ROUTE,
                                    "articles": self.recommender.n_articles})
        if path != ROUTE:
            return self._json(404, {"error": f"route inconnue : {parsed.path}"})
        self._handle(self._query(parsed.query))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if (parsed.path.rstrip("/") or "/") != ROUTE:
            return self._json(404, {"error": f"route inconnue : {parsed.path}"})

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw) if raw else {}
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}

        # Comme la Function : la query string prime sur le corps JSON.
        self._handle({**body, **self._query(parsed.query)})

    @staticmethod
    def _query(query: str) -> dict:
        return {k: v[0] for k, v in parse_qs(query).items() if v}

    # ------------------------------------------------------------------ métier
    def _handle(self, params: dict) -> None:
        raw_user = params.get("user_id")
        if raw_user is None:
            return self._json(400, {"error": "paramètre 'user_id' requis"})

        try:
            user_id = int(raw_user)
            n = int(params.get("n") or 5)
        except (TypeError, ValueError):
            return self._json(400, {"error": "'user_id' et 'n' doivent être des entiers"})

        method = str(params.get("method") or "mix").lower()

        raw_region = params.get("region")
        try:
            region = int(raw_region) if raw_region not in (None, "") else None
        except (TypeError, ValueError):
            return self._json(400, {"error": "'region' doit être un entier"})


        # Fraîcheur : le levier le plus fort du projet (facteur 250 sur la précision).
        # Exposé en paramètre pour que le client puisse démontrer l'écart, mais activé
        # par défaut — c'est la configuration servie en production.
        raw_fresh = params.get("fresh_only")
        fresh_only = str(raw_fresh).lower() not in ("0", "false", "non", "no")


        # Historique transmis par l'appelant : rend le service utilisable sans état.
        # Un lecteur inscrit à l'instant dans l'application cliente est inconnu des
        # artefacts ; sans cela il ne recevrait que de la popularité.
        raw_history = params.get("history")
        history = None
        if raw_history:
            try:
                history = [int(a) for a in str(raw_history).split(",") if a.strip()]
            except ValueError:
                return self._json(400, {"error": "'history' doit être une liste "
                                                    "d'entiers séparés par des virgules"})

        try:
            recs = self.recommender.recommend(user_id, n=n, method=method, region=region,
                                              fresh_only=fresh_only, history=history)
        except ValueError as exc:  # method inconnue
            return self._json(400, {"error": str(exc)})
        except Exception:  # noqa: BLE001
            logging.exception("Échec de la recommandation")
            return self._json(500, {"error": "erreur interne"})

        self._json(200, {"user_id": user_id, "method": method,
                         "recommendations": [int(a) for a in recs]})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models-dir", default=ROOT / "models", type=Path,
                        help="dossier des artefacts (défaut : models/ du dépôt)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=7071, type=int,
                        help="défaut 7071, le port de `func start`")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")

    if not (args.models_dir / "articles_embeddings_pca.npy").exists():
        print(f"Artefacts introuvables dans {args.models_dir}.\n"
              "Générez-les d'abord :\n"
              "  python -m src.prepare_model --data-dir data/raw --out-dir models",
              file=sys.stderr)
        return 1

    logging.info("Chargement des artefacts depuis %s…", args.models_dir)
    _Handler.recommender = Recommender(args.models_dir)
    logging.info("Recommender prêt (%d articles, %d utilisateurs connus).",
                 _Handler.recommender.n_articles, len(_Handler.recommender.user_clicks))

    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    logging.info("Écoute sur http://%s:%d%s  (Ctrl+C pour arrêter)",
                 args.host, args.port, ROUTE)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Arrêt demandé.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
