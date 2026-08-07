"""Cœur de recommandation — COPIE DÉPLOYÉE (solution locale).

⚠️  GÉNÉRÉ par scripts/sync_recommender.py — NE PAS ÉDITER ICI.
    Source unique de vérité : src/recommender.py.
    Régénérer après toute modification : python scripts/sync_recommender.py

À l'inférence : dépend uniquement de numpy + pickle (stdlib).
"""


from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np


class Recommender:
    """Charge les artefacts pré-calculés et sert des recommandations top-N."""

    def __init__(self, models_dir: str | Path):
        self.models_dir = Path(models_dir)

        # --- Content-based ---------------------------------------------------
        # Embeddings réduits par ACP, indexés par article_id (ligne = article_id).
        emb = np.load(self.models_dir / "articles_embeddings_pca.npy").astype(np.float32)
        # Pré-normalisation L2 => le produit scalaire donne directement le cosinus.
        norms = np.linalg.norm(emb, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.embeddings = emb / norms
        self.n_articles = self.embeddings.shape[0]

        # Historique de clics par utilisateur : dict user_id -> np.ndarray[article_id]
        with open(self.models_dir / "user_clicks.pkl", "rb") as f:
            self.user_clicks: dict[int, np.ndarray] = pickle.load(f)

        # Articles les plus populaires (article_id triés par popularité décroissante).
        self.popular_articles = np.load(self.models_dir / "popular_articles.npy")

        # Popularité par région : cold start contextuel (artefact optionnel).
        self.popular_by_region: dict[int, np.ndarray] = {}
        region_file = self.models_dir / "popular_by_region.pkl"
        if region_file.exists():
            with open(region_file, "rb") as f:
                self.popular_by_region = pickle.load(f)

        # --- SVD Surprise (facteurs pré-entraînés hors-ligne) ---------------
        # Surprise n'est pas importée ici : on rejoue son calcul de score en numpy
        # (µ + biais_user + biais_item + pu·qi). Artefacts optionnels.
        self._has_svd = (self.models_dir / "svd_item_factors.npy").exists()
        if self._has_svd:
            self.svd_user_factors = np.load(self.models_dir / "svd_user_factors.npy").astype(np.float32)
            self.svd_item_factors = np.load(self.models_dir / "svd_item_factors.npy").astype(np.float32)
            self.svd_user_bias = np.load(self.models_dir / "svd_user_bias.npy").astype(np.float32)
            self.svd_item_bias = np.load(self.models_dir / "svd_item_bias.npy").astype(np.float32)
            self.svd_global_mean = float(np.load(self.models_dir / "svd_global_mean.npy")[0])
            self.svd_item_ids = np.load(self.models_dir / "svd_item_ids.npy")
            with open(self.models_dir / "svd_user_index.pkl", "rb") as f:
                self.svd_user_index: dict[int, int] = pickle.load(f)

        # --- Collaborative filtering (facteurs ALS pré-entraînés) ------------
        self._has_cf = (self.models_dir / "cf_item_factors.npy").exists()
        if self._has_cf:
            self.cf_item_factors = np.load(self.models_dir / "cf_item_factors.npy").astype(np.float32)
            self.cf_user_factors = np.load(self.models_dir / "cf_user_factors.npy").astype(np.float32)
            # Correspondances index <-> identifiants.
            with open(self.models_dir / "cf_user_index.pkl", "rb") as f:
                self.cf_user_index: dict[int, int] = pickle.load(f)  # user_id -> ligne
            # colonne des facteurs articles -> article_id
            self.cf_item_ids = np.load(self.models_dir / "cf_item_ids.npy")

    # ------------------------------------------------------------------ utils
    def _seen(self, user_id: int) -> np.ndarray:
        """Articles déjà cliqués par l'utilisateur (vide si inconnu)."""
        return self.user_clicks.get(user_id, np.array([], dtype=np.int64))

    @staticmethod
    def _top_n(scores: np.ndarray, exclude: np.ndarray, n: int) -> list[int]:
        """Renvoie les n article_id de meilleur score, hors `exclude`."""
        if exclude.size:
            scores = scores.copy()
            scores[exclude] = -np.inf
        # argpartition pour éviter un tri complet du catalogue (360k+ articles).
        k = min(n, scores.size)
        idx = np.argpartition(-scores, k - 1)[:k]
        idx = idx[np.argsort(-scores[idx])]
        # Ne jamais renvoyer un article exclu : si moins de n candidats valides
        # existent, on renvoie moins de n plutôt que de compléter avec du -inf.
        idx = idx[np.isfinite(scores[idx])]
        return idx.tolist()

    # ------------------------------------------------------------- stratégies
    def _content_based(self, user_id: int, n: int) -> list[int] | None:
        seen = self._seen(user_id)
        if seen.size == 0:
            return None  # cold start géré par l'appelant
        # Profil = moyenne des embeddings (déjà normalisés) des articles lus.
        profile = self.embeddings[seen].mean(axis=0)
        p_norm = np.linalg.norm(profile)
        if p_norm == 0:
            return None
        profile /= p_norm
        scores = self.embeddings @ profile  # cosinus vers tout le catalogue
        return self._top_n(scores, seen, n)

    def _collaborative(self, user_id: int, n: int) -> list[int] | None:
        if not self._has_cf or user_id not in self.cf_user_index:
            return None
        row = self.cf_user_index[user_id]
        scores = self.cf_item_factors @ self.cf_user_factors[row]
        seen = self._seen(user_id)
        # Les facteurs sont indexés par colonne -> on masque puis on remappe.
        order = self._top_n(scores, self._to_cf_cols(seen), n)
        return self.cf_item_ids[order].tolist()

    def _svd(self, user_id: int, n: int) -> list[int] | None:
        """Score SVD (Surprise) rejoué en numpy : µ + b_u + b_i + pu·qi."""
        if not self._has_svd or user_id not in self.svd_user_index:
            return None
        row = self.svd_user_index[user_id]
        scores = (self.svd_global_mean
                  + self.svd_user_bias[row]
                  + self.svd_item_bias
                  + self.svd_item_factors @ self.svd_user_factors[row])
        seen = self._seen(user_id)
        order = self._top_n(scores, self._to_svd_cols(seen), n)
        return self.svd_item_ids[order].tolist()

    def _to_svd_cols(self, article_ids: np.ndarray) -> np.ndarray:
        """article_id -> indices de colonnes SVD (ignore les absents)."""
        lookup = {int(a): i for i, a in enumerate(self.svd_item_ids)}
        cols = [lookup[int(a)] for a in article_ids if int(a) in lookup]
        return np.array(cols, dtype=np.int64)

    def _to_cf_cols(self, article_ids: np.ndarray) -> np.ndarray:
        """Convertit des article_id en indices de colonnes CF (ignore les absents)."""
        lookup = {a: i for i, a in enumerate(self.cf_item_ids)}
        cols = [lookup[a] for a in article_ids if a in lookup]
        return np.array(cols, dtype=np.int64)

    def _hybrid(self, user_id: int, n: int, alpha: float = 0.5) -> list[int] | None:
        """Mélange content + collab sur leurs scores min-max normalisés."""
        seen = self._seen(user_id)
        if seen.size == 0:
            return None

        # Score contenu (sur tout le catalogue).
        profile = self.embeddings[seen].mean(axis=0)
        p_norm = np.linalg.norm(profile)
        if p_norm == 0:
            return None
        content_scores = self.embeddings @ (profile / p_norm)
        combined = _minmax(content_scores)

        # Score collaboratif (si l'utilisateur est connu du modèle CF).
        if self._has_cf and user_id in self.cf_user_index:
            row = self.cf_user_index[user_id]
            cf_raw = self.cf_item_factors @ self.cf_user_factors[row]
            cf_full = np.zeros(self.n_articles, dtype=np.float32)
            cf_full[self.cf_item_ids] = cf_raw
            combined = alpha * combined + (1 - alpha) * _minmax(cf_full)

        return self._top_n(combined, seen, n)

    # ----------------------------------------------------------------- public
    def recommend(self, user_id: int, n: int = 5, method: str = "hybrid",
                  region: int | None = None) -> list[int]:
        """Renvoie `n` article_id recommandés pour `user_id`.

        method ∈ {"content", "collab", "hybrid"}. En l'absence d'historique
        exploitable, bascule automatiquement sur les articles populaires.

        `region` (code anonymisé, optionnel) n'intervient que dans ce repli : un
        lecteur dont on ne sait rien reçoit alors la popularité **de sa région**
        plutôt que la popularité mondiale. Ignoré dès qu'un historique existe, le
        contenu étant un signal bien plus fort.
        """
        dispatch = {
            "content": self._content_based,
            "collab": self._collaborative,
            "svd": self._svd,
            "hybrid": self._hybrid,
        }
        if method not in dispatch:
            raise ValueError(f"method inconnue : {method!r} (attendu {set(dispatch)})")

        result = dispatch[method](user_id, n)
        if result:
            return result
        return self._popularity_fallback(user_id, n, region)

    def _popularity_fallback(self, user_id: int, n: int,
                             region: int | None = None) -> list[int]:
        """Articles populaires, si possible ceux de la région de l'utilisateur."""
        seen = set(self._seen(user_id).tolist())
        ranking = self._region_ranking(region, n, seen)
        if ranking is None:
            ranking = self.popular_articles
        out = [int(a) for a in ranking if a not in seen]
        return out[:n]

    def _region_ranking(self, region: int | None, n: int,
                        seen: set[int]) -> np.ndarray | None:
        """Classement régional s'il est exploitable, sinon None.

        Un classement régional trop court après exclusion des articles déjà lus
        donnerait moins de `n` résultats : on préfère alors le classement global.
        """
        if region is None:
            return None
        ranking = self.popular_by_region.get(int(region))
        if ranking is None:
            return None
        available = sum(1 for a in ranking if a not in seen)
        return ranking if available >= n else None


def _minmax(x: np.ndarray) -> np.ndarray:
    """Normalisation min-max robuste (renvoie des zéros si tout est égal)."""
    lo, hi = x.min(), x.max()
    if hi - lo < 1e-12:
        return np.zeros_like(x)
    return (x - lo) / (hi - lo)
