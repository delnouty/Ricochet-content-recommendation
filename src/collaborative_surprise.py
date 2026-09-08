"""Filtrage collaboratif par SVD (bibliothèque Surprise) — entraînement hors-ligne.

Surprise attend des **notes explicites**. Les données Globo n'en contiennent pas :
on dérive donc une note du nombre de clics d'un utilisateur sur un article, borné
à `max_rating`. Sur le jeu complet, 37 471 paires (utilisateur, article) sont
répétées (2 à 33 clics), ce qui donne une échelle exploitable — même si la grande
majorité des paires reste à 1.

Surprise n'est utilisée qu'ici, à l'entraînement. On sérialise ensuite les
**facteurs appris** (`pu`, `qi`, biais, moyenne globale), si bien que l'inférence
reste en numpy pur : ni `Recommender`, ni l'Azure Function, ni les Spaces
n'embarquent Surprise. Le score d'un couple se reconstitue exactement comme le
fait Surprise :

    note_estimée = µ + biais_utilisateur + biais_article + pu · qi

Artefacts produits dans `models/` :
  - svd_user_factors.npy / svd_item_factors.npy : facteurs latents ;
  - svd_user_bias.npy / svd_item_bias.npy       : biais ;
  - svd_global_mean.npy                          : µ (tableau à un élément) ;
  - svd_user_index.pkl                           : user_id -> ligne ;
  - svd_item_ids.npy                             : colonne -> article_id.

Usage :
    python -m src.collaborative_surprise --data-dir data/news-portal-user \
        --out-dir models --factors 50 --epochs 20
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import numpy as np
import pandas as pd


def build_ratings(clicks: pd.DataFrame, max_rating: int = 5) -> pd.DataFrame:
    """Convertit les clics en notes : nombre de clics par couple, borné.

    Une note de 1 signifie « lu une fois », 5 « lu au moins cinq fois ». C'est un
    signal faible — 98,9 % des couples restent à 1 — mais c'est la seule notion
    d'intensité que portent les données.

    ⚠️  Ces notes seules ne suffisent **pas** à ranger des articles : elles ne
    contiennent que des exemples positifs. Un modèle ajusté dessus n'apprend jamais
    qu'un article non lu doit obtenir un score plus faible, et son classement est
    alors arbitraire. Voir `add_negative_samples`.
    """
    counts = (clicks.groupby(["user_id", "click_article_id"])
              .size()
              .clip(upper=max_rating)
              .reset_index(name="rating"))
    counts.columns = ["user_id", "article_id", "rating"]
    return counts


def build_ratings_from_stars(clicks: pd.DataFrame, models_dir: Path) -> pd.DataFrame:
    """Notes issues des **étoiles de l'article** (`article_stars.npy`).

    Séquence : `prepare_model.build_article_stars` calcule d'abord une note en
    étoiles par article à partir de tout l'historique de clics ; on l'attache
    ensuite à chaque couple (utilisateur, article) lu. Surprise reçoit alors une
    véritable échelle 1–5, celle qu'attendent les modèles de prédiction de notes.

    Conséquence à garder en tête : la note ne dépend que de l'article, pas du
    lecteur. Deux personnes qui lisent le même article lui donnent la même note.
    Le modèle apprend donc surtout *quels articles sont lus*, et la personnalisation
    ne peut venir que des couples qu'un lecteur a réellement ouverts.
    """
    stars_file = models_dir / "article_stars.npy"
    if not stars_file.exists():
        raise FileNotFoundError(
            f"{stars_file} absent. Générez d'abord les étoiles :\n"
            "  python -m src.prepare_model --data-dir <data> --out-dir models"
        )
    stars = np.load(stars_file)

    pairs = clicks[["user_id", "click_article_id"]].drop_duplicates()
    pairs.columns = ["user_id", "article_id"]
    inside = pairs["article_id"].to_numpy() < stars.size
    pairs = pairs[inside]

    pairs = pairs.assign(rating=stars[pairs["article_id"].to_numpy()].astype(int))
    pairs = pairs[pairs["rating"] > 0]   # 0 = jamais cliqué : ne peut pas arriver ici

    spread = pairs["rating"].value_counts().sort_index()
    print(f"[notes] {len(pairs):,} couples notés à partir des étoiles — "
          + " · ".join(f"{int(k)}★:{v:,}" for k, v in spread.items()))
    return pairs


def add_negative_samples(ratings: pd.DataFrame, negatives_per_positive: int = 1,
                         random_state: int = 42) -> pd.DataFrame:
    """Ajoute des exemples négatifs : articles **non lus**, notés 0.

    C'est ce qui rend un modèle de prédiction de notes utilisable pour du
    classement. Sans négatifs, il n'existe aucun contraste entre « lu » et
    « non lu » ; avec eux, la tâche devient comparable à celle que résout l'ALS
    (qui traite implicitement toute case vide comme un négatif de faible confiance).

    Les négatifs sont tirés parmi les articles **déjà cliqués par quelqu'un** : le
    modèle est ainsi évalué sur le même vivier de candidats que l'ALS, et non sur
    les 318 k articles que personne n'a jamais ouverts.

    Les notes deviennent binaires (0 = non lu, 1 = lu) : mélanger une intensité
    1–5 et un 0 fabriquerait une échelle dont les écarts n'ont pas de sens.
    """
    rng = np.random.default_rng(random_state)

    positives = ratings[["user_id", "article_id"]].copy()
    positives["rating"] = 1

    pool = ratings["article_id"].unique()
    seen = set(zip(ratings["user_id"].to_numpy(), ratings["article_id"].to_numpy()))

    users = np.repeat(positives["user_id"].to_numpy(), negatives_per_positive)
    candidates = rng.choice(pool, size=users.size, replace=True)

    # Un tirage peut tomber sur un article déjà lu : on écarte ces couples plutôt
    # que de boucler jusqu'à trouver un négatif (le biais introduit est négligeable
    # à cette densité, et le coût d'un rejet est nul).
    keep = [(u, a) not in seen for u, a in zip(users, candidates)]
    negatives = pd.DataFrame({"user_id": users[keep], "article_id": candidates[keep],
                              "rating": 0})
    negatives = negatives.drop_duplicates(["user_id", "article_id"])

    out = pd.concat([positives, negatives], ignore_index=True)
    print(f"[notes] {len(positives):,} positifs + {len(negatives):,} négatifs "
          f"= {len(out):,} exemples")
    return out


def train_svd(ratings: pd.DataFrame, n_factors: int = 50, n_epochs: int = 20,
              max_rating: int = 5, random_state: int = 42):
    """Entraîne un SVD Surprise sur l'ensemble des notes. Renvoie (algo, trainset).

    L'échelle est déduite des notes fournies : (0, 1) après ajout de négatifs,
    (1, max_rating) si l'on passe les intensités de clics brutes.
    """
    from surprise import SVD, Dataset, Reader

    low, high = int(ratings["rating"].min()), int(ratings["rating"].max())
    reader = Reader(rating_scale=(low, max(high, low + 1)))
    data = Dataset.load_from_df(ratings[["user_id", "article_id", "rating"]], reader)
    trainset = data.build_full_trainset()

    algo = SVD(n_factors=n_factors, n_epochs=n_epochs, random_state=random_state)
    algo.fit(trainset)
    return algo, trainset


def extract_factors(algo, trainset) -> dict:
    """Facteurs appris, sous la forme exacte que `Recommender` attend.

    Extrait ici plutôt que dans `save_artifacts` parce que deux appelants en ont
    besoin : la sérialisation vers `models/`, et l'évaluation, qui ré-entraîne le
    SVD sur l'historique de la mesure et n'a aucune raison d'écrire 60 Mo sur le
    disque pour les relire aussitôt.
    """
    # Surprise indexe en interne ; on rétablit les identifiants d'origine.
    return {
        "svd_user_factors": np.asarray(algo.pu, dtype=np.float32),
        "svd_item_factors": np.asarray(algo.qi, dtype=np.float32),
        "svd_user_bias": np.asarray(algo.bu, dtype=np.float32),
        "svd_item_bias": np.asarray(algo.bi, dtype=np.float32),
        "svd_global_mean": float(trainset.global_mean),
        "svd_item_ids": np.array(
            [int(trainset.to_raw_iid(i)) for i in range(trainset.n_items)],
            dtype=np.int64),
        "svd_user_index": {int(trainset.to_raw_uid(i)): i
                           for i in range(trainset.n_users)},
    }


def save_artifacts(algo, trainset, out_dir: Path) -> None:
    """Sérialise les facteurs appris pour une inférence numpy-only."""
    n_users = trainset.n_users
    n_items = trainset.n_items
    facteurs = extract_factors(algo, trainset)

    for nom in ("svd_user_factors", "svd_item_factors", "svd_user_bias",
                "svd_item_bias", "svd_item_ids"):
        np.save(out_dir / f"{nom}.npy", facteurs[nom])
    np.save(out_dir / "svd_global_mean.npy",
            np.array([facteurs["svd_global_mean"]], dtype=np.float32))
    with open(out_dir / "svd_user_index.pkl", "wb") as f:
        pickle.dump(facteurs["svd_user_index"], f,
                    protocol=pickle.HIGHEST_PROTOCOL)

    total = sum((out_dir / n).stat().st_size for n in (
        "svd_user_factors.npy", "svd_item_factors.npy", "svd_user_bias.npy",
        "svd_item_bias.npy", "svd_global_mean.npy", "svd_item_ids.npy",
        "svd_user_index.pkl"))
    print(f"[svd] {n_users:,} users x {n_items:,} items, "
          f"{algo.pu.shape[1]} facteurs, ~{total / 1e6:.1f} Mo d'artefacts")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default="data/raw", type=Path)
    parser.add_argument("--out-dir", default="models", type=Path)
    parser.add_argument("--factors", default=50, type=int)
    parser.add_argument("--epochs", default=20, type=int)
    parser.add_argument("--max-rating", default=5, type=int,
                        help="borne haute de la note (nombre de clics)")
    parser.add_argument("--negatives", default=0, type=int,
                        help="exemples négatifs par positif (0 = aucun)")
    parser.add_argument("--rating", default="stars", choices=["stars", "clicks"],
                        help="source de la note : 'stars' = étoiles de l'article "
                             "(article_stars.npy, échelle 1-5) ; 'clicks' = nombre "
                             "de clics du couple, borné")
    args = parser.parse_args()

    from src.prepare_model import load_clicks

    args.out_dir.mkdir(parents=True, exist_ok=True)

    clicks = load_clicks(args.data_dir)
    print(f"[clicks] {len(clicks):,} interactions")

    if args.rating == "stars":
        ratings = build_ratings_from_stars(clicks, args.out_dir)
    else:
        ratings = build_ratings(clicks, args.max_rating)
        spread = ratings["rating"].value_counts().sort_index()
        print(f"[notes] {len(ratings):,} couples notés — répartition : "
              + ", ".join(f"{int(k)}★:{v:,}" for k, v in spread.items()))

    if args.negatives > 0:
        ratings = add_negative_samples(ratings, args.negatives)
    else:
        print("[notes] aucun négatif : le modèle ne pourra pas classer les articles")

    algo, trainset = train_svd(ratings, args.factors, args.epochs, args.max_rating)
    save_artifacts(algo, trainset, args.out_dir)
    print("\nArtefacts SVD prêts dans", args.out_dir.resolve())


if __name__ == "__main__":
    main()
