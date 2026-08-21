"""COPIE DÉPLOYÉE (solution Hugging Face) — générée depuis src/recommender.py.

⚠️  NE PAS ÉDITER ICI : toute modification serait écrasée.
    Source unique de vérité : src/recommender.py
    Régénérer : python scripts/sync_recommender.py
    Vérifier  : python scripts/sync_recommender.py --check   (utilisé en CI)
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

        # --- Fraîcheur ------------------------------------------------------
        # Vivier d'articles récents : de loin le levier le plus fort mesuré sur ce
        # jeu (HitRate@5 de 0,0010 sur tout l'historique contre 0,2525 sur une
        # fenêtre d'une heure). Toutes les stratégies ranguent à l'intérieur de ce
        # vivier lorsqu'il est disponible ; sans lui, elles retombent sur le
        # catalogue entier — comportement d'origine, conservé pour compatibilité.
        recent_file = self.models_dir / "popular_recent.npy"
        self.popular_recent = (np.load(recent_file) if recent_file.exists()
                               else np.array([], dtype=np.int64))
        self.recent_window: dict = {}
        window_file = self.models_dir / "recent_window.json"
        if window_file.exists():
            import json
            self.recent_window = json.loads(window_file.read_text(encoding="utf-8"))

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

    def _candidates(self, fresh_only: bool, n: int) -> np.ndarray | None:
        """Vivier de candidats : articles récents, ou None pour tout le catalogue.

        Renvoie None si le vivier est absent ou trop petit pour remplir un top-n :
        mieux vaut un classement sur tout le catalogue qu'une liste tronquée.
        """
        if not fresh_only or self.popular_recent.size <= n:
            return None
        # Un article du vivier absent du catalogue (artefacts désynchronisés) ferait
        # échouer l'indexation : on le filtre.
        pool = self.popular_recent[self.popular_recent < self.n_articles]
        return pool if pool.size > n else None

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
    def _profile(self, user_id: int) -> np.ndarray | None:
        """Profil de contenu : moyenne normalisée des embeddings des articles lus."""
        seen = self._seen(user_id)
        if seen.size == 0:
            return None
        profile = self.embeddings[seen].mean(axis=0)
        norm = np.linalg.norm(profile)
        return None if norm == 0 else profile / norm

    def _content_based(self, user_id: int, n: int,
                       pool: np.ndarray | None = None) -> list[int] | None:
        profile = self._profile(user_id)
        if profile is None:
            return None  # cold start géré par l'appelant
        seen = self._seen(user_id)

        if pool is None:
            scores = self.embeddings @ profile          # tout le catalogue
            return self._top_n(scores, seen, n)

        # Classement à l'intérieur du vivier récent : un article similaire mais
        # vieux de plusieurs années n'intéresse personne (mesuré : 0,0015 sur le
        # catalogue entier contre 0,0390 sur un vivier de 6 h).
        scores = self.embeddings[pool] @ profile
        scores[np.isin(pool, seen)] = -np.inf
        k = min(n, scores.size)
        idx = np.argpartition(-scores, k - 1)[:k]
        idx = idx[np.argsort(-scores[idx])]
        return [int(a) for a in pool[idx[np.isfinite(scores[idx])]]]

    def _collaborative(self, user_id: int, n: int,
                       pool: np.ndarray | None = None) -> list[int] | None:
        if not self._has_cf or user_id not in self.cf_user_index:
            return None
        row = self.cf_user_index[user_id]
        scores = self.cf_item_factors @ self.cf_user_factors[row]
        seen = self._seen(user_id)

        if pool is not None:
            # On restreint aux colonnes dont l'article est dans le vivier récent.
            garde = np.isin(self.cf_item_ids, pool)
            if garde.sum() > n:
                ids = self.cf_item_ids[garde]
                sous_scores = scores[garde].copy()
                sous_scores[np.isin(ids, seen)] = -np.inf
                k = min(n, sous_scores.size)
                idx = np.argpartition(-sous_scores, k - 1)[:k]
                idx = idx[np.argsort(-sous_scores[idx])]
                return [int(a) for a in ids[idx[np.isfinite(sous_scores[idx])]]]

        # Les facteurs sont indexés par colonne -> on masque puis on remappe.
        order = self._top_n(scores, self._to_cf_cols(seen), n)
        return self.cf_item_ids[order].tolist()

    def _svd(self, user_id: int, n: int,
             pool: np.ndarray | None = None) -> list[int] | None:
        """Score SVD (Surprise) rejoué en numpy : µ + b_u + b_i + pu·qi."""
        if not self._has_svd or user_id not in self.svd_user_index:
            return None
        row = self.svd_user_index[user_id]
        scores = (self.svd_global_mean
                  + self.svd_user_bias[row]
                  + self.svd_item_bias
                  + self.svd_item_factors @ self.svd_user_factors[row])
        seen = self._seen(user_id)

        if pool is not None:
            garde = np.isin(self.svd_item_ids, pool)
            if garde.sum() > n:
                ids = self.svd_item_ids[garde]
                sous = scores[garde].copy()
                sous[np.isin(ids, seen)] = -np.inf
                k = min(n, sous.size)
                idx = np.argpartition(-sous, k - 1)[:k]
                idx = idx[np.argsort(-sous[idx])]
                return [int(a) for a in ids[idx[np.isfinite(sous[idx])]]]

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

    def _hybrid(self, user_id: int, n: int, pool: np.ndarray | None = None,
                alpha: float = 0.5) -> list[int] | None:
        """Mélange content + collab sur leurs scores min-max normalisés.

        Restreint au vivier récent lorsqu'il est fourni : sans cette restriction, le
        mélange choisit parmi tout le catalogue, dont l'essentiel n'a plus aucun
        lecteur (mesuré : facteur 20 sur la précision du contenu).
        """
        seen = self._seen(user_id)
        profile = self._profile(user_id)
        if profile is None:
            return None

        indices = pool if pool is not None else np.arange(self.n_articles)
        combined = _minmax(self.embeddings[indices] @ profile)

        # Score collaboratif (si l'utilisateur est connu du modèle CF).
        if self._has_cf and user_id in self.cf_user_index:
            row = self.cf_user_index[user_id]
            cf_raw = self.cf_item_factors @ self.cf_user_factors[row]
            cf_full = np.zeros(self.n_articles, dtype=np.float32)
            cf_full[self.cf_item_ids] = cf_raw
            combined = alpha * combined + (1 - alpha) * _minmax(cf_full[indices])

        scores = combined.astype(np.float32)
        scores[np.isin(indices, seen)] = -np.inf
        k = min(n, scores.size)
        idx = np.argpartition(-scores, k - 1)[:k]
        idx = idx[np.argsort(-scores[idx])]
        return [int(a) for a in indices[idx[np.isfinite(scores[idx])]]]

    # ----------------------------------------------------------------- public
    def recommend(self, user_id: int, n: int = 5, method: str = "hybrid",
                  region: int | None = None, fresh_only: bool = True) -> list[int]:
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

        # Les quatre stratégies acceptent le vivier : sans cela, la stratégie par
        # défaut (hybrid) continuerait de choisir dans tout le catalogue.
        pool = self._candidates(fresh_only, n)
        result = dispatch[method](user_id, n, pool)
        if result:
            return result
        return self._popularity_fallback(user_id, n, region, fresh_only)

    def _popularity_fallback(self, user_id: int, n: int, region: int | None = None,
                             fresh_only: bool = True) -> list[int]:
        """Articles populaires : d'abord la région, puis la fenêtre récente, puis tout.

        Ordre de préférence délibéré. La popularité **récente** est de loin la plus
        précise (0,2525 contre 0,0010 sur tout l'historique) ; la popularité
        régionale reste prioritaire quand la région est connue, car elle ajoute la
        seule information disponible sur un lecteur inconnu.
        """
        seen = set(self._seen(user_id).tolist())

        # Ordre : fraîcheur, puis région, puis historique complet. La fraîcheur
        # passe devant car elle est mesurée bien supérieure (0,2525 contre 0,0010) ;
        # `popular_by_region` est calculé sur tout l'historique et souffre donc du
        # même défaut que `popular_articles`. Le calculer aussi sur la fenêtre est
        # la suite logique (voir docs/architecture.md §4.c).
        ranking = None
        if fresh_only and self.popular_recent.size > n:
            ranking = self.popular_recent
        if ranking is None:
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
