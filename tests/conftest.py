"""Configuration pytest : rend `src/` importable et fournit des artefacts synthétiques."""

import pickle
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


# Embeddings jouets : 3 paires d'articles proches (0~1, 2~3, 4/5 isolés).
_EMB = np.array(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.9, 0.1, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.9, 0.1, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ],
    dtype=np.float32,
)


def _write_base(path: Path) -> None:
    np.save(path / "articles_embeddings_pca.npy", _EMB)
    user_clicks = {
        100: np.array([0], dtype=np.int64),        # a lu l'article 0
        200: np.array([2, 3], dtype=np.int64),     # a lu 2 et 3
    }
    with open(path / "user_clicks.pkl", "wb") as f:
        pickle.dump(user_clicks, f)
    # Popularité : 5 le plus populaire … 0 le moins.
    np.save(path / "popular_articles.npy", np.array([5, 4, 3, 2, 1, 0], dtype=np.int64))


def _write_cf(path: Path) -> None:
    # user 100 (ligne 0) ; l'article 3 obtient le meilleur score collaboratif.
    np.save(path / "cf_user_factors.npy", np.array([[1.0, 0.0]], dtype=np.float32))
    np.save(path / "cf_item_factors.npy",
            np.array([[0.1, 0], [0.2, 0], [0.3, 0], [0.9, 0], [0.5, 0], [0.4, 0]],
                     dtype=np.float32))
    np.save(path / "cf_item_ids.npy", np.array([0, 1, 2, 3, 4, 5], dtype=np.int64))
    with open(path / "cf_user_index.pkl", "wb") as f:
        pickle.dump({100: 0}, f)


@pytest.fixture
def models_dir(tmp_path):
    """Artefacts sans filtrage collaboratif (content + popularité seulement)."""
    _write_base(tmp_path)
    return tmp_path


@pytest.fixture
def models_dir_cf(tmp_path):
    """Artefacts complets, avec facteurs ALS."""
    _write_base(tmp_path)
    _write_cf(tmp_path)
    return tmp_path
