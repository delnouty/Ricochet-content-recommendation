"""Client de l'API de recommandation — solution Azure.

Rôle assumé : **client HTTP**, et non copie de l'interface produit. Les solutions
locale et Hugging Face embarquent le modèle et partagent une interface riche
(`src/app_ui.py`) ; ici tout passe par le réseau, donc l'application ne connaît que
ce que l'endpoint renvoie : des identifiants d'articles.

Elle affiche en revanche ce qu'un client d'API a besoin de voir — la requête, la
latence, la réponse brute — car c'est précisément ce que cette architecture démontre.

Lancement :
    streamlit run app/streamlit_app.py

Configuration (barre latérale ou variables d'environnement) :
    FUNCTION_URL : endpoint (défaut http://localhost:7071/api/recommend)
    FUNCTION_KEY : clé de fonction Azure ; vide en local
"""

from __future__ import annotations

import os
import pickle
import time
from pathlib import Path

import requests
import streamlit as st

DEFAULT_URL = os.environ.get("FUNCTION_URL", "http://localhost:7071/api/recommend")
DEFAULT_KEY = os.environ.get("FUNCTION_KEY", "")
USER_CLICKS = Path(__file__).resolve().parents[1] / "models" / "user_clicks.pkl"

# Libellés identiques à ceux de l'interface produit, pour qu'une démonstration
# passant d'une solution à l'autre reste lisible.
STRATEGIES = {
    "mix": "Production — 4 populaires (1 h) + 1 contenu",
    "content": "Contenu — similarité des embeddings",
    "collab": "Collaboratif ALS — bibliothèque implicit",
    "svd": "Collaboratif SVD — bibliothèque Surprise",
    "hybrid": "Hybride — contenu + ALS (normalisé)",
}


@st.cache_data
def load_user_ids(limit: int = 500) -> list[int]:
    """Quelques identifiants connus, pour peupler la liste déroulante.

    Lus dans les artefacts locaux s'ils existent : l'API n'expose pas la liste des
    lecteurs, et ce client ne doit pas en dépendre — d'où le repli sur une saisie
    manuelle.
    """
    if USER_CLICKS.exists():
        with open(USER_CLICKS, "rb") as f:
            return sorted(pickle.load(f).keys())[:limit]
    return []


def call_api(url: str, key: str, params: dict) -> tuple[dict, float, int]:
    """Appelle l'endpoint. Renvoie (charge JSON, latence en ms, code HTTP)."""
    if key:
        params = {**params, "code": key}      # clé de fonction Azure
    debut = time.perf_counter()
    reponse = requests.get(url, params=params, timeout=60)
    latence = (time.perf_counter() - debut) * 1000
    try:
        charge = reponse.json()
    except ValueError:
        charge = {"error": reponse.text[:400] or "réponse non JSON"}
    return charge, latence, reponse.status_code


def expliquer_erreur(code: int, charge: dict) -> str:
    """Message actionnable plutôt qu'un code brut."""
    if code == 401:
        return ("401 — clé de fonction absente ou invalide. Récupérez-la avec : "
                "az functionapp function keys list --name <app> "
                "--resource-group <rg> --function-name recommend "
                "--query default -o tsv")
    if code == 404:
        return "404 — route introuvable. L'URL doit finir par /api/recommend"
    if code == 400:
        return f"400 — requête refusée : {charge.get('error', 'motif inconnu')}"
    if code >= 500:
        return (f"{code} — erreur côté service : {charge.get('error', '')}. "
                "Un premier appel après inactivité peut expirer : les artefacts "
                "(265 Mo) sont retéléchargés depuis Blob Storage.")
    return f"{code} — {charge.get('error', 'échec')}"


def main() -> None:
    st.set_page_config(page_title="Ricochet — client de l'API", page_icon="🎯")
    st.title("🎯 Ricochet — client de l'API")
    st.caption("Cette application n'embarque aucun modèle : elle interroge l'Azure "
               "Function par HTTP et affiche sa réponse.")

    with st.sidebar:
        st.header("Endpoint")
        url = st.text_input("URL", value=DEFAULT_URL)
        key = st.text_input("Clé de fonction", value=DEFAULT_KEY, type="password",
                            help="Vide pour le serveur local ; requise sur Azure "
                                 "(AuthLevel.FUNCTION).")
        st.divider()
        st.header("Paramètres de la requête")
        method = st.selectbox("Stratégie", list(STRATEGIES), index=0,
                              format_func=lambda m: STRATEGIES[m])
        n = st.slider("Nombre d'articles", 1, 10, 5)
        fresh_only = st.checkbox(
            "Limiter aux articles récents", value=True,
            help="Paramètre `fresh_only`. Décocher élargit à tout le catalogue : "
                 "c'est la comparaison qui montre l'effet de la fraîcheur "
                 "(HitRate@5 mesuré à 0,2525 contre 0,0010).")
        region = st.text_input("Région (optionnel)", value="",
                               help="Code de région anonymisé. N'intervient que "
                                    "pour un lecteur sans historique.")

    identifiants = load_user_ids()
    if identifiants:
        user_id = st.selectbox("Identifiant lecteur", identifiants)
    else:
        st.info("Aucun `models/user_clicks.pkl` en local — saisissez un identifiant.")
        user_id = st.number_input("Identifiant lecteur", min_value=0, value=0, step=1)

    st.caption("Un identifiant inconnu du service est traité en cold start : il "
               "reçoit les articles récents les plus lus.")

    if not st.button("Appeler l'API", type="primary"):
        return

    params = {"user_id": int(user_id), "n": n, "method": method}
    if not fresh_only:
        params["fresh_only"] = "0"
    if region.strip():
        params["region"] = region.strip()

    try:
        with st.spinner("Appel en cours…"):
            charge, latence, code = call_api(url, key, params)
    except requests.RequestException as exc:
        st.error(f"Appel impossible : {exc}")
        return

    if code != 200:
        st.error(expliquer_erreur(code, charge))
        st.json(charge)
        return

    recommandations = charge.get("recommendations", [])
    st.success(f"{len(recommandations)} article(s) — stratégie "
               f"« {charge.get('method')} » en {latence:.0f} ms")

    for rang, article_id in enumerate(recommandations, start=1):
        st.markdown(f"**{rang}.** Article #{article_id}")

    st.caption("Le service ne renvoie que des identifiants : titres et texte sont "
               "absents du jeu de données, anonymisé par la source.")

    with st.expander("Requête et réponse brutes"):
        lignes = "\n".join(f"  {k} = {v}" for k, v in params.items())
        st.code(f"GET {url}\n{lignes}" + ("\n  code = ***" if key else ""),
                language="text")
        st.json(charge)


if __name__ == "__main__":
    main()
