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
                    factors: int = 50, with_svd: bool = True,
                    svd_negatives: int = 4) -> None:
    """Construit tous les artefacts à partir de la **seule** période d'entraînement.

    `svd_negatives` fixe la variante de note du SVD, et ce choix n'est pas neutre :
    le notebook 06 a comparé trois définitions et deux échouent. Les étoiles de
    l'article (note identique pour tous les lecteurs) donnent 0,0000 en HitRate@5,
    parce que le modèle apprend « quels articles sont lus », pas « par qui ». Seule
    la variante binaire avec négatifs échantillonnés classe : 4 négatifs par
    positif donnent 0,0755 sur validation.

    Cette fonction construisait auparavant la variante « étoiles », c'est-à-dire
    celle que l'étude rejette. La mesure de référence rapportait donc 0,0000 pour
    le SVD — un chiffre exact pour un modèle que personne n'aurait déployé.
    Mettre 0 ici reproduit cet ancien comportement.
    """
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
        from src.collaborative_surprise import (add_negative_samples,
                                                build_ratings,
                                                build_ratings_from_stars,
                                                save_artifacts, train_svd)
        if svd_negatives > 0:
            # Variante retenue : positifs issus des clics, ramenés au binaire par
            # l'ajout de négatifs (articles non lus, note 0).
            notes = add_negative_samples(build_ratings(clicks_train),
                                         svd_negatives)
        else:
            notes = build_ratings_from_stars(clicks_train, out_dir)
        algo, trainset = train_svd(notes, n_factors=factors, n_epochs=20)
        save_artifacts(algo, trainset, out_dir)


def evaluate(models_dir: Path, clicks_history: pd.DataFrame, clicks_eval: pd.DataFrame,
             n: int = 5, max_users: int = 2000, pop_hours: float = 1,
             content_hours: float = 6, als_hours: float = 24,
             als_factors: int = 16) -> pd.DataFrame:
    """Mesure chaque stratégie sur une période **postérieure** à l'historique fourni.

    Deux règles de protocole, établies par les notebooks 03 à 07 :

    1. **Le vivier de candidats est recalculé à partir de `clicks_history`**, c'est-à-
       dire tout ce qui précède la période évaluée. Un vivier gelé à la fin de
       l'entraînement est périmé et donne 0,0000 pour toutes les méthodes — mesuré.
    2. **Chaque méthode reçoit sa meilleure configuration** (fenêtres et facteurs
       réglés sur la validation). Comparer une méthode réglée à des méthodes par
       défaut fausse la conclusion.

    Les valeurs par défaut sont les optima mesurés sur la **validation** :
    popularité sur 1 h, contenu sur un vivier de 6 h, ALS entraîné sur 24 h avec
    16 facteurs.

    Pourquoi 24 h et non 72 h. Les notebooks 05 et 07 ont balayé les deux réglages
    de l'ALS **séparément** : la fenêtre à 50 facteurs (72 h : 0,0200 contre 0,0175
    à 24 h), puis les facteurs à 24 h (16 : 0,0345 contre 0,0175 à 50). Combiner
    les deux gagnants — 72 h et 16 facteurs — paraissait naturel. Le balayage
    croisé sur validation montre que non : les deux effets interagissent, et cette
    combinaison est la **pire** des quatre.

    | fenêtre | facteurs | HitRate@5 (validation) |
    |---|---|---|
    | 24 h | 16 | **0,0345** |
    | 72 h | 50 | 0,0200 |
    | 24 h | 50 | 0,0175 |
    | 72 h | 16 | 0,0110 |

    Lecture : un modèle petit (16 facteurs) a besoin d'un signal dense pour placer
    ses facteurs ; l'élargissement à 72 h dilue les co-lectures sur trois fois plus
    d'articles et lui retire cette densité. La configuration se choisit donc en
    croisant les réglages, jamais en juxtaposant des optima partiels.
    """
    from src import experiments as xp
    from src.recommender import Recommender

    reco = Recommender(models_dir)

    # Les profils doivent inclure tout l'historique disponible, pas seulement la
    # période d'entraînement des artefacts.
    for user_id, articles in clicks_history.groupby("user_id")["click_article_id"]:
        nouveaux = articles.to_numpy(dtype=np.int64)
        ancien = reco.user_clicks.get(int(user_id))
        reco.user_clicks[int(user_id)] = (nouveaux if ancien is None
                                         else np.unique(np.concatenate([ancien, nouveaux])))

    pool_pop = xp.recent_pool(clicks_history, pop_hours)
    pool = xp.recent_pool(clicks_history, content_hours)
    print(f"[eval] vivier popularité {pool_pop.size:,} articles ({pop_hours} h) | "
          f"vivier contenu {pool.size:,} articles ({content_hours} h)")

    users, cible = xp.eval_users(reco, clicks_eval, max_users=max_users)
    print(f"[eval] {len(users):,} lecteurs évalués (connus et actifs ensuite)")

    popularite = xp.make_popularity(pool_pop, reco)
    contenu = xp.make_content(reco, pool, last_k=None)
    als = xp.train_als_window(clicks_history, als_hours,
                          factors=als_factors)(pool, reco)

    strategies = {
        f"popularité {pop_hours} h": popularite,
        f"contenu (vivier {content_hours} h)": contenu,
        f"ALS ({als_hours} h, {als_factors} facteurs)": als,
        "mixte 4 popularité + 1 contenu": xp.make_mix(popularite, contenu, 1),
    }
    if reco._has_svd:
        strategies["SVD (Surprise)"] = xp.make_svd(reco, pool)

    return xp.compare(strategies, users, cible, n=n, n_articles=reco.n_articles)


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
    # Réglages de l'ALS exposés en ligne de commande : sans eux, la configuration
    # présentée en soutenance (72 h) n'était pas reproductible sans modifier le
    # code, et le chiffre du rapport n'aurait pas eu de commande pour le refaire.
    parser.add_argument("--als-hours", default=24, type=float,
                        help="fenêtre d'entraînement de l'ALS, en heures "
                             "(défaut 24 : optimum du balayage croisé sur validation)")
    parser.add_argument("--als-factors", default=16, type=int,
                        help="nombre de facteurs latents de l'ALS "
                             "(défaut 16 : optimum mesuré sur validation)")
    parser.add_argument("--max-users", default=2000, type=int)
    parser.add_argument("--skip-build", action="store_true",
                        help="réutiliser les artefacts déjà construits")
    parser.add_argument("--no-svd", action="store_true")
    parser.add_argument("--json", type=Path,
                        help="écrire les métriques dans ce fichier (porte de qualité CI)")
    parser.add_argument("--track", action="store_true",
                        help="enregistrer les résultats dans MLflow")
    parser.add_argument("--experiment", default="ricochet-evaluation",
                        help="nom de l'expérience MLflow")
    parser.add_argument("--register", metavar="NOM",
                        help="versionner les artefacts dans le registre MLflow "
                             "sous ce nom (ex. ricochet-artefacts)")
    args = parser.parse_args()

    from src.prepare_model import load_clicks

    clicks = load_clicks(args.data_dir)
    print(f"[clicks] {len(clicks):,} interactions")
    train, val, test = split_by_time(clicks)

    if not args.skip_build:
        build_artifacts(train, args.source_models, args.out_dir,
                        factors=args.factors, with_svd=not args.no_svd)

    # Historique disponible au moment de l'évaluation : tout ce qui la précède.
    # Pour le test, la validation est déjà du passé — l'utiliser n'est pas une fuite,
    # c'est ce que fait un service en production au moment de répondre.
    if args.split == "val":
        evaluation, historique = val, train
    else:
        evaluation, historique = test, pd.concat([train, val], ignore_index=True)

    print(f"\n=== évaluation sur la période « {args.split} » "
          f"({len(historique):,} clics d'historique) ===")
    resultats = evaluate(args.out_dir, historique, evaluation, n=args.n,
                         max_users=args.max_users,
                         als_hours=args.als_hours, als_factors=args.als_factors)
    print()
    print(resultats.to_string())

    contexte = {"split": args.split, "n": args.n, "factors": args.factors,
                "clics_entrainement": len(train), "clics_evaluation": len(evaluation),
                "lecteurs_max": args.max_users}

    if args.track:
        from src import tracking
        runs = tracking.log_comparison(args.experiment, resultats,
                                       params_communs=contexte,
                                       tags={"split": args.split})
        if runs:
            print(f"\n[mlflow] {len(runs)} essai(s) enregistré(s) dans "
                  f"l'expérience « {args.experiment} »")

    if args.register:
        from src import tracking
        colonne_hr = f"HitRate@{args.n}"
        meilleure_ligne = resultats.loc[resultats[colonne_hr].idxmax()]
        tracking.register_artifacts(
            args.register, args.out_dir,
            metrics={k: float(v) for k, v in meilleure_ligne.items()},
            params={**contexte, "strategie": str(resultats[colonne_hr].idxmax())},
            tags={"split": args.split})

    if args.json:
        import json as _json

        # La porte de qualité surveille la **meilleure** stratégie du tableau : c'est
        # celle qui serait déployée. Suivre une moyenne masquerait une régression sur
        # la seule configuration qui compte.
        colonne = f"HitRate@{args.n}"
        meilleure = resultats[colonne].idxmax()
        charge = {"run_name": f"{args.split}-{meilleure}",
                  "strategie": meilleure,
                  "params": contexte,
                  "metrics": {k: float(v) for k, v in resultats.loc[meilleure].items()},
                  "toutes_strategies": {str(i): {k: float(v) for k, v in ligne.items()}
                                        for i, ligne in resultats.iterrows()}}
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(_json.dumps(charge, indent=2, ensure_ascii=False),
                             encoding="utf-8")
        print(f"[json] métriques écrites dans {args.json} "
              f"(stratégie retenue : {meilleure})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
