"""Évaluation avec découpage **temporel** 60 / 20 / 20.

Pourquoi temporel et non aléatoire : le jeu est un flux d'actualité. Un découpage
aléatoire laisserait le modèle apprendre des clics postérieurs à ceux qu'il doit
prédire — il « verrait le futur ». On coupe donc sur `click_timestamp` :

    | 60 % entraînement | 20 % validation | 20 % test |
    t0 -------------- t60 ------------ t80 ---------- tfin

Ce que cela corrige par rapport à l'évaluation précédente : les artefacts
(historique, popularité, étoiles, facteurs ALS et SVD) sont construits **uniquement
sur la période d'entraînement**. Auparavant tout était appris sur 100 % des données
puis évalué sur ces mêmes données : les scores étaient gonflés par cette fuite.

L'ACP fait exception : elle ne dépend que des embeddings d'articles, jamais des
clics. Elle est donc reprise telle quelle, sans fuite possible.

Usage :
    python -m src.evaluate --data-dir data/news-portal-user --out-dir models_split
    python -m src.evaluate --out-dir models_split --skip-build --split test
"""

from __future__ import annotations

import argparse
import itertools
import shutil
from pathlib import Path

import numpy as np
import pandas as pd


def split_by_time(clicks: pd.DataFrame, train: float = 0.6, val: float = 0.2
                  ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Découpe les clics en trois périodes successives selon leur horodatage."""
    clicks = clicks.sort_values("click_timestamp", kind="mergesort")
    n = len(clicks)
    i_train, i_val = int(n * train), int(n * (train + val))

    parts = (clicks.iloc[:i_train], clicks.iloc[i_train:i_val], clicks.iloc[i_val:])
    borne_1 = int(clicks["click_timestamp"].iloc[i_train])
    borne_2 = int(clicks["click_timestamp"].iloc[i_val])
    print(f"[split] entraînement {len(parts[0]):,} | validation {len(parts[1]):,} "
          f"| test {len(parts[2]):,}")
    print(f"[split] bornes temporelles : t60={borne_1} t80={borne_2}")
    return parts


def build_artifacts(clicks_train: pd.DataFrame, source_models: Path, out_dir: Path,
                    factors: int = 50, with_svd: bool = True) -> None:
    """Construit tous les artefacts à partir de la **seule** période d'entraînement."""
    from src.prepare_model import (build_article_stars, build_collaborative,
                                   build_segment_popularity, build_user_artifacts)

    out_dir.mkdir(parents=True, exist_ok=True)

    for nom in ("articles_embeddings_pca.npy", "pca_mean.npy", "pca_components.npy"):
        source = source_models / nom
        if not source.exists():
            raise FileNotFoundError(
                f"{source} manquant. Lancez d'abord :\n"
                "  python -m src.prepare_model --data-dir <data> --out-dir models")
        if not (out_dir / nom).exists():
            shutil.copy2(source, out_dir / nom)
    print(f"[acp] artefacts d'embeddings repris depuis {source_models}")

    build_user_artifacts(clicks_train, out_dir)
    build_article_stars(clicks_train, out_dir)
    build_segment_popularity(clicks_train, out_dir)
    build_collaborative(clicks_train, out_dir, factors)

    if with_svd:
        from src.collaborative_surprise import (build_ratings_from_stars,
                                                save_artifacts, train_svd)
        notes = build_ratings_from_stars(clicks_train, out_dir)
        algo, trainset = train_svd(notes, n_factors=factors, n_epochs=20)
        save_artifacts(algo, trainset, out_dir)


def evaluate(models_dir: Path, clicks_eval: pd.DataFrame, n: int = 5,
             max_users: int = 2000) -> pd.DataFrame:
    """Mesure chaque stratégie sur une période **postérieure** à l'entraînement.

    Vérité terrain : les articles réellement cliqués pendant la période d'évaluation
    par un lecteur déjà connu de la période d'entraînement.
    """
    from src.recommender import Recommender

    reco = Recommender(models_dir)

    cible = (clicks_eval.groupby("user_id")["click_article_id"]
             .apply(lambda s: {int(a) for a in s}))
    connus = [u for u in cible.index if int(u) in reco.user_clicks][:max_users]
    print(f"[eval] {len(connus):,} lecteurs évalués "
          f"(connus à l'entraînement et actifs ensuite)")

    strategies = {
        "hybrid": lambda u, k: reco.recommend(u, n=k, method="hybrid"),
        "content": lambda u, k: reco.recommend(u, n=k, method="content"),
        "collab (ALS)": lambda u, k: reco.recommend(u, n=k, method="collab"),
        "svd (Surprise)": lambda u, k: reco.recommend(u, n=k, method="svd"),
        "popularité": lambda u, k: reco._popularity_fallback(u, k),
    }

    lignes = []
    for nom, fonction in strategies.items():
        succes = rappel = 0.0
        listes = []
        for u in connus:
            attendu = cible[u]
            recs = fonction(int(u), n)
            trouves = len(attendu & set(recs))
            succes += trouves > 0
            rappel += trouves / len(attendu)
            listes.append(set(recs))

        couverture = len({a for liste in listes for a in liste}) / reco.n_articles
        paires = list(itertools.islice(itertools.combinations(range(len(listes)), 2), 3000))
        recouvrement = float(np.mean([len(listes[i] & listes[j]) / n for i, j in paires]))
        lignes.append({"stratégie": nom,
                       f"HitRate@{n}": round(succes / len(connus), 4),
                       f"Recall@{n}": round(rappel / len(connus), 4),
                       "couverture %": round(couverture * 100, 3),
                       "personnalisation %": round((1 - recouvrement) * 100, 1)})
    return pd.DataFrame(lignes).set_index("stratégie")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=Path("data/news-portal-user"), type=Path)
    parser.add_argument("--source-models", default=Path("models"), type=Path,
                        help="dossier contenant l'ACP déjà calculée")
    parser.add_argument("--out-dir", default=Path("models_split"), type=Path)
    parser.add_argument("--split", default="val", choices=["val", "test"],
                        help="période d'évaluation (garder « test » pour la mesure finale)")
    parser.add_argument("--n", default=5, type=int)
    parser.add_argument("--factors", default=50, type=int)
    parser.add_argument("--max-users", default=2000, type=int)
    parser.add_argument("--skip-build", action="store_true",
                        help="réutiliser les artefacts déjà construits")
    parser.add_argument("--no-svd", action="store_true")
    args = parser.parse_args()

    from src.prepare_model import load_clicks

    clicks = load_clicks(args.data_dir)
    print(f"[clicks] {len(clicks):,} interactions")
    train, val, test = split_by_time(clicks)

    if not args.skip_build:
        build_artifacts(train, args.source_models, args.out_dir,
                        factors=args.factors, with_svd=not args.no_svd)

    evaluation = val if args.split == "val" else test
    print(f"\n=== évaluation sur la période « {args.split} » ===")
    resultats = evaluate(args.out_dir, evaluation, n=args.n, max_users=args.max_users)
    print()
    print(resultats.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
