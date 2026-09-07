"""Cold start contextuel : popularité par région.

Enjeu couvert : un lecteur dont on ne sait rien ne devrait pas recevoir le même
top-5 mondial que tout le monde. La région (seule information disponible avant le
premier clic) permet de lui servir ce que lisent les lecteurs de sa région.
"""

import pickle

import numpy as np
import pandas as pd
import pytest

from prepare_model import build_segment_popularity
from recommender import Recommender


def _write_regions(models_dir, mapping):
    with open(models_dir / "popular_by_region.pkl", "wb") as f:
        pickle.dump({k: np.array(v, dtype=np.int64) for k, v in mapping.items()}, f)


# ------------------------------------------------------- construction d'artefact
def test_build_filters_small_regions(tmp_path):
    """Une région trop peu représentée est écartée : son classement serait du bruit."""
    clicks = pd.DataFrame({
        "user_id": list(range(12)),
        "click_article_id": [1, 1, 2, 2, 3, 1, 2, 1, 1, 2, 3, 3],
        "click_timestamp": list(range(12)),
        "click_region": [10] * 10 + [99, 99],   # région 99 : 2 clics seulement
    })

    build_segment_popularity(clicks, tmp_path, min_clicks=5)

    with open(tmp_path / "popular_by_region.pkl", "rb") as f:
        by_region = pickle.load(f)

    assert set(by_region) == {10}
    # L'article 1 est le plus cliqué de la région 10 : il arrive en tête.
    assert by_region[10][0] == 1


def test_build_without_region_column_is_skipped(tmp_path):
    """Sans colonne de contexte, l'étape ne doit pas échouer."""
    clicks = pd.DataFrame({"user_id": [1], "click_article_id": [2],
                           "click_timestamp": [3]})

    build_segment_popularity(clicks, tmp_path)

    assert not (tmp_path / "popular_by_region.pkl").exists()


# --------------------------------------------------------------- recommandations
def test_new_user_gets_regional_popularity(models_dir):
    """Un utilisateur inconnu reçoit le classement de sa région."""
    _write_regions(models_dir, {7: [4, 2, 1], 8: [1, 5, 0]})
    reco = Recommender(models_dir)

    assert reco.recommend(999, n=3, region=7) == [4, 2, 1]
    assert reco.recommend(999, n=3, region=8) == [1, 5, 0]
    # Sans région : popularité globale (5, 4, 3… d'après la fixture).
    assert reco.recommend(999, n=3) == [5, 4, 3]


def test_unknown_region_falls_back_to_global(models_dir):
    _write_regions(models_dir, {7: [4, 2, 1]})
    reco = Recommender(models_dir)

    assert reco.recommend(999, n=3, region=12345) == [5, 4, 3]


def test_regional_ranking_court_complete_par_le_global(models_dir):
    """Un classement régional plus court que `n` est utilisé **puis** complété.

    Comportement modifié volontairement : la règle précédente jetait l'information
    régionale dès qu'elle ne suffisait pas à remplir le top-n. Servir les articles
    régionaux disponibles puis compléter par la popularité globale conserve les deux
    signaux, et la cascade garantit d'atteindre n articles.
    """
    _write_regions(models_dir, {7: [4, 2]})   # 2 articles pour n=3
    reco = Recommender(models_dir)

    recs = reco.recommend(999, n=3, region=7)
    assert recs[:2] == [4, 2], f"les articles régionaux doivent venir d'abord : {recs}"
    assert len(recs) == 3, "la réponse doit être complétée jusqu'à n"
    assert recs[2] not in (4, 2)


def test_region_sans_effet_sur_une_strategie_personnalisee(models_dir):
    """La région n'intervient pas dans une stratégie qui a un historique à exploiter.

    Précision utile : la stratégie de production `mix` réserve quatre places sur cinq
    à la popularité, donc **elle** utilise la région. Le test porte donc sur
    `content`, qui ne s'appuie que sur le profil du lecteur.
    """
    _write_regions(models_dir, {7: [4, 2, 1]})
    reco = Recommender(models_dir)

    # L'utilisateur 100 a lu l'article 0 (fixture) : content-based, pas de repli.
    assert (reco.recommend(100, n=3, region=7, method="content")
            == reco.recommend(100, n=3, method="content"))


def test_regional_ranking_excludes_seen_articles(models_dir):
    """Les articles déjà lus restent exclus, y compris en repli régional."""
    _write_regions(models_dir, {7: [0, 4, 2, 1]})
    reco = Recommender(models_dir)
    reco.user_clicks[999] = np.array([0], dtype=np.int64)

    # L'utilisateur a lu 0 : profil de contenu exploitable, donc pas de repli.
    # On force le repli en demandant une méthode collaborative indisponible.
    recs = reco.recommend(999, n=3, method="collab", region=7)
    assert 0 not in recs


def test_missing_region_artifact_is_optional(models_dir):
    """L'artefact régional est optionnel : son absence ne casse rien."""
    reco = Recommender(models_dir)

    assert reco.popular_by_region == {}
    assert reco.recommend(999, n=3, region=7) == [5, 4, 3]
