"""Quantifie la fuite d'une évaluation sans découpage temporel.

La présentation affirme que les premiers chiffres du projet étaient faux. Ce
script produit le chiffre qui le prouve, au lieu de le citer de mémoire : la
diapositive annonçait « 0,2300 sans découpage, 0,0250 avec, un facteur 42 », dont
aucun des trois nombres ne se retrouvait (0,2300 / 0,0250 valant 9,2, et l'ALS
correctement mesuré 0,0415).

**Protocole biaisé reproduit ici** — celui d'un début de projet :

  - profil du lecteur = tous ses clics **sauf le dernier** ;
  - cible             = son dernier clic ;
  - ALS entraîné sur **tous** les clics, dernier inclus  ← la fuite ;
  - classement sur **tout le catalogue**, sans vivier récent.

Le modèle a donc vu, pendant son entraînement, le clic qu'on lui demande de
prédire. C'est ce que fait toute évaluation « entraîner sur 100 %, mesurer sur
les mêmes données ».

Deux protocoles biaisés ont été essayés avant celui-ci, et tous deux donnaient
0,0000 — utile à savoir avant de croire un zéro :

  1. historique *et* cible = tous les clics : les cibles se retrouvaient dans les
     articles déjà lus, donc exclues du classement. Mesure impossible, pas fuite.
  2. leave-last-out mais avec un vivier de 6 h : le dernier clic d'un lecteur est
     dispersé sur toute la période, un vivier récent ne peut pas le contenir.

    python scripts/mesure_fuite.py

Mesure obtenue : ALS **0,2415** avec fuite, contre **0,0415** sur la période de
test — un facteur **5,8**. La popularité, elle, ne profite pas de la fuite : son
classement ne dépend pas du lecteur, et sur tout l'historique elle tombe à 0,0000.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MAX_LECTEURS = 2000
# Référence : l'ALS dans sa configuration retenue, mesuré sur la période de test
# (models/baseline_metrics.json).
ALS_TEST = 0.0415


def main() -> None:
    from src import experiments as xp
    from src.prepare_model import load_clicks
    from src.recommender import Recommender

    clicks = load_clicks(Path("data/news-portal-user")).sort_values("click_timestamp")
    print(f"[data] {len(clicks):,} clics")

    reco = Recommender(Path("models_split"))

    cibles, profils = {}, {}
    for user_id, groupe in clicks.groupby("user_id")["click_article_id"]:
        articles = groupe.to_numpy(dtype=np.int64)
        if articles.size < 2:
            continue
        cibles[int(user_id)] = {int(articles[-1])}
        profils[int(user_id)] = np.unique(articles[:-1])

    reco.user_clicks.update(profils)
    users = list(profils)[:MAX_LECTEURS]
    cible = pd.Series(cibles)
    print(f"[eval] {len(users):,} lecteurs, cible = leur dernier clic")

    tout = np.arange(reco.n_articles, dtype=np.int64)
    configs = {
        "ALS (fuite, tout le catalogue)": xp.train_als_window(
            clicks, None, factors=50)(tout, reco),
        "popularité historique (fuite)": xp.make_popularity(
            xp.recent_pool(clicks, 240), reco),
    }
    tableau = xp.compare(configs, users, cible, n_articles=reco.n_articles)
    print()
    print("=== leave-last-out, modèle entraîné sur la cible ===")
    print(tableau.to_string())

    fuite = float(tableau.loc["ALS (fuite, tout le catalogue)", "HitRate@5"])
    print()
    print(f"ALS avec fuite         : {fuite:.4f}")
    print(f"ALS découpage temporel : {ALS_TEST:.4f}  (période de test)")
    print(f"facteur de la fuite    : {fuite / ALS_TEST:.1f}")


if __name__ == "__main__":
    main()
