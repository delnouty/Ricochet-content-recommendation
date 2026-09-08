"""Mesure l'effet de la fenêtre de comptage, sur la période de **test**.

C'est le résultat principal de l'étude, et il doit venir d'un seul relevé. La
diapositive affichait auparavant les valeurs de validation (0,2190 pour 1 h)
sous une annotation « facteur 250 » tirée d'une autre mesure : deux relevés
mélangés dans une même figure, dont le rapport réel était 29.

Ici, une seule variable change — la durée sur laquelle les clics sont comptés —
et tout est mesuré sur la période de test, avec `train + validation` comme
historique (ce dont disposerait un service au moment de répondre).

    python scripts/sweep_fraicheur.py

Écrit `models/freshness_sweep.json`, que `scripts/figures_presentation.py` lit
pour dessiner la figure. Aucun modèle n'est entraîné : seule la popularité est
classée, donc la mesure prend quelques minutes.

À ne pas confondre avec l'incident décrit en § 3.a de `docs/architecture.md` :
là, le service servait un `popular_articles.npy` **figé** sur la seule période
d'entraînement, ce qui est encore pire qu'une fenêtre longue recalculée.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Fenêtres retenues : de la fenêtre de production à la totalité de l'historique.
# 240 h dépasse l'étendue des données, et vaut donc « tout l'historique ».
FENETRES = (1, 3, 6, 12, 24, 48, 72, 240)

SORTIE = Path("models/freshness_sweep.json")
MAX_LECTEURS = 2000


def main() -> None:
    from src import experiments as xp
    from src.evaluate import split_by_time
    from src.prepare_model import load_clicks
    from src.recommender import Recommender

    clicks = load_clicks(Path("data/news-portal-user"))
    train, val, test = split_by_time(clicks)
    historique = pd.concat([train, val], ignore_index=True)
    print(f"[data] historique {len(historique):,} clics | test {len(test):,}")

    reco = Recommender(Path("models_split"))
    # Les profils doivent inclure la validation : c'est l'historique connu au
    # moment de servir, et il détermine quels articles sont exclus.
    for user_id, articles in historique.groupby("user_id")["click_article_id"]:
        nouveaux = articles.to_numpy(dtype=np.int64)
        ancien = reco.user_clicks.get(int(user_id))
        reco.user_clicks[int(user_id)] = (
            nouveaux if ancien is None
            else np.unique(np.concatenate([ancien, nouveaux])))

    users, cible = xp.eval_users(reco, test, max_users=MAX_LECTEURS)
    print(f"[eval] {len(users):,} lecteurs")

    configs, tailles = {}, {}
    for heures in FENETRES:
        vivier = xp.recent_pool(historique, heures)
        tailles[heures] = int(vivier.size)
        configs[f"{heures} h"] = xp.make_popularity(vivier, reco)

    tableau = xp.compare(configs, users, cible, n_articles=reco.n_articles)
    print()
    print(tableau.to_string())

    lignes = []
    for heures in FENETRES:
        metriques = tableau.loc[f"{heures} h"]
        lignes.append({
            "fenetre_h": heures,
            "candidats": tailles[heures],
            "HitRate@5": float(metriques["HitRate@5"]),
            "Recall@5": float(metriques["Recall@5"]),
            "couverture %": float(metriques["couverture %"]),
            "personnalisation %": float(metriques["personnalisation %"]),
        })

    premier, dernier = lignes[0]["HitRate@5"], lignes[-1]["HitRate@5"]
    facteur = premier / dernier if dernier else float("inf")

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(json.dumps({
        "split": "test",
        "lecteurs": len(users),
        "clics_historique": int(len(historique)),
        "facteur_1h_vs_tout": round(facteur, 1),
        "fenetres": lignes,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(f"facteur entre 1 h et {FENETRES[-1]} h : {facteur:.0f}")
    print(f"[json] {SORTIE}")


if __name__ == "__main__":
    main()
