"""Azure Function — service de recommandation (modèle de programmation Python v2).

Endpoint HTTP : GET/POST /api/recommend
  Paramètres (query string ou corps JSON) :
    - user_id (int, requis)
    - n       (int, défaut 5)
    - method  (str, défaut "mix" — stratégie servie en production ;
              "mix" | "content" | "collab" | "svd" | "hybrid")
    - region  (int, optionnel) : code de région, utilisé uniquement pour le cold
              start (un lecteur inconnu reçoit la popularité de sa région)
    - fresh_only (bool, défaut vrai) : limiter aux articles récents ; « 0 » ou
              « false » élargit à tout le catalogue (utile pour comparer)
    - history (str, optionnel) : article_id séparés par des virgules. Profil
              transmis par l'appelant, prioritaire sur les artefacts — permet de
              recommander un lecteur que le service ne connaît pas

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

    method = (_param(req, "method", body) or "mix").lower()

    # Région (code anonymisé) : n'affecte que le cold start.
    raw_region = _param(req, "region", body)
    try:
        region = int(raw_region) if raw_region not in (None, "") else None
    except (TypeError, ValueError):
        return func.HttpResponse(
            json.dumps({"error": "'region' doit être un entier"}),
            status_code=400, mimetype="application/json",
        )


    # Fraîcheur : le levier le plus fort du projet (facteur 250 sur la précision).
    # Exposé en paramètre pour que le client puisse démontrer l'écart, mais activé
    # par défaut — c'est la configuration servie en production.
    raw_fresh = _param(req, "fresh_only", body)
    fresh_only = str(raw_fresh).lower() not in ("0", "false", "non", "no")


    # Historique transmis par l'appelant : rend le service utilisable sans état.
    # Un lecteur inscrit à l'instant dans l'application cliente est inconnu des
    # artefacts ; sans cela il ne recevrait que de la popularité.
    raw_history = _param(req, "history", body)
    history = None
    if raw_history:
        try:
            history = [int(a) for a in str(raw_history).split(",") if a.strip()]
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "'history' doit être une liste d'entiers "
                                     "séparés par des virgules"}),
                status_code=400, mimetype="application/json",
            )

    try:
        recs = _get_recommender().recommend(user_id, n=n, method=method, region=region,
                                            fresh_only=fresh_only, history=history)
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
