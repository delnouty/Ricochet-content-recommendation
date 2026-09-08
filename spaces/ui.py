"""COPIE DÉPLOYÉE (solution Hugging Face) — générée depuis src/app_ui.py.

⚠️  NE PAS ÉDITER ICI : toute modification serait écrasée.
    Source unique de vérité : src/app_ui.py
    Régénérer : python scripts/sync_recommender.py
    Vérifier  : python scripts/sync_recommender.py --check   (utilisé en CI)
"""


from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import streamlit as st

from recommender import Recommender  # copie embarquée (scripts/sync_recommender.py)
from user_store import UserStore

# Contexte fourni par l'hébergement (voir run()).
_CTX: dict = {"models_dir": None, "clients_db": None, "recommender": None,
              "store": None}
# Libellés explicites : « collab » et « svd » sont deux modèles collaboratifs
# différents, entraînés par deux bibliothèques différentes.
# `mix` en premier : c'est la stratégie retenue pour la production, sur mesures
# (voir notebooks 03 à 07). Les autres restent accessibles pour comparaison.
STRATEGIES = {
    "mix": "Production — 4 populaires (1 h) + 1 contenu",
    "content": "Contenu — similarité des embeddings",
    "collab": "Collaboratif ALS — bibliothèque implicit",
    "svd": "Collaboratif SVD — bibliothèque Surprise",
    "hybrid": "Hybride — contenu + ALS (normalisé)",
}


# --------------------------------------------------------------------- chargement
def resolve_models_dir() -> Path:
    """Dossier d'artefacts fixé par l'hébergement, avec repli sur le dépôt."""
    if _CTX["models_dir"] is not None:
        return Path(_CTX["models_dir"])
    candidates = []
    if env := os.environ.get("MODELS_DIR"):
        candidates.append(Path(env))
    candidates += [Path.cwd() / "models", Path.cwd().parent / "models"]
    for path in candidates:
        if (path / "articles_embeddings_pca.npy").exists():
            return path
    raise FileNotFoundError(
        "Artefacts introuvables. Cherché dans : "
        + ", ".join(str(c) for c in candidates)
        + "\nGénérez-les : python -m src.prepare_model --data-dir data/raw --out-dir models"
    )


def resolve_metadata_file() -> Path | None:
    candidates = []
    if env := os.environ.get("DATA_DIR"):
        candidates.append(Path(env) / "articles_metadata.csv")
    # À côté des artefacts en priorité : sur un Space, le dépôt de données n'est
    # pas cloné, le CSV ne peut venir que du dépôt de modèle HF.
    candidates.append(resolve_models_dir() / "articles_metadata.csv")
    racine = Path.cwd()
    candidates += [racine / "data" / "raw" / "articles_metadata.csv",
                   racine / "data" / "news-portal-user" / "articles_metadata.csv",
                   racine.parent / "data" / "news-portal-user" / "articles_metadata.csv"]
    return next((c for c in candidates if c.exists()), None)


def get_recommender() -> tuple[object, str]:
    """Moteur injecté par l'hébergement, sinon `Recommender` local (mis en cache)."""
    if _CTX["recommender"] is not None:
        return _CTX["recommender"], str(_CTX["models_dir"])
    return _charger_local(str(_CTX["models_dir"] or ""))


@st.cache_resource(show_spinner="Chargement du modèle…")
def _charger_local(_cle: str) -> tuple[Recommender, str]:
    models_dir = resolve_models_dir()
    return Recommender(models_dir), str(models_dir)


def get_store():
    """Magasin de clients : injecté par l'hébergement, sinon SQLite local."""
    if _CTX["store"] is not None:
        return _CTX["store"]
    return _ouvrir_store_local(_CTX["clients_db"]
                               or os.environ.get("CLIENTS_DB", "clients.db"))


@st.cache_resource
def _ouvrir_store_local(chemin: str) -> UserStore:
    return UserStore(chemin)


@st.cache_resource(show_spinner="Lecture des métadonnées d'articles…")
def get_metadata(path_str: str | None) -> dict[int, tuple[int, int, int]]:
    """article_id -> (category_id, words_count, created_at_ts). Vide si absent."""
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


@st.cache_resource(show_spinner="Chargement des notes…")
def get_ratings() -> tuple[np.ndarray | None, np.ndarray | None]:
    """Étoiles et nombre de clics par article (artefacts optionnels).

    Produits par `prepare_model.build_article_stars` : tout l'historique de clics
    distillé en un octet par article. On peut donc afficher une note sans embarquer
    les données utilisateur.
    """
    models_dir = resolve_models_dir()
    stars_file = models_dir / "article_stars.npy"
    clicks_file = models_dir / "article_clicks.npy"
    if not stars_file.exists():
        return None, None
    stars = np.load(stars_file)
    clicks = np.load(clicks_file) if clicks_file.exists() else None
    return stars, clicks


# ---------------------------------------------------------------------- affichage
def describe(article_id: int, meta: dict) -> str:
    stars, clicks = get_ratings()

    # Note : ★ par facteur 10 de clics (voir build_article_stars). 0 = jamais lu.
    note = ""
    if stars is not None and int(article_id) < stars.size:
        n_stars = int(stars[int(article_id)])
        if n_stars > 0:
            note = " " + "★" * n_stars
            if clicks is not None:
                note += f" ({int(clicks[int(article_id)]):,} lecteurs)".replace(",", " ")
        else:
            note = " ☆ (jamais lu)"

    entry = meta.get(int(article_id))
    if not entry:
        return f"Article #{article_id}{note}"
    category, words, created_ts = entry
    published = datetime.fromtimestamp(created_ts / 1000, tz=timezone.utc).strftime("%d/%m/%Y")
    return (f"Article #{article_id}{note} — catégorie {category} · {words} mots "
            f"· publié le {published}")


@st.cache_resource(show_spinner="Tri du catalogue…")
def get_sorted_articles(_meta: dict, order: str, _popular: tuple) -> list[int]:
    """Catalogue trié selon un critère lisible par un humain.

    Les seuls critères disponibles sont ceux que porte réellement le jeu de données
    (anonymisé) : popularité, date de publication, longueur.
    """
    if order == "popular" or not _meta:
        return list(_popular)
    if order == "recent":
        return [a for a, _ in sorted(_meta.items(), key=lambda kv: -kv[1][2])]
    if order == "short":
        return [a for a, _ in sorted(_meta.items(), key=lambda kv: kv[1][1])]
    if order == "long":
        return [a for a, _ in sorted(_meta.items(), key=lambda kv: -kv[1][1])]
    raise ValueError(f"ordre inconnu : {order}")


def sync_store_into_model(reco: Recommender, store: UserStore) -> None:
    """Injecte les historiques des clients inscrits dans le modèle en mémoire.

    `user_clicks` est un simple dictionnaire : y ajouter un client suffit pour que
    le content-based et l'hybride le prennent en compte. Le collaboratif l'ignore
    (absent des facteurs ALS) et retombe proprement sur le contenu — comportement
    attendu jusqu'au prochain ré-entraînement.
    """
    for user_id, history in store.all_histories().items():
        reco.user_clicks[user_id] = np.asarray(history, dtype=np.int64)


# ------------------------------------------------------------------------- vues
def view_new_client(reco: Recommender, store: UserStore, meta: dict) -> None:
    st.subheader("Inscrire un nouveau client")

    st.caption("Le jeu de données est anonymisé : les articles n'ont ni titre ni texte, "
               "seulement un identifiant, une date et une longueur. Un nouveau client "
               "démarre donc sur les articles **les plus lus**, puis son profil se "
               "construit à mesure qu'il marque des articles comme lus.")

    # Clé explicite : permet de vider le champ après inscription (voir plus bas).
    name = st.text_input("Nom du client", placeholder="ex. Camille Martin", key="new_name")

    # Région : seule information exploitable sur un lecteur dont on ne sait rien.
    # Elle sert uniquement au cold start (popularité régionale plutôt que mondiale).
    regions = sorted(reco.popular_by_region)
    region = st.selectbox(
        "Région du lecteur (optionnel)", [None] + regions, key="new_region",
        format_func=lambda r: ("— inconnue (popularité mondiale) —" if r is None
                               else f"Région {r}"),
        help="Avant son premier clic, le client reçoit les articles les plus lus "
             "de sa région. Les codes de région sont anonymisés dans le jeu de données.")

    popular = [int(a) for a in reco.popular_articles]
    seed = st.multiselect(
        "Articles déjà lus (optionnel)", popular[:30], key="new_articles",
        format_func=lambda a: f"{popular.index(a) + 1}ᵉ article le plus lu — "
                              f"{describe(a, meta).removeprefix('Article #' + str(a) + ' — ')}"
                              if meta.get(a) else f"Article #{a} (n°{popular.index(a) + 1} des plus lus)",
        help="Laissez vide pour un démarrage à froid : le client recevra les articles "
             "les plus populaires, et son profil se formera à l'usage.")

    if seed:
        st.caption(f"Profil initial : {len(seed)} article(s).")
    else:
        st.caption("Aucun article sélectionné → démarrage à froid (articles populaires).")

    if st.button("Inscrire le client", type="primary", disabled=not name.strip()):
        try:
            user_id = store.create_client(name, region=region)
        except ValueError as exc:
            st.error(str(exc))
            return
        added = store.add_reads(user_id, seed)
        sync_store_into_model(reco, store)
        # Relance immédiate : sans elle, la barre latérale et le sélecteur de
        # l'onglet « Recommandations » afficheraient l'état d'avant l'inscription.
        st.session_state["flash"] = (
            f"Client « {name} » inscrit — user_id **{user_id}**, "
            f"{added} lecture(s) enregistrée(s). "
            + ("Sélectionnez-le dans l'onglet « Recommandations »."
               if added else
               "Sans lecture initiale, il reçoit les articles populaires (cold start).")
        )
        st.session_state["selected_client"] = user_id
        # Remise à zéro du formulaire : supprimer la clé d'un widget le réinitialise
        # à sa valeur par défaut au prochain rendu. Sans cela, le nom et les
        # catégories du client précédent restent affichés, et une seconde
        # inscription échoue sur l'unicité du nom.
        for key in ("new_name", "new_articles", "new_region"):
            st.session_state.pop(key, None)
        st.rerun()


def view_recommendations(reco: Recommender, store: UserStore, meta: dict) -> None:
    clients = store.list_clients()
    dataset_users = sorted(reco.user_clicks.keys() - {c["user_id"] for c in clients})

    choices: list[tuple[str, int]] = [
        (f"👤 {c['name']} (#{c['user_id']}, {c['reads']} lecture(s))", c["user_id"])
        for c in clients
    ]
    choices += [(f"jeu de données — utilisateur {u}", u) for u in dataset_users[:500]]

    if not choices:
        st.info("Aucun client inscrit. Utilisez l'onglet « Nouveau client ».")
        return

    # Un client qui vient d'être inscrit est présélectionné.
    labels = [c[0] for c in choices]
    just_created = st.session_state.pop("selected_client", None)
    index = next((i for i, (_lbl, uid) in enumerate(choices) if uid == just_created), 0)

    label = st.selectbox("Client / utilisateur", labels, index=index)
    user_id = dict(choices)[label]

    col1, col2 = st.columns(2)
    method = col1.selectbox("Stratégie", list(STRATEGIES), index=0,
                            format_func=lambda m: STRATEGIES[m])
    n = col2.slider("Nombre d'articles", 1, 10, 5)

    # La fraîcheur est le levier le plus fort mesuré (facteur 250 sur la précision) :
    # elle est donc active par défaut, mais reste débrayable pour comparer.
    fenetre = reco.recent_window.get("window_hours_effective")
    if reco.popular_recent.size:
        duree = f", fenêtre {fenetre:g} h" if fenetre else ""
        etiquette = (f"Limiter aux articles récents — "
                     f"{reco.popular_recent.size:,} articles{duree}".replace(",", " "))
    else:
        etiquette = "Limiter aux articles récents (artefact absent)"
    fresh_only = st.checkbox(
        etiquette,
        value=bool(reco.popular_recent.size),
        disabled=not reco.popular_recent.size,
        help="Sans ce filtre, les stratégies choisissent dans tout le catalogue, "
             "dont l'essentiel n'a plus aucun lecteur.")

    history = list(reco.user_clicks.get(int(user_id), []))
    region = store.region_of(user_id)

    if history:
        with st.expander(f"Historique de lecture ({len(history)} article(s))"):
            for article_id in history[-10:][::-1]:
                st.write("•", describe(int(article_id), meta))
    else:
        # Le message doit décrire ce que le moteur fait réellement : la cascade de
        # repli croise région et fraîcheur quand les deux sont disponibles, sinon
        # elle utilise ce qui existe. Annoncer « articles de votre région » alors
        # que le moteur sert des articles frais serait faux.
        a_region = region is not None and region in reco.popular_by_region
        a_frais = fresh_only and reco.popular_recent.size > 0
        if a_region and a_frais:
            origine = f"les articles récents les plus lus dans la région {region}"
        elif a_frais:
            origine = "les articles les plus lus de la fenêtre récente"
        elif a_region:
            origine = f"les articles les plus lus de la région {region}"
        else:
            origine = "les articles les plus lus de tout l'historique"
        st.info(f"Aucun historique : ce client reçoit {origine} (cold start).")

    if store.name_of(user_id) and user_id not in getattr(reco, "cf_user_index", {}):
        st.caption("Client inscrit localement : absent des facteurs ALS, le "
                   "collaboratif retombe sur le contenu jusqu'au prochain ré-entraînement.")

    # Action explicite : rien n'est calculé avant le clic. Le choix du client reste
    # mémorisé ensuite, pour que les recommandations se rafraîchissent d'elles-mêmes
    # quand on marque un article comme lu ou qu'on change de stratégie.
    if st.button("Recommander", type="primary"):
        st.session_state["recs_for"] = int(user_id)

    if st.session_state.get("recs_for") != int(user_id):
        st.caption("Cliquez sur « Recommander » pour obtenir les suggestions.")
        return

    try:
        recs = reco.recommend(int(user_id), n=n, method=method, region=region,
                              fresh_only=fresh_only)
    except ValueError as exc:
        st.error(str(exc))
        return

    if not recs:
        # Un moteur distant peut échouer sans lever d'exception (réseau, 401) :
        # il expose alors `derniere_erreur`, qu'il faut montrer plutôt que de
        # laisser une page vide.
        erreur = getattr(reco, "derniere_erreur", None)
        if erreur:
            st.error(f"Le service n'a rien renvoyé — {erreur}")
        else:
            st.warning("Aucune recommandation disponible pour ce lecteur.")
        return

    latence = getattr(reco, "derniere_latence_ms", None)
    detail = f" — {latence:.0f} ms" if latence else ""
    st.markdown(f"**{len(recs)} article(s) recommandé(s)** — "
                f"{'popularité (cold start)' if not history else method}{detail}")

    is_client = store.name_of(user_id) is not None
    for rank, article_id in enumerate(recs, start=1):
        row = st.columns([6, 1])
        row[0].markdown(f"**{rank}.** {describe(int(article_id), meta)}")
        if is_client and row[1].button("Lu", key=f"read-{user_id}-{article_id}",
                                       help="Enregistrer cette lecture et affiner le profil"):
            store.add_read(user_id, int(article_id))
            sync_store_into_model(reco, store)
            st.rerun()

    if not is_client:
        st.caption("Les lectures ne peuvent être enregistrées que pour un client "
                   "inscrit (les utilisateurs du jeu de données sont en lecture seule).")


def view_browse(reco: Recommender, store: UserStore, meta: dict) -> None:
    """Catalogue parcourable : le client peut lire autre chose que nos 5 suggestions.

    Sans cette page, un client ne peut cliquer que sur ce que le modèle propose déjà :
    son profil ne peut alors que se renforcer dans la direction initiale, et il n'a
    aucun moyen d'exprimer un nouvel intérêt.
    """
    clients = store.list_clients()
    if not clients:
        st.info("Inscrivez d'abord un client (onglet « Nouveau client ») pour "
                "enregistrer ses lectures.")
        return

    labels = {f"👤 {c['name']} (#{c['user_id']}, {c['reads']} lecture(s))": c["user_id"]
              for c in clients}
    user_id = labels[st.selectbox("Client", list(labels), key="browse_client")]

    ORDERS = {"Les plus lus": "popular", "Les plus récents": "recent",
              "Les plus courts": "short", "Les plus longs": "long"}
    col1, col2, col3 = st.columns([2, 1, 1])
    order_label = col1.selectbox("Trier par", list(ORDERS), key="browse_order")
    # Trier « par étoiles » reviendrait exactement au tri « Les plus lus » : les
    # étoiles sont le nombre de clics ramené à cinq classes. On offre donc un
    # filtre, qui se combine avec n'importe quel tri (ex. récents ET bien notés).
    min_stars = col2.slider("Note minimale (★)", 0, 5, 0, key="browse_min_stars")
    hide_read = col3.checkbox("Masquer les articles lus", value=True, key="browse_hide")

    if not meta and ORDERS[order_label] != "popular":
        st.warning("`articles_metadata.csv` absent : seul le tri par popularité "
                   "est disponible.")

    articles = get_sorted_articles(meta, ORDERS[order_label],
                                   tuple(int(a) for a in reco.popular_articles))

    stars, _ = get_ratings()
    if min_stars > 0:
        if stars is None:
            st.warning("`article_stars.npy` absent : filtre par note indisponible.")
        else:
            articles = [a for a in articles
                        if a < stars.size and stars[a] >= min_stars]

    already_read = set(int(a) for a in reco.user_clicks.get(int(user_id), []))
    if hide_read:
        articles = [a for a in articles if a not in already_read]

    PAGE_SIZE = 20
    pages = max(1, (len(articles) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = st.number_input(f"Page (sur {pages:,})", min_value=1, max_value=pages,
                           value=1, step=1, key="browse_page")
    start = (int(page) - 1) * PAGE_SIZE
    shown = articles[start:start + PAGE_SIZE]

    st.caption(f"{len(articles):,} article(s) — affichage {start + 1}–"
               f"{start + len(shown)}. Cliquez « Lu » sur ce que le client a lu.")

    for article_id in shown:
        row = st.columns([6, 1])
        read_marker = " ✓" if article_id in already_read else ""
        row[0].markdown(f"{describe(article_id, meta)}{read_marker}")
        if row[1].button("Lu", key=f"browse-{user_id}-{article_id}",
                         disabled=article_id in already_read):
            store.add_read(user_id, article_id)
            sync_store_into_model(reco, store)
            st.rerun()


def run(models_dir, clients_db, banniere: str | None = None,
        recommender=None, store=None) -> None:
    """Point d'entrée unique des trois solutions.

    `recommender` permet d'injecter un moteur autre que le `Recommender` local : la
    solution Azure fournit un adaptateur HTTP (`app/api_client.py`) exposant la même
    surface. L'interface ne fait alors aucune différence entre un modèle embarqué et
    un service distant.
    """
    _CTX["models_dir"] = str(models_dir)
    _CTX["clients_db"] = str(clients_db)
    _CTX["recommender"] = recommender
    # `store` permet de remplacer SQLite par Azure Table Storage : indispensable
    # dès que l'hébergement est éphémère (Space) ou partagé entre appareils.
    _CTX["store"] = store

    st.set_page_config(page_title="Ricochet — recommandation d'articles", page_icon="🎯")
    st.title("🎯 Ricochet — recommandation d'articles")
    st.caption("Suggère des articles à un lecteur à partir de ce qu'il a déjà lu.")

    if banniere:
        st.warning(banniere)

    if flash := st.session_state.pop("flash", None):
        st.success(flash)

    try:
        reco, models_dir = get_recommender()
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
        return

    store = get_store()
    meta = get_metadata(str(f) if (f := resolve_metadata_file()) else None)
    sync_store_into_model(reco, store)

    with st.sidebar:
        st.header("Système")
        # Le moteur peut être un mandataire HTTP (`app/api_client.ApiRecommender`,
        # solution Azure) : affirmer « aucun service externe » serait alors faux,
        # et contredirait la bannière affichée juste au-dessus.
        service = getattr(reco, "url", None)
        if service:
            hote = service.split("/api/")[0]
            # Formulation choisie pour lever une ambiguïté réelle : dire « aucun
            # modèle ici » se lit facilement comme « aucun modèle nulle part ».
            # Le modèle existe bel et bien — il est chargé par le service, pas
            # par cette application.
            st.caption(f"Le modèle est chargé et exécuté par le **service** "
                       f"`{hote}`. Cette application ne le contient pas : elle "
                       "lui envoie la requête et affiche la réponse.")
            latence = getattr(reco, "derniere_latence_ms", None)
            if latence is not None:
                st.caption(f"Dernier appel : {latence:.0f} ms")
            st.caption(f"Artefacts d'**affichage** : `{models_dir}` "
                       "(notes, historiques, métadonnées — pas les embeddings)")
        else:
            st.caption("Exécution locale : modèle chargé dans ce processus, "
                       "aucun service externe.")
            st.caption(f"Artefacts : `{models_dir}`")
        st.caption(f"Catalogue : {reco.n_articles:,} articles")
        st.caption(f"Clients inscrits : {len(store.list_clients())}")
        st.caption(f"Utilisateurs du jeu de données : "
                   f"{len(reco.user_clicks) - len(store.list_clients()):,}")
        st.caption(f"ALS (implicit) : {'disponible' if reco._has_cf else 'absent'}")
        st.caption(f"SVD (Surprise) : {'disponible' if reco._has_svd else 'absent'}")
        st.caption(f"Métadonnées : {'chargées' if meta else 'non trouvées'}")
        # La fenêtre peut manquer alors que le vivier est là (artefacts publiés
        # sans `recent_window.json`) : on affiche alors le vivier sans la durée.
        fenetre = reco.recent_window.get("window_hours_effective")
        if reco.popular_recent.size:
            duree = f", fenêtre {fenetre:g} h" if fenetre else ""
            st.caption(f"Fraîcheur : {reco.popular_recent.size:,} articles{duree}"
                       .replace(",", " "))
        else:
            st.caption("Fraîcheur : artefact absent — tout le catalogue")
        _stars, _ = get_ratings()
        st.caption("Notes ★ : "
                   + (f"{int((_stars > 0).sum()):,} articles notés".replace(",", " ")
                      if _stars is not None else "artefact absent"))
        origine = getattr(store, "db_path", None)
        if origine is None:
            st.caption(f"Clients : Azure Table Storage "
                       f"(`{getattr(store, 'nom_clients', 'table')}`)")
        else:
            st.caption(f"Clients : SQLite `{origine}`")

    tab_reco, tab_browse, tab_new = st.tabs(
        ["Recommandations", "Parcourir les articles", "Nouveau client"])
    with tab_reco:
        view_recommendations(reco, store, meta)
    with tab_browse:
        view_browse(reco, store, meta)
    with tab_new:
        view_new_client(reco, store, meta)
