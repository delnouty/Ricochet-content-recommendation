"""Application de gestion du système de recommandation (interface simple).

Conforme au besoin exprimé : lister des id utilisateurs, appeler l'Azure
Function pour l'id choisi, afficher les 5 articles recommandés.

Lancement :
    streamlit run app/streamlit_app.py

Configuration (barre latérale ou variables d'environnement) :
    FUNCTION_URL  : URL de l'endpoint (ex. http://localhost:7071/api/recommend
                    en local, ou https://<app>.azurewebsites.net/api/recommend)
    FUNCTION_KEY  : clé de fonction Azure (vide en local)
"""

import os
import pickle
from pathlib import Path

import requests
import streamlit as st

DEFAULT_URL = os.environ.get("FUNCTION_URL", "http://localhost:7071/api/recommend")
DEFAULT_KEY = os.environ.get("FUNCTION_KEY", "")
USER_CLICKS = Path(__file__).resolve().parents[1] / "models" / "user_clicks.pkl"


@st.cache_data
def load_user_ids(limit: int = 500) -> list[int]:
    """Charge quelques id utilisateurs connus (pour peupler la liste déroulante)."""
    if USER_CLICKS.exists():
        with open(USER_CLICKS, "rb") as f:
            users = list(pickle.load(f).keys())
        return sorted(users)[:limit]
    return []


def call_function(url: str, key: str, user_id: int, n: int, method: str) -> dict:
    params = {"user_id": user_id, "n": n, "method": method}
    if key:
        params["code"] = key  # clé de fonction Azure
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    st.set_page_config(page_title="My Content — Recommandations", page_icon="📚")
    st.title("📚 My Content — Recommandation d'articles")
    st.caption("MVP : sélectionnez un utilisateur pour obtenir 5 articles suggérés.")

    with st.sidebar:
        st.header("Configuration")
        url = st.text_input("URL de l'Azure Function", value=DEFAULT_URL)
        key = st.text_input("Clé de fonction", value=DEFAULT_KEY, type="password")
        method = st.selectbox("Stratégie", ["hybrid", "content", "collab"], index=0)
        n = st.slider("Nombre d'articles", 1, 10, 5)

    user_ids = load_user_ids()
    if user_ids:
        user_id = st.selectbox("Identifiant utilisateur", user_ids)
    else:
        st.info("Aucun `models/user_clicks.pkl` trouvé — saisissez un id manuellement.")
        user_id = st.number_input("Identifiant utilisateur", min_value=0, value=0, step=1)

    if st.button("Recommander", type="primary"):
        try:
            with st.spinner("Appel de l'Azure Function…"):
                data = call_function(url, key, int(user_id), n, method)
        except requests.RequestException as exc:
            st.error(f"Échec de l'appel : {exc}")
            return

        recs = data.get("recommendations", [])
        st.success(f"{len(recs)} articles recommandés pour l'utilisateur {user_id} "
                   f"(stratégie : {data.get('method')})")
        for rank, article_id in enumerate(recs, start=1):
            st.markdown(f"**{rank}. Article #{article_id}**")


if __name__ == "__main__":
    main()
