"""Préparation hors-ligne des artefacts de recommandation.

Lit les données brutes (Globo.com) et produit dans `models/` des artefacts
légers, chargés ensuite par `Recommender` (et par l'Azure Function) :

  - articles_embeddings_pca.npy : embeddings réduits par ACP (astuce de Julien
    pour tenir dans les limites du free tier Azure) ;
  - pca_mean.npy / pca_components.npy : la projection ACP elle-même, nécessaire
    pour intégrer un **nouvel article** sans réajuster l'ACP (project_embeddings) ;
  - user_clicks.pkl             : dict user_id -> np.ndarray des article_id lus ;
  - popular_articles.npy        : article_id triés par popularité (tout l'historique) ;
  - popular_recent.npy          : popularité sur **fenêtre courte** (1 h) — le levier
    le plus fort du projet (facteur 250 sur la précision) ;
  - candidates_recent.npy       : vivier de candidats sur fenêtre plus large (6 h),
    utilisé par les stratégies personnalisées ;
  - recent_window.json          : bornes des deux fenêtres, pour dater le classement ;
  - popular_by_region.pkl       : popularité **par région**, pour un cold start
    contextuel (un nouveau lecteur reçoit ce qui marche dans sa région) ;
  - cf_*.npy / cf_*.pkl         : facteurs ALS du filtrage collaboratif.

Usage :
    python -m src.prepare_model --data-dir data/raw --out-dir models --pca 50
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import numpy as np
import pandas as pd


CLICK_COLUMNS = ["user_id", "click_article_id", "click_timestamp"]
CONTEXT_COLUMNS = ["click_region"]  # contexte exploité pour le cold start


def _read_clicks_csv(path: Path) -> pd.DataFrame:
    """Lit un CSV de clics, avec le contexte lorsqu'il est présent."""
    try:
        return pd.read_csv(path, usecols=CLICK_COLUMNS + CONTEXT_COLUMNS)
    except ValueError:
        # Fichier sans colonne de contexte : on se limite au strict nécessaire.
        return pd.read_csv(path, usecols=CLICK_COLUMNS)


def _coerce_int64(clicks: pd.DataFrame) -> pd.DataFrame:
    """Force les colonnes en entiers et écarte les lignes non numériques.

    Nécessaire car un seul fichier horaire **vide** (`clicks_hour_100.csv` dans le
    jeu Globo) suffit à faire basculer toutes les colonnes en `object` lors de la
    concaténation : pandas ne peut pas inférer de type sur zéro ligne. Les
    identifiants deviennent alors des objets Python, et toute indexation numpy
    échoue en aval.
    """
    for column in clicks.columns:
        if clicks[column].dtype != np.int64:
            clicks[column] = pd.to_numeric(clicks[column], errors="coerce")

    before = len(clicks)
    clicks = clicks.dropna()
    if len(clicks) < before:
        print(f"[clicks] {before - len(clicks):,} ligne(s) non numérique(s) écartée(s)")
    return clicks.astype(np.int64)


def load_clicks(data_dir: Path) -> pd.DataFrame:
    """Charge tous les clics depuis un dossier `clicks/` ou un CSV échantillon."""
    clicks_dir = data_dir / "clicks"
    if clicks_dir.is_dir():
        files = sorted(clicks_dir.glob("clicks_hour_*.csv"))
        if not files:
            raise FileNotFoundError(f"Aucun fichier clicks_hour_*.csv dans {clicks_dir}")
        frames = [_read_clicks_csv(f) for f in files]

        # Un fichier vide n'apporte aucune ligne mais imposerait `object` au concat.
        empty = [f.name for f, frame in zip(files, frames) if frame.empty]
        if empty:
            print(f"[clicks] {len(empty)} fichier(s) vide(s) ignoré(s) : "
                  f"{', '.join(empty[:3])}{'…' if len(empty) > 3 else ''}")
        frames = [frame for frame in frames if not frame.empty]

        return _coerce_int64(pd.concat(frames, ignore_index=True))

    sample = data_dir / "clicks_sample.csv"
    if sample.exists():
        return _coerce_int64(_read_clicks_csv(sample))

    raise FileNotFoundError(
        f"Ni {clicks_dir} ni {sample} trouvés. Voir data/README.md pour l'arborescence."
    )


def build_embeddings_pca(data_dir: Path, out_dir: Path, n_components: int) -> np.ndarray:
    """Réduit la matrice d'embeddings par ACP et sérialise **aussi la projection**.

    Trois fichiers sont produits :
      - `articles_embeddings_pca.npy` : le catalogue réduit, lu à l'inférence ;
      - `pca_mean.npy` + `pca_components.npy` : la projection elle-même.

    Sauvegarder la projection est ce qui rend l'**ajout d'un nouvel article**
    possible : on projette son embedding dans la base existante
    (`project_embeddings`). Sans elle, il faudrait réajuster l'ACP — donc changer
    de base et recalculer les vecteurs de tout le catalogue.
    """
    from sklearn.decomposition import PCA

    with open(data_dir / "articles_embeddings.pickle", "rb") as f:
        emb = pickle.load(f)
    emb = np.asarray(emb, dtype=np.float32)

    n_components = min(n_components, emb.shape[1])
    pca = PCA(n_components=n_components, random_state=42)
    reduced = pca.fit_transform(emb).astype(np.float32)

    np.save(out_dir / "articles_embeddings_pca.npy", reduced)
    np.save(out_dir / "pca_mean.npy", pca.mean_.astype(np.float32))
    np.save(out_dir / "pca_components.npy", pca.components_.astype(np.float32))
    print(f"[embeddings] {emb.shape} -> ACP {reduced.shape} "
          f"(~{reduced.nbytes / 1e6:.1f} Mo)")
    print(f"[pca] projection sauvegardée : {n_components} composantes, "
          f"{pca.explained_variance_ratio_.sum():.1%} de variance expliquée")
    return reduced


def project_embeddings(embeddings: np.ndarray, models_dir: Path) -> np.ndarray:
    """Projette des embeddings bruts (250 dim) dans l'espace ACP existant (50 dim).

    Chemin d'intégration d'un **nouvel article** : calculer son embedding, le
    projeter ici, puis l'ajouter à `articles_embeddings_pca.npy`. L'ACP n'est pas
    réajustée : la base reste celle des articles déjà en place, donc leurs vecteurs
    (et tout index construit dessus) restent valides.

    Ne dépend que de numpy — utilisable dans une fonction d'ingestion sans
    embarquer scikit-learn.
    """
    mean = np.load(models_dir / "pca_mean.npy")
    components = np.load(models_dir / "pca_components.npy")

    x = np.atleast_2d(np.asarray(embeddings, dtype=np.float32))
    if x.shape[1] != mean.size:
        raise ValueError(
            f"embeddings de dimension {x.shape[1]}, attendu {mean.size} "
            "(dimension d'origine du catalogue)"
        )
    return ((x - mean) @ components.T).astype(np.float32)


def build_user_artifacts(clicks: pd.DataFrame, out_dir: Path) -> None:
    """Construit l'historique par utilisateur et le classement de popularité."""
    # Historique de clics (ordre chronologique), dédupliqué par utilisateur.
    clicks = clicks.sort_values("click_timestamp")
    user_clicks: dict[int, np.ndarray] = {}
    for user_id, grp in clicks.groupby("user_id"):
        articles = pd.unique(grp["click_article_id"].to_numpy())
        user_clicks[int(user_id)] = articles.astype(np.int64)
    with open(out_dir / "user_clicks.pkl", "wb") as f:
        pickle.dump(user_clicks, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[user_clicks] {len(user_clicks)} utilisateurs")

    # Popularité globale (cold start).
    popular = (clicks["click_article_id"].value_counts().index.to_numpy().astype(np.int64))
    np.save(out_dir / "popular_articles.npy", popular)
    print(f"[popular_articles] {popular.size} articles classés")


def build_recent_popularity(clicks: pd.DataFrame, out_dir: Path,
                            window_hours: float = 1,
                            candidate_hours: float = 6,
                            min_articles: int = 200) -> np.ndarray:
    """Popularité sur une **fenêtre glissante**, et vivier d'articles frais.

    C'est le levier le plus fort du projet, mesuré sur découpage temporel :

        popularité sur tout l'historique  ->  HitRate@5 = 0,0010
        popularité sur la dernière heure  ->  HitRate@5 = 0,2525

    Un facteur 250 sans changer d'algorithme. La raison : 48 % des articles lus
    pendant la période évaluée n'existaient pas encore pendant l'entraînement. Un
    classement sur tout l'historique noie les nouveautés ; une fenêtre courte les
    capte.

    Produit deux artefacts :
      - `popular_recent.npy`  : article_id de la fenêtre, du plus lu au moins lu.
        Sert à la fois de repli cold start et de **vivier de candidats** pour les
        autres stratégies ;
      - `recent_window.json`  : bornes et taille de la fenêtre, pour savoir de quand
        date le classement servi.

    ⚠️ Un artefact de fraîcheur périme. Servi deux jours plus tard, il redescend à
    0,0000 — mesuré. En production, la fenêtre se recalcule à intervalle régulier
    (§4.f de docs/architecture.md).
    """
    import json

    horodatages = clicks["click_timestamp"]

    # L'ancre n'est **pas** le dernier clic : le jeu Globo contient des horodatages
    # aberrants — 99,9 % des clics s'arrêtent 665 h avant le dernier, et il ne reste
    # que 76 clics dans les 480 dernières heures. Ancrer sur le maximum donnerait une
    # fenêtre vide. On prend donc un quantile élevé comme « instant présent ».
    ancre = int(horodatages.quantile(0.999))
    aberrants = int((horodatages > ancre).sum())

    # Élargissement automatique : une fenêtre trop étroite ne peut pas remplir un
    # top-n, et un classement de trois articles n'est pas un classement.
    heures = float(window_hours)
    while True:
        fenetre = clicks[(horodatages >= ancre - heures * 3600 * 1000)
                         & (horodatages <= ancre)]
        ordre = (fenetre["click_article_id"].value_counts().index
                 .to_numpy().astype(np.int64))
        if ordre.size >= min_articles or heures >= 24 * 30:
            break
        heures *= 2

    np.save(out_dir / "popular_recent.npy", ordre)

    # Seconde fenêtre, plus large : le **vivier de candidats** des stratégies
    # personnalisées. Les deux optima mesurés diffèrent — 1 h pour le classement
    # par popularité (0,2190), 6 h pour le contenu (0,0405, contre 0,0255 sur 1 h) :
    # une fenêtre étroite prive le contenu de candidats à départager.
    heures_vivier = max(heures, candidate_hours)
    vivier_clics = clicks[(horodatages >= ancre - heures_vivier * 3600 * 1000)
                          & (horodatages <= ancre)]
    vivier = (vivier_clics["click_article_id"].value_counts().index
              .to_numpy().astype(np.int64))
    np.save(out_dir / "candidates_recent.npy", vivier)

    meta = {"window_hours_demandee": window_hours,
            "window_hours_effective": heures,
            "candidate_hours": heures_vivier,
            "ancre_ms": ancre, "debut_ms": int(ancre - heures * 3600 * 1000),
            "clics_fenetre": int(len(fenetre)),
            "articles_fenetre": int(ordre.size),
            "articles_vivier": int(vivier.size),
            "clics_aberrants_ecartes": aberrants}
    (out_dir / "recent_window.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[popular_recent] vivier de candidats {heures_vivier:g} h : "
          f"{vivier.size:,} articles")
    print(f"[popular_recent] fenêtre {heures:g} h "
          f"{'(élargie depuis ' + format(window_hours, 'g') + ' h)' if heures != window_hours else ''}"
          f" : {ordre.size:,} articles, {len(fenetre):,} clics")
    if aberrants:
        print(f"[popular_recent] {aberrants} clic(s) au-delà de l'ancre écarté(s) "
              "(horodatages aberrants)")
    return ordre


def build_article_stars(clicks: pd.DataFrame, out_dir: Path,
                        max_stars: int = 5) -> np.ndarray:
    """Note en étoiles de chaque article, déduite du nombre de clics reçus.

    Tout l'historique (≈ 3 M de clics) est distillé en **un octet par article** :
    l'artefact pèse ~0,4 Mo là où les données dont il est issu pèsent des dizaines
    de Mo. C'est ce qui permet de servir une note sans embarquer l'historique.

    L'échelle est **logarithmique** :

        1★ : 1-9 clics      3★ : 100-999 clics      5★ : 10 000+ clics
        2★ : 10-99 clics    4★ : 1 000-9 999 clics

    Pourquoi pas des quantiles : la distribution suit une loi de puissance (de 1 à
    37 213 clics) et sa médiane vaut 1. Les bornes de quintiles tombent sur
    [1, 1, 1, 2, 11] — quatre bornes sur cinq sur la même valeur, donc des classes
    indiscernables. Le logarithme, lui, répartit les articles de façon lisible.

    0 étoile signifie « jamais cliqué » (318 k articles du catalogue).
    """
    counts = clicks["click_article_id"].value_counts()

    catalogue = out_dir / "articles_embeddings_pca.npy"
    if catalogue.exists():
        n_articles = int(np.load(catalogue, mmap_mode="r").shape[0])
    else:
        n_articles = int(counts.index.max()) + 1

    article_clicks = np.zeros(n_articles, dtype=np.int32)
    ids = counts.index.to_numpy().astype(np.int64)
    inside = ids < n_articles
    article_clicks[ids[inside]] = counts.to_numpy()[inside]

    stars = np.zeros(n_articles, dtype=np.int8)
    clicked = article_clicks > 0
    stars[clicked] = np.clip(1 + np.floor(np.log10(article_clicks[clicked])),
                             1, max_stars).astype(np.int8)

    np.save(out_dir / "article_clicks.npy", article_clicks)
    np.save(out_dir / "article_stars.npy", stars)

    spread = " · ".join(f"{s}★:{int((stars == s).sum()):,}" for s in range(1, max_stars + 1))
    print(f"[article_stars] {int(clicked.sum()):,} articles notés — {spread}")
    print(f"[article_stars] artefacts ~{(stars.nbytes + article_clicks.nbytes) / 1e6:.1f} Mo")
    return stars


def build_segment_popularity(clicks: pd.DataFrame, out_dir: Path,
                             min_clicks: int = 30) -> None:
    """Classement de popularité **par région**, pour un cold start contextuel.

    Sans contexte, tout nouveau lecteur reçoit le même top-5 mondial. Avec la
    région, il reçoit ce que lisent les lecteurs de sa région — la seule
    information disponible sur un utilisateur dont on ne sait rien d'autre.

    `min_clicks` écarte les régions trop peu représentées : un classement établi
    sur une poignée de clics est du bruit, mieux vaut retomber sur le global.
    Les régions sont des codes anonymisés (entiers) : c'est le système qui segmente,
    aucun libellé n'est nécessaire.
    """
    if "click_region" not in clicks.columns:
        print("[popular_by_region] colonne click_region absente -> ignoré")
        return

    by_region: dict[int, np.ndarray] = {}
    skipped = 0
    for region, group in clicks.groupby("click_region"):
        if len(group) < min_clicks:
            skipped += 1
            continue
        ranking = group["click_article_id"].value_counts().index.to_numpy().astype(np.int64)
        by_region[int(region)] = ranking

    with open(out_dir / "popular_by_region.pkl", "wb") as f:
        pickle.dump(by_region, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[popular_by_region] {len(by_region)} région(s) retenue(s) "
          f"(≥ {min_clicks} clics), {skipped} écartée(s)")


def build_collaborative(clicks: pd.DataFrame, out_dir: Path, factors: int) -> None:
    """Entraîne un modèle ALS (feedback implicite) et sauvegarde les facteurs."""
    try:
        from implicit.als import AlternatingLeastSquares
    except ImportError:
        print("[collab] 'implicit' non installé -> filtrage collaboratif ignoré.")
        return

    from scipy.sparse import coo_matrix

    # Encodage dense des identifiants (les article_id/user_id sont creux).
    user_ids = clicks["user_id"].astype(np.int64)
    item_ids = clicks["click_article_id"].astype(np.int64)

    uniq_users, u_idx = np.unique(user_ids, return_inverse=True)
    uniq_items, i_idx = np.unique(item_ids, return_inverse=True)

    # Matrice user x item, valeur = nombre de clics (confiance implicite).
    data = np.ones(len(clicks), dtype=np.float32)
    ui = coo_matrix((data, (u_idx, i_idx)),
                    shape=(uniq_users.size, uniq_items.size)).tocsr()

    # ALS parallélise déjà ses itérations : laisser OpenBLAS ouvrir en plus son
    # propre pool de threads dégrade fortement les performances (implicit émet un
    # avertissement explicite à ce sujet). On borne BLAS à 1 thread pendant
    # l'entraînement — la borne doit englober la **construction** du modèle, car
    # c'est là qu'implicit contrôle la configuration BLAS.
    try:
        from threadpoolctl import threadpool_limits
        blas_limit = threadpool_limits(1, "blas")
    except ImportError:  # threadpoolctl absent : on entraîne sans borne
        from contextlib import nullcontext
        blas_limit = nullcontext()

    with blas_limit:
        model = AlternatingLeastSquares(factors=factors, regularization=0.05,
                                        iterations=15, random_state=42)
        model.fit(ui)

    np.save(out_dir / "cf_user_factors.npy", model.user_factors.astype(np.float32))
    np.save(out_dir / "cf_item_factors.npy", model.item_factors.astype(np.float32))
    np.save(out_dir / "cf_item_ids.npy", uniq_items)  # colonne -> article_id
    user_index = {int(uid): int(row) for row, uid in enumerate(uniq_users)}
    with open(out_dir / "cf_user_index.pkl", "wb") as f:
        pickle.dump(user_index, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[collab] ALS entraîné : {uniq_users.size} users x {uniq_items.size} items, "
          f"{factors} facteurs")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/raw", type=Path)
    parser.add_argument("--out-dir", default="models", type=Path)
    parser.add_argument("--pca", default=50, type=int, help="dimensions après ACP")
    parser.add_argument("--factors", default=50, type=int, help="facteurs latents ALS")
    parser.add_argument("--window-hours", default=1, type=float,
                        help="fenêtre du classement par popularité (optimum mesuré : 1 h)")
    parser.add_argument("--candidate-hours", default=6, type=float,
                        help="fenêtre du vivier de candidats des stratégies "
                             "personnalisées (optimum mesuré : 6 h)")
    parser.add_argument("--min-region-clicks", default=30, type=int,
                        help="clics minimum pour retenir une région (cold start contextuel)")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    build_embeddings_pca(args.data_dir, args.out_dir, args.pca)
    clicks = load_clicks(args.data_dir)
    print(f"[clicks] {len(clicks):,} interactions chargées")
    build_user_artifacts(clicks, args.out_dir)
    build_recent_popularity(clicks, args.out_dir, args.window_hours,
                            args.candidate_hours)
    build_article_stars(clicks, args.out_dir)
    build_segment_popularity(clicks, args.out_dir, args.min_region_clicks)
    build_collaborative(clicks, args.out_dir, args.factors)
    print("\nArtefacts prêts dans", args.out_dir.resolve())


if __name__ == "__main__":
    main()
