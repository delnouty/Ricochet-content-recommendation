"""Azure Function — service de recommandation (modèle de programmation Python v2).

Endpoint HTTP : GET/POST /api/recommend
  Paramètres (query string ou corps JSON) :
    - user_id (int, requis)
    - n       (int, défaut 5)
    - method  (str, défaut "hybrid" ; "content" | "collab" | "hybrid")

Réponse JSON :
    {"user_id": 123, "method": "hybrid", "recommendations": [id1, ..., id5]}

Le Recommender est instancié une seule fois (démarrage à froid) puis réutilisé.
"""

import json
import logging

import azure.functions as func

from shared_code.blob_utils import ensure_models
from shared_code.recommender import Recommender

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

_recommender: Recommender | None = None


def _get_recommender() -> Recommender:
    """Charge (paresseusement) puis met en cache le Recommender."""
    global _recommender
    if _recommender is None:
        logging.info("Chargement des artefacts de modèle…")
        _recommender = Recommender(ensure_models())
        logging.info("Recommender prêt (%d articles).", _recommender.n_articles)
    return _recommender


def _param(req: func.HttpRequest, name: str, body: dict):
    """Récupère un paramètre depuis la query string ou le corps JSON."""
    value = req.params.get(name)
    if value is None:
        value = body.get(name)
    return value


@app.route(route="recommend", methods=[func.HttpMethod.GET, func.HttpMethod.POST])
def recommend(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json() if req.get_body() else {}
    except ValueError:
        body = {}

    raw_user = _param(req, "user_id", body)
    if raw_user is None:
        return func.HttpResponse(
            json.dumps({"error": "paramètre 'user_id' requis"}),
            status_code=400, mimetype="application/json",
        )

    try:
        user_id = int(raw_user)
        n = int(_param(req, "n", body) or 5)
    except (TypeError, ValueError):
        return func.HttpResponse(
            json.dumps({"error": "'user_id' et 'n' doivent être des entiers"}),
            status_code=400, mimetype="application/json",
        )

    method = (_param(req, "method", body) or "hybrid").lower()

    try:
        recs = _get_recommender().recommend(user_id, n=n, method=method)
    except ValueError as exc:  # method inconnue
        return func.HttpResponse(
            json.dumps({"error": str(exc)}),
            status_code=400, mimetype="application/json",
        )
    except Exception:  # noqa: BLE001
        logging.exception("Échec de la recommandation")
        return func.HttpResponse(
            json.dumps({"error": "erreur interne"}),
            status_code=500, mimetype="application/json",
        )

    return func.HttpResponse(
        json.dumps({"user_id": user_id, "method": method,
                    "recommendations": [int(a) for a in recs]}),
        status_code=200, mimetype="application/json",
    )
