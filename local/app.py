"""Ricochet — solution LOCALE autonome (aucun cloud, aucun appel réseau).

Troisième solution du dépôt, indépendante des deux autres :

  - solution Azure  : Streamlit -> HTTP -> Azure Function -> artefacts dans Blob ;
  - solution HF     : Streamlit embarquant le modèle, artefacts depuis le HF Hub ;
  - solution LOCALE : Streamlit embarquant le modèle, artefacts depuis un dossier
                      du disque. Pas de HTTP, pas de SDK Azure, pas de HF Hub.

Le dossier `local/` est autoportant : copié ailleurs avec un dossier `models/`,
il fonctionne avec `streamlit` + `numpy` uniquement (`local/requirements.txt`).

Lancement (depuis la racine du dépôt) :
    streamlit run local/app.py

Configuration optionnelle (variables d'environnement) :
    MODELS_DIR : dossier des artefacts       (défaut : ../models puis ./models)
    DATA_DIR   : dossier contenant articles_metadata.csv, pour enrichir
                 l'affichage (catégorie, longueur, date). Purement cosmétique :
                 sans ce fichier, l'app affiche les identifiants d'articles.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from recommender import Recommender  # copie embarquée (voir scripts/sync_recommender.py)

HERE = Path(__file__).resolve().parent
STRATEGIES = ["hybrid", "content", "collab"]


# --------------------------------------------------------------------- chargement
def resolve_models_dir() -> Path:
    """Premier dossier d'artefacts trouvé : $MODELS_DIR, ../models, ./models."""
    candidates = []
    env = os.environ.get("MODELS_DIR")
    if env:
        candidates.append(Path(env))
    candidates += [HERE.parent / "models", Path.cwd() / "models"]
    for path in candidates:
        if (path / "articles_embeddings_pca.npy").exists():
            return path
    raise FileNotFoundError(
        "Artefacts introuvables. Cherché dans : "
        + ", ".join(str(c) for c in candidates)
        + "\nGénérez-les avec : python -m src.prepare_model --data-dir data/raw "
          "--out-dir models"
    )


def resolve_metadata_file() -> Path | None:
    """Localise articles_metadata.csv (optionnel) pour enrichir l'affichage."""
    candidates = []
    env = os.environ.get("DATA_DIR")
    if env:
        candidates.append(Path(env) / "articles_metadata.csv")
    root = HERE.parent
    candidates += [
        root / "data" / "raw" / "articles_metadata.csv",
        root / "data" / "news-portal-user" / "articles_metadata.csv",
    ]
    return next((c for c in candidates if c.exists()), None)


@st.cache_resource(show_spinner="Chargement du modèle…")
def get_recommender() -> tuple[Recommender, str]:
    models_dir = resolve_models_dir()
    return Recommender(models_dir), str(models_dir)


@st.cache_resource(show_spinner="Lecture des métadonnées d'articles…")
def get_metadata(path_str: str | None) -> dict[int, tuple[int, int, int]]:
    """article_id -> (category_id, words_count, created_at_ts). Vide si absent.

    Stocké en tuples d'entiers plutôt qu'en dictionnaires : 364 k articles tiennent
    ainsi dans quelques dizaines de Mo.
    """
    if not path_str:
        return {}
    out: dict[int, tuple[int, int, int]] = {}
    with open(path_str, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                out[int(row["article_id"])] = (int(row["category_id"]),
                                               int(row["words_count"]),
                                               int(row["created_at_ts"]))
            except (KeyError, TypeError, ValueError):
                continue
    return out


# ---------------------------------------------------------------------- affichage
def describe(article_id: int, meta: dict[int, tuple[int, int, int]]) -> str:
    """Ligne descriptive d'un article, dégradée proprement sans métadonnées."""
    entry = meta.get(int(article_id))
    if not entry:
        return f"Article #{article_id}"
    category, words, created_ts = entry
    published = datetime.fromtimestamp(created_ts / 1000, tz=timezone.utc).strftime("%d/%m/%Y")
    return f"Article #{article_id} — catégorie {category} · {words} mots · publié le {published}"


def main() -> None:
    st.set_page_config(page_title="Ricochet — recommandation locale", page_icon="🎯")
    st.title("🎯 Ricochet — recommandation d'articles")
    st.caption("Solution locale autonome : le modèle tourne dans ce processus, "
               "aucun appel réseau, aucun service cloud.")

    try:
        reco, models_dir = get_recommender()
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
        return

    meta_file = resolve_metadata_file()
    meta = get_metadata(str(meta_file) if meta_file else None)

    known_users = sorted(reco.user_clicks.keys())

    with st.sidebar:
        st.header("Paramètres")
        method = st.selectbox("Stratégie", STRATEGIES, index=0,
                              help="hybrid = contenu + collaboratif (min-max normalisés)")
        n = st.slider("Nombre d'articles", 1, 10, 5)
        cold_start = st.checkbox("Simuler un nouvel utilisateur (cold start)",
                                 help="Utilisateur inconnu du modèle : repli sur les "
                                      "articles les plus populaires.")
        st.divider()
        st.caption(f"Artefacts : `{models_dir}`")
        st.caption(f"Catalogue : {reco.n_articles:,} articles")
        st.caption(f"Utilisateurs connus : {len(known_users):,}")
        st.caption(f"Filtrage collaboratif : {'disponible' if reco._has_cf else 'absent'}")
        st.caption(f"Métadonnées : {'chargées' if meta else 'non trouvées (affichage des id)'}")

    if cold_start:
        user_id = -1
        st.info("Mode cold start : aucun historique, la recommandation se rabat sur "
                "la popularité globale.")
    elif known_users:
        user_id = st.selectbox("Identifiant utilisateur", known_users)
    else:
        user_id = st.number_input("Identifiant utilisateur", min_value=0, value=0, step=1)

    # Historique : rend la recommandation interprétable (d'où vient le profil).
    history = reco.user_clicks.get(int(user_id), [])
    if len(history):
        with st.expander(f"Historique de lecture ({len(history)} article(s))"):
            for article_id in list(history)[-10:][::-1]:
                st.write("•", describe(int(article_id), meta))

    if st.button("Recommander", type="primary"):
        try:
            recs = reco.recommend(int(user_id), n=n, method=method)
        except ValueError as exc:
            st.error(str(exc))
            return

        if not recs:
            st.warning("Aucune recommandation disponible pour cet utilisateur.")
            return

        used_fallback = not len(history)
        st.success(f"{len(recs)} article(s) recommandé(s) — stratégie : "
                   f"{'popularité (cold start)' if used_fallback else method}")
        for rank, article_id in enumerate(recs, start=1):
            st.markdown(f"**{rank}.** {describe(int(article_id), meta)}")


if __name__ == "__main__":
    main()
