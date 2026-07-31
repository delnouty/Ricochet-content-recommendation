"""Vérifie l'intégration d'un nouvel article : projection ACP persistée.

Enjeu couvert : sans `pca_mean.npy` / `pca_components.npy`, un article arrivant
après la génération des artefacts ne peut pas être placé dans l'espace réduit
sans réajuster l'ACP (donc sans invalider tout le catalogue). Ces tests
garantissent que la projection sauvegardée reproduit bien celle de scikit-learn.
"""

import numpy as np
import pytest

from prepare_model import build_embeddings_pca, project_embeddings

pytest.importorskip("sklearn", reason="scikit-learn requis pour ajuster l'ACP")


@pytest.fixture
def raw_catalogue(tmp_path):
    """Catalogue brut jouet : 40 articles en 12 dimensions, structure non triviale."""
    import pickle

    rng = np.random.default_rng(42)
    base = rng.normal(size=(4, 12))                       # 4 « thèmes »
    weights = rng.random(size=(40, 4))
    emb = (weights @ base + rng.normal(scale=0.05, size=(40, 12))).astype(np.float32)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    with open(data_dir / "articles_embeddings.pickle", "wb") as f:
        pickle.dump(emb, f)
    return data_dir, emb


def test_projection_artifacts_written(tmp_path, raw_catalogue):
    data_dir, emb = raw_catalogue
    out = tmp_path / "models"
    out.mkdir()

    build_embeddings_pca(data_dir, out, n_components=5)

    mean = np.load(out / "pca_mean.npy")
    components = np.load(out / "pca_components.npy")
    assert mean.shape == (emb.shape[1],)
    assert components.shape == (5, emb.shape[1])


def test_projection_matches_fitted_pca(tmp_path, raw_catalogue):
    """Projeter un article déjà vu doit redonner sa ligne de la matrice réduite."""
    data_dir, emb = raw_catalogue
    out = tmp_path / "models"
    out.mkdir()

    reduced = build_embeddings_pca(data_dir, out, n_components=5)
    projected = project_embeddings(emb, out)

    assert projected.shape == reduced.shape
    np.testing.assert_allclose(projected, reduced, atol=1e-5)


def test_new_article_projects_without_refitting(tmp_path, raw_catalogue):
    """Un article absent de l'ajustement obtient un vecteur exploitable."""
    data_dir, emb = raw_catalogue
    out = tmp_path / "models"
    out.mkdir()
    build_embeddings_pca(data_dir, out, n_components=5)

    # Nouvel article : proche de l'article 0, jamais vu par l'ACP.
    new_article = emb[0] + np.float32(0.01)
    vector = project_embeddings(new_article, out)

    assert vector.shape == (1, 5)
    assert np.isfinite(vector).all()

    # Il doit rester plus proche de l'article 0 que la moyenne du catalogue :
    # c'est ce qui permet au content-based de le recommander immédiatement.
    reduced = np.load(out / "articles_embeddings_pca.npy")
    distances = np.linalg.norm(reduced - vector, axis=1)
    assert int(np.argmin(distances)) == 0


def test_projection_rejects_wrong_dimension(tmp_path, raw_catalogue):
    data_dir, _ = raw_catalogue
    out = tmp_path / "models"
    out.mkdir()
    build_embeddings_pca(data_dir, out, n_components=5)

    with pytest.raises(ValueError, match="dimension"):
        project_embeddings(np.zeros((1, 3), dtype=np.float32), out)
