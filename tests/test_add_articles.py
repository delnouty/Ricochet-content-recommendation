"""Vérifie l'ajout de nouveaux articles au catalogue (scripts/add_articles.py).

Enjeu couvert (§4.b de docs/architecture.md) : un article publié après la
génération des artefacts doit être intégrable sans réajuster l'ACP, recevoir un
`article_id` cohérent avec son indice de ligne, et devenir immédiatement
recommandable par le content-based.
"""

import pickle
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

pytest.importorskip("sklearn", reason="scikit-learn requis pour ajuster l'ACP")

from add_articles import append_to_catalogue, load_embeddings  # noqa: E402
from src.prepare_model import build_embeddings_pca, project_embeddings  # noqa: E402
from recommender import Recommender  # noqa: E402


@pytest.fixture
def catalogue(tmp_path):
    """Artefacts complets issus d'un catalogue jouet de 40 articles en 12 dimensions."""
    rng = np.random.default_rng(7)
    base = rng.normal(size=(4, 12))
    emb = (rng.random(size=(40, 4)) @ base
           + rng.normal(scale=0.05, size=(40, 12))).astype(np.float32)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    with open(data_dir / "articles_embeddings.pickle", "wb") as f:
        pickle.dump(emb, f)

    models = tmp_path / "models"
    models.mkdir()
    build_embeddings_pca(data_dir, models, n_components=5)

    # Artefacts utilisateur minimaux, pour instancier un Recommender.
    with open(models / "user_clicks.pkl", "wb") as f:
        pickle.dump({100: np.array([0], dtype=np.int64)}, f)
    np.save(models / "popular_articles.npy", np.arange(40, dtype=np.int64))

    return models, emb


def test_load_embeddings_npy_and_pickle(tmp_path):
    matrix = np.arange(24, dtype=np.float32).reshape(2, 12)

    np.save(tmp_path / "a.npy", matrix)
    with open(tmp_path / "a.pickle", "wb") as f:
        pickle.dump(matrix, f)

    np.testing.assert_array_equal(load_embeddings(tmp_path / "a.npy"), matrix)
    np.testing.assert_array_equal(load_embeddings(tmp_path / "a.pickle"), matrix)


def test_load_embeddings_rejects_non_finite(tmp_path):
    bad = np.array([[1.0, np.nan]], dtype=np.float32)
    np.save(tmp_path / "bad.npy", bad)
    with pytest.raises(ValueError, match="non finies"):
        load_embeddings(tmp_path / "bad.npy")


def test_append_assigns_row_indices_as_ids(catalogue):
    models, emb = catalogue
    before = np.load(models / "articles_embeddings_pca.npy").shape[0]

    new_raw = np.stack([emb[0] + 0.01, emb[5] + 0.01]).astype(np.float32)
    vectors = project_embeddings(new_raw, models)
    first_id, last_id = append_to_catalogue(vectors, models)

    after = np.load(models / "articles_embeddings_pca.npy")
    assert (first_id, last_id) == (before, before + 1)
    assert after.shape[0] == before + 2
    # L'article_id doit bien être l'indice de ligne.
    np.testing.assert_allclose(after[first_id], vectors[0], atol=1e-6)


def test_existing_vectors_are_untouched(catalogue):
    """L'ajout ne doit pas modifier les vecteurs déjà en place (base ACP inchangée)."""
    models, emb = catalogue
    before = np.load(models / "articles_embeddings_pca.npy").copy()

    append_to_catalogue(project_embeddings(emb[3] + 0.01, models), models)

    after = np.load(models / "articles_embeddings_pca.npy")
    np.testing.assert_array_equal(after[: before.shape[0]], before)


def test_new_article_is_recommendable_immediately(catalogue):
    """Un article ajouté doit pouvoir être recommandé par le content-based."""
    models, emb = catalogue

    # Nouvel article très proche de l'article 0, que l'utilisateur 100 a lu.
    new_raw = (emb[0] + np.float32(0.001)).astype(np.float32)
    first_id, _ = append_to_catalogue(project_embeddings(new_raw, models), models)

    reco = Recommender(models)
    recs = reco.recommend(100, n=5, method="content")

    assert first_id in recs, f"article {first_id} absent du top-5 : {recs}"
    assert 0 not in recs, "l'article déjà lu ne doit pas être recommandé"
