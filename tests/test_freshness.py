"""Vivier d'articles récents : la fraîcheur comme filtre de candidats.

Enjeu couvert : sur découpage temporel, la popularité calculée sur une fenêtre
courte atteint HitRate@5 = 0,2525 contre 0,0010 sur tout l'historique — un facteur
250. Ces tests garantissent que le vivier est bien appliqué, qu'il n'est jamais
appliqué à moitié, et que son absence ne casse rien.
"""

import json
import pickle

import numpy as np
import pandas as pd
import pytest

from prepare_model import build_recent_popularity
from recommender import Recommender

HEURE_MS = 3600 * 1000


def _ecrire_vivier(models_dir, articles):
    np.save(models_dir / "popular_recent.npy", np.array(articles, dtype=np.int64))
    (models_dir / "recent_window.json").write_text(
        json.dumps({"window_hours_effective": 6}), encoding="utf-8")


# --------------------------------------------------------- construction du vivier
def test_ancre_ignore_les_horodatages_aberrants(tmp_path):
    """Le jeu Globo contient des clics très postérieurs au gros du trafic.

    Ancrer la fenêtre sur le dernier clic la viderait : 99,9 % des clics s'arrêtent
    665 h avant le maximum, et il n'en reste que 2 dans les 72 dernières heures.
    """
    base = 1_000_000_000_000
    dense = pd.DataFrame({
        "user_id": range(2000),
        "click_article_id": [i % 300 for i in range(2000)],
        "click_timestamp": [base + i * 1000 for i in range(2000)],
    })
    aberrant = pd.DataFrame({"user_id": [9999], "click_article_id": [1],
                             "click_timestamp": [base + 500 * HEURE_MS]})
    clicks = pd.concat([dense, aberrant], ignore_index=True)

    ordre = build_recent_popularity(clicks, tmp_path, window_hours=6, min_articles=10)

    meta = json.loads((tmp_path / "recent_window.json").read_text(encoding="utf-8"))
    assert meta["clics_aberrants_ecartes"] >= 1
    assert ordre.size >= 10, "l'ancre aberrante a vidé la fenêtre"


def test_elargissement_automatique(tmp_path):
    """Une fenêtre trop étroite s'élargit jusqu'à contenir assez d'articles."""
    base = 1_000_000_000_000
    clicks = pd.DataFrame({
        "user_id": range(600),
        "click_article_id": range(600),
        # étalés sur 60 h : une fenêtre de 1 h ne contient qu'une dizaine d'articles
        "click_timestamp": [base + int(i * 0.1 * HEURE_MS) for i in range(600)],
    })

    build_recent_popularity(clicks, tmp_path, window_hours=1, min_articles=200)

    meta = json.loads((tmp_path / "recent_window.json").read_text(encoding="utf-8"))
    assert meta["window_hours_effective"] > meta["window_hours_demandee"]
    assert meta["articles_fenetre"] >= 200


def test_classement_par_popularite_dans_la_fenetre(tmp_path):
    base = 1_000_000_000_000
    clicks = pd.DataFrame({
        "user_id": range(10),
        "click_article_id": [7, 7, 7, 3, 3, 1, 1, 1, 1, 5],
        "click_timestamp": [base + i * 1000 for i in range(10)],
    })

    ordre = build_recent_popularity(clicks, tmp_path, window_hours=6, min_articles=1)

    assert ordre[0] == 1, "l'article le plus cliqué de la fenêtre doit arriver en tête"


# ------------------------------------------------------ application par le moteur
def test_toutes_les_strategies_respectent_le_vivier(models_dir_cf):
    """Aucune stratégie ne doit recommander hors du vivier — `mix` inclus.

    `mix` est la stratégie **servie en production** : l'omettre de cette boucle
    reviendrait à ne vérifier la fraîcheur que sur les stratégies de comparaison.
    Elle en était absente jusqu'à la revue de la spécification fonctionnelle.
    """
    _ecrire_vivier(models_dir_cf, [2, 3, 4, 5])
    reco = Recommender(models_dir_cf)

    for methode in ("mix", "hybrid", "content", "collab", "svd"):
        recs = reco.recommend(100, n=2, method=methode)
        assert recs, f"{methode} ne renvoie rien"
        assert set(recs) <= {2, 3, 4, 5}, f"{methode} sort du vivier : {recs}"


def test_mix_reserve_une_place_au_contenu(models_dir_cf):
    """`mix` = 4 places de popularité + 1 place de contenu (FS-017).

    C'est la composition qui justifie la stratégie retenue : la place donnée au
    contenu multiplie la couverture du catalogue sans coûter de justesse
    mesurable. Sans ce test, rien ne garantit que la cinquième place existe.
    """
    _ecrire_vivier(models_dir_cf, [1, 2, 3, 4, 5])
    reco = Recommender(models_dir_cf)

    populaires = reco.popular_recent[:4].tolist()
    recs = reco.recommend(100, n=5, method="mix")

    assert len(recs) == 5, f"cinq places attendues, obtenu {recs}"
    assert recs[:4] == populaires, (
        f"les quatre premières places doivent suivre la popularité récente "
        f"{populaires}, obtenu {recs[:4]}")
    assert recs[4] not in populaires, (
        "la cinquième place doit venir du contenu, pas de la popularité")


def test_fresh_only_desactivable(models_dir_cf):
    """`fresh_only=False` rétablit le classement sur tout le catalogue."""
    _ecrire_vivier(models_dir_cf, [2, 3, 4, 5])
    reco = Recommender(models_dir_cf)

    frais = reco.recommend(100, n=3, method="content")
    complet = reco.recommend(100, n=3, method="content", fresh_only=False)

    assert set(frais) <= {2, 3, 4, 5}
    assert frais != complet, "le vivier devrait changer le classement"


def test_vivier_trop_petit_ignore(models_dir):
    """Un vivier plus court que n donnerait une liste tronquée : on l'ignore."""
    _ecrire_vivier(models_dir, [2])
    reco = Recommender(models_dir)

    recs = reco.recommend(100, n=3, method="content")
    assert len(recs) == 3, "le moteur devrait retomber sur le catalogue entier"


def test_cold_start_prefere_la_fraicheur(models_dir):
    """Sans historique, le lecteur reçoit les articles récents, pas les plus lus."""
    _ecrire_vivier(models_dir, [1, 2, 3, 4])
    reco = Recommender(models_dir)

    # La fixture classe la popularité globale 5, 4, 3, 2, 1, 0.
    assert reco.recommend(999, n=3) == [1, 2, 3]
    assert reco.recommend(999, n=3, fresh_only=False) == [5, 4, 3]


def test_artefact_absent_sans_effet(models_dir):
    """Le vivier est optionnel : un `models/` ancien doit continuer de fonctionner."""
    reco = Recommender(models_dir)

    assert reco.popular_recent.size == 0
    assert reco.recommend(999, n=3) == [5, 4, 3]
    assert reco.recommend(100, n=3, method="content")


def test_vivier_hors_catalogue_filtre(models_dir):
    """Un identifiant hors catalogue dans le vivier ne doit pas faire planter.

    Cas réel : les artefacts de fraîcheur et le catalogue peuvent être
    désynchronisés après l'ajout d'articles.
    """
    _ecrire_vivier(models_dir, [2, 3, 4, 999_999])
    reco = Recommender(models_dir)

    recs = reco.recommend(100, n=3, method="content")
    assert 999_999 not in recs
    assert recs
