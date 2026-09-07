"""COPIE DÉPLOYÉE (solution locale) — générée depuis src/recommender.py.

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

        # Un identifiant hors catalogue ferait échouer l'indexation des embeddings
        # (IndexError). Cas réel : artefacts d'historique et catalogue
        # désynchronisés — par exemple après un ajout d'articles suivi d'une
        # reconstruction sur un catalogue plus petit.
        hors_catalogue = 0
        for user_id, articles in list(self.user_clicks.items()):
            valides = articles[articles < self.n_articles]
            if valides.size != articles.size:
                hors_catalogue += int(articles.size - valides.size)
                self.user_clicks[user_id] = valides
        if hors_catalogue:
            print(f"[recommender] {hors_catalogue} clic(s) hors catalogue ignoré(s)")

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

        # Vivier de candidats : fenêtre plus large que le classement (6 h contre 1 h).
        # Les deux optima diffèrent — une fenêtre étroite est la meilleure pour
        # classer par popularité, mais laisse trop peu d'articles à départager au
        # contenu. À défaut d'artefact dédié, on réutilise le classement.
        cand_file = self.models_dir / "candidates_recent.npy"
        self.candidates_recent = (np.load(cand_file) if cand_file.exists()
                                  else self.popular_recent)
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
        """Articles déjà cliqués par l'utilisateur (vide si inconnu).

        Les identifiants hors catalogue sont écartés ici, et non seulement au
        chargement : `user_clicks` est un dictionnaire public, que l'application
        alimente après coup avec l'historique des clients inscrits
        (`sync_store_into_model`). Un identifiant obsolète y provoquerait un
        `IndexError` à l'indexation des embeddings.
        """
        seen = self.user_clicks.get(user_id)
        if seen is None or len(seen) == 0:
            return np.array([], dtype=np.int64)
        seen = np.asarray(seen, dtype=np.int64)
        return seen[(seen >= 0) & (seen < self.n_articles)]

    def _candidates(self, fresh_only: bool, n: int) -> np.ndarray | None:
        """Vivier de candidats : articles récents, ou None pour tout le catalogue.

        Renvoie None si le vivier est absent ou trop petit pour remplir un top-n :
        mieux vaut un classement sur tout le catalogue qu'une liste tronquée.
        """
        if not fresh_only or self.candidates_recent.size <= n:
            return None
        # Un article du vivier absent du catalogue (artefacts désynchronisés) ferait
        # échouer l'indexation : on le filtre.
        pool = self.candidates_recent[self.candidates_recent < self.n_articles]
        return pool if pool.size > n else None

    @staticmethod
    def _argtop(scores: np.ndarray, n: int) -> np.ndarray:
        """Indices des n meilleurs scores finis, du meilleur au moins bon.

        Les scores à -inf (articles exclus) sont écartés : on préfère renvoyer moins
        de n articles qu'un article déjà lu.
        """
        k = min(n, scores.size)
        idx = np.argpartition(-scores, k - 1)[:k]
        idx = idx[np.argsort(-scores[idx])]
        return idx[np.isfinite(scores[idx])]

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
        return [int(a) for a in pool[self._argtop(scores, n)]]

    def _collaborative(self, user_id: int, n: int,
                       pool: np.ndarray | None = None) -> list[int] | None:
        if not self._has_cf or user_id not in self.cf_user_index:
            return None
        row = self.cf_user_index[user_id]
        scores = self.cf_item_factors @ self.cf_user_factors[row]
        seen = self._seen(user_id)

        if pool is not None:
            # On restreint aux colonnes dont l'article est dans le vivier récent.
            # Même si le vivier contient peu d'articles connus du modèle : renvoyer
            # moins de n articles frais est correct, retomber sur le catalogue
            # entier serait un contournement silencieux de la fraîcheur demandée.
            garde = np.isin(self.cf_item_ids, pool)
            if not garde.any():
                return None      # aucun article frais connu : cold start assumé
            ids = self.cf_item_ids[garde]
            sous_scores = scores[garde].copy()
            sous_scores[np.isin(ids, seen)] = -np.inf
            return [int(a) for a in ids[self._argtop(sous_scores, n)]]

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
            if not garde.any():
                return None
            ids = self.svd_item_ids[garde]
            sous = scores[garde].copy()
            sous[np.isin(ids, seen)] = -np.inf
            return [int(a) for a in ids[self._argtop(sous, n)]]

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
            # Les articles absents du modèle ALS (87 % du catalogue) reçoivent le
            # **minimum** de l'échelle, pas 0 : avec 0, un article inconnu se
            # classerait devant les 43 % d'articles que le modèle note négativement,
            # c'est-à-dire devant ceux qu'il déconseille explicitement.
            cf_full = np.full(self.n_articles, cf_raw.min(), dtype=np.float32)
            cf_full[self.cf_item_ids] = cf_raw
            combined = alpha * combined + (1 - alpha) * _minmax(cf_full[indices])

        scores = combined.astype(np.float32)
        scores[np.isin(indices, seen)] = -np.inf
        return [int(a) for a in indices[self._argtop(scores, n)]]

    def _mix(self, user_id: int, n: int, pool: np.ndarray | None = None,
             places_contenu: int = 1, region: int | None = None,
             fresh_only: bool = True) -> list[int] | None:
        """Stratégie retenue en production : popularité récente + une place au contenu.

        Composition mesurée sur validation puis confirmée sur test :

            5 places popularité        HitRate@5 0,2190 | couverture 0,004 %
            4 popularité + 1 contenu   HitRate@5 0,2190 | couverture 0,130 %
            3 popularité + 2 contenu   HitRate@5 0,2100 | couverture 0,194 %

        La première place donnée au contenu **ne coûte rien** en précision et
        multiplie la couverture du catalogue par 32 ; la deuxième coûte 4 %. Une
        place donnée à l'ALS, elle, coûte 3,7 % pour un gain de couverture neuf fois
        plus faible — d'où son absence ici (les facteurs ALS et SVD restent
        disponibles via les stratégies `collab` et `svd`, mais ne sont pas servis).
        """
        places_popularite = max(0, n - places_contenu)

        # Les places « popularité » passent par la cascade de repli, et non par un
        # classement choisi ici : c'est elle qui croise région et fraîcheur, et qui
        # garantit de ne jamais renvoyer une liste vide.
        out = list(self._popularity_fallback(user_id, places_popularite, region,
                                             fresh_only))

        # Le contenu complète ; il peut ne rien renvoyer (lecteur sans historique),
        # auquel cas la liste reste purement populaire — comportement voulu en
        # cold start.
        for article in (self._content_based(user_id, n, pool) or []):
            if len(out) >= n:
                break
            if article not in out:
                out.append(article)

        return out or None

    # ----------------------------------------------------------------- public
    def recommend(self, user_id: int, n: int = 5, method: str = "mix",
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
            "mix": self._mix,
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
        if method == "mix":
            # `mix` a besoin du contexte complet : ses places populaires empruntent
            # la cascade de repli, qui dépend de la région et de la fraîcheur.
            result = self._mix(user_id, n, pool, region=region,
                               fresh_only=fresh_only) or []
        else:
            result = dispatch[method](user_id, n, pool) or []

        if len(result) >= n:
            return result[:n]

        # Complément : une stratégie restreinte à un vivier peut épuiser ses
        # candidats (lecteur assidu, vivier étroit). On complète avec le repli
        # populaire plutôt que de servir une liste courte — voire vide.
        complement = self._popularity_fallback(user_id, n + len(result), region,
                                               fresh_only)
        for article in complement:
            if article not in result:
                result.append(article)
            if len(result) == n:
                break
        return result

    def _popularity_fallback(self, user_id: int, n: int, region: int | None = None,
                             fresh_only: bool = True) -> list[int]:
        """Articles populaires, par **cascade** de classements complémentaires.

        Deux principes, tirés des mesures :

        1. la fraîcheur d'abord (0,2525 contre 0,0010 sur tout l'historique) ;
        2. **jamais de liste vide**. Chaque classement est épuisable : un lecteur
           assidu peut avoir lu tous les articles de la fenêtre. On enchaîne donc
           les classements jusqu'à réunir n articles, en terminant par la popularité
           sur tout l'historique, qui compte des dizaines de milliers d'articles.

        La région intervient **à l'intérieur** de la fenêtre récente quand c'est
        possible : c'est la seule façon d'utiliser les deux signaux à la fois.
        Croiser région et fraîcheur dès la construction des artefacts serait plus
        propre (voir docs/architecture.md §4.c) ; ce croisement à la lecture est en
        attendant ce qui évite d'ignorer purement et simplement la région.
        """
        seen = set(self._seen(user_id).tolist())
        frais = set(int(a) for a in self.popular_recent) if fresh_only else set()

        classements: list[np.ndarray] = []
        region_ranking = self._region_ranking(region, seen)

        if region_ranking is not None and frais:
            # Articles de la région **présents dans la fenêtre**, dans l'ordre de
            # popularité régionale : les deux signaux sont respectés.
            croise = np.array([a for a in region_ranking if int(a) in frais],
                              dtype=np.int64)
            if croise.size:
                classements.append(croise)

        if fresh_only and self.popular_recent.size:
            classements.append(self.popular_recent)
        if region_ranking is not None:
            classements.append(region_ranking)
        classements.append(self.popular_articles)

        out: list[int] = []
        deja = set(seen)
        for ranking in classements:
            for article in ranking:
                article = int(article)
                if article in deja:
                    continue
                out.append(article)
                deja.add(article)
                if len(out) == n:
                    return out
        return out

    def _region_ranking(self, region: int | None,
                        seen: set[int]) -> np.ndarray | None:
        """Classement régional, ou None si la région est inconnue.

        Aucune condition de longueur : c'est la cascade de `_popularity_fallback`
        qui garantit d'atteindre n articles. Exiger `len >= n` conduisait à jeter
        l'information régionale dès que la région comptait peu d'articles — alors
        que servir les deux articles régionaux disponibles puis compléter est
        strictement meilleur que les ignorer.
        """
        if region is None:
            return None
        ranking = self.popular_by_region.get(int(region))
        if ranking is None or ranking.size == 0:
            return None
        return ranking if any(int(a) not in seen for a in ranking) else None


def _minmax(x: np.ndarray) -> np.ndarray:
    """Normalisation min-max robuste (renvoie des zéros si tout est égal)."""
    lo, hi = x.min(), x.max()
    if hi - lo < 1e-12:
        return np.zeros_like(x)
    return (x - lo) / (hi - lo)
