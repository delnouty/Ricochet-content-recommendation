"""Tests unitaires du cœur de recommandation."""

import numpy as np
import pytest
from recommender import Recommender, _minmax


# --------------------------------------------------------------- content-based
def test_recommend_returns_exactly_n(models_dir):
    reco = Recommender(models_dir)
    assert len(reco.recommend(100, n=3, method="content")) == 3


def test_content_excludes_already_seen(models_dir):
    reco = Recommender(models_dir)
    recs = reco.recommend(200, n=5, method="content")  # a lu 2 et 3
    assert 2 not in recs and 3 not in recs


def test_content_ranks_most_similar_first(models_dir):
    reco = Recommender(models_dir)
    # user 100 a lu l'article 0 ; le plus proche est l'article 1.
    assert reco.recommend(100, n=5, method="content")[0] == 1


# ------------------------------------------------------------------- cold start
def test_unknown_user_falls_back_to_popularity(models_dir):
    reco = Recommender(models_dir)
    recs = reco.recommend(999, n=3, method="content")
    assert recs == [5, 4, 3]  # ordre de popularité


def test_popularity_fallback_excludes_seen(models_dir):
    reco = Recommender(models_dir)
    # user connu mais méthode collab indisponible -> repli popularité sans doublons
    recs = reco.recommend(200, n=6, method="collab")
    assert 2 not in recs and 3 not in recs


# ---------------------------------------------------------------- collaboratif
def test_collaborative_ranks_by_factor_score(models_dir_cf):
    reco = Recommender(models_dir_cf)
    # article 3 = meilleur score latent pour user 100 (qui n'a lu que 0).
    assert reco.recommend(100, n=5, method="collab")[0] == 3


def test_collaborative_unknown_user_falls_back(models_dir_cf):
    reco = Recommender(models_dir_cf)
    assert reco.recommend(300, n=2, method="collab") == [5, 4]


# --------------------------------------------------------------------- hybride
def test_hybrid_without_cf_behaves_like_content(models_dir):
    reco = Recommender(models_dir)
    assert reco.recommend(100, n=5, method="hybrid")[0] == 1


def test_hybrid_with_cf_excludes_seen(models_dir_cf):
    reco = Recommender(models_dir_cf)
    recs = reco.recommend(100, n=4, method="hybrid")
    assert 0 not in recs and len(recs) == 4


# ----------------------------------------------------------------- robustesse
def test_invalid_method_raises(models_dir):
    reco = Recommender(models_dir)
    with pytest.raises(ValueError):
        reco.recommend(100, method="unknown")


def test_n_larger_than_catalog_is_capped(models_dir):
    reco = Recommender(models_dir)
    # 6 articles, user 100 en a lu 1 -> au plus 5 recommandables.
    assert len(reco.recommend(100, n=50, method="content")) <= 5


def test_minmax_constant_array_returns_zeros():
    assert np.allclose(_minmax(np.array([3.0, 3.0, 3.0])), 0.0)


def test_minmax_scales_to_unit_range():
    out = _minmax(np.array([0.0, 5.0, 10.0]))
    assert out.min() == 0.0 and out.max() == 1.0
