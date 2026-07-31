"""Space Hugging Face — démo de recommandation d'articles (AUTO-SUFFISANT).

Solution HF indépendante de la solution Azure : l'app embarque le Recommender
et calcule elle-même les recommandations. Les artefacts sont chargés depuis un
dépôt de modèle HF Hub (voir model_loader.py).

Lancement local :
    MODELS_DIR=../models streamlit run spaces/app.py
"""

import streamlit as st

from model_loader import ensure_models
from recommender import Recommender


@st.cache_resource(show_spinner="Chargement du modèle…")
def get_recommender() -> Recommender:
    """Instancie le Recommender une seule fois (mis en cache par le Space)."""
    return Recommender(ensure_models())


@st.cache_data
def sample_user_ids(_reco: Recommender, limit: int = 500) -> list[int]:
    return sorted(_reco.user_clicks.keys())[:limit]


def main() -> None:
    st.set_page_config(page_title="My Content — Recommandations", page_icon="📚")
    st.title("📚 My Content — Recommandation d'articles")
    st.caption("Démo Hugging Face (auto-suffisante) — 5 articles recommandés par utilisateur.")

    try:
        reco = get_recommender()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Impossible de charger le modèle : {exc}")
        st.info("Vérifiez le secret `HF_MODEL_REPO` (dépôt de modèle HF Hub) "
                "ou `MODELS_DIR` en local.")
        return

    with st.sidebar:
        st.header("Paramètres")
        method = st.selectbox("Stratégie", ["hybrid", "content", "collab"], index=0)
        n = st.slider("Nombre d'articles", 1, 10, 5)
        st.caption(f"Catalogue : {reco.n_articles:,} articles")

    ids = sample_user_ids(reco)
    if ids:
        user_id = st.selectbox("Identifiant utilisateur", ids)
    else:
        user_id = st.number_input("Identifiant utilisateur", min_value=0, value=0, step=1)

    if st.button("Recommander", type="primary"):
        try:
            recs = reco.recommend(int(user_id), n=n, method=method)
        except ValueError as exc:
            st.error(str(exc))
            return
        st.success(f"{len(recs)} articles recommandés pour l'utilisateur {user_id} "
                   f"(stratégie : {method})")
        for rank, article_id in enumerate(recs, start=1):
            st.markdown(f"**{rank}. Article #{article_id}**")


if __name__ == "__main__":
    main()
