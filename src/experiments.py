"""Boîte à outils commune aux notebooks d'expérimentation (03 à 07).

Chaque notebook règle **une** méthode, mais tous doivent partager exactement le
même protocole, sinon les chiffres ne sont pas comparables :

  - même découpage temporel 60 / 20 / 20 (`load_split`) ;
  - mêmes lecteurs évalués (`eval_users`) ;
  - mêmes métriques (`metrics`).

Règle de méthode : le réglage se fait **uniquement sur la période de validation**.
La période de test reste intacte jusqu'à la mesure finale, effectuée une seule fois
avec la meilleure configuration de chaque méthode.

Les artefacts attendus dans `models_split/` sont ceux construits sur la seule
période d'entraînement (`python -m src.evaluate --out-dir models_split`).
"""

from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pandas as pd

HEURE_MS = 3600 * 1000


# ------------------------------------------------------------------ découpage
def load_split(data_dir: Path, train: float = 0.6, val: float = 0.2
               ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Charge les clics et applique le découpage temporel 60 / 20 / 20."""
    from src.evaluate import split_by_time
    from src.prepare_model import load_clicks

    return split_by_time(load_clicks(data_dir), train=train, val=val)


def recent_pool(clicks_train: pd.DataFrame, hours: float) -> np.ndarray:
    """Articles cliqués pendant les `hours` dernières heures de l'entraînement.

    Renvoyés **triés par popularité décroissante** sur cette fenêtre : le tableau
    sert donc à la fois de vivier de candidats et de classement par popularité.

    C'est la notion de « fraîcheur » du projet : sans elle, une méthode choisit
    parmi 364 047 articles dont la plupart ont des années.
    """
    fin = int(clicks_train["click_timestamp"].max())
    fenetre = clicks_train[clicks_train["click_timestamp"] >= fin - hours * HEURE_MS]
    ordre = fenetre["click_article_id"].value_counts().index.to_numpy().astype(np.int64)
    return ordre


# ------------------------------------------------------------------ évaluation
def eval_users(reco, clicks_eval: pd.DataFrame, max_users: int = 2000
               ) -> tuple[list[int], pd.Series]:
    """Lecteurs connus à l'entraînement et actifs pendant la période d'évaluation.

    Vérité terrain : l'ensemble des articles qu'ils ont réellement ouverts pendant
    cette période. On exclut les lecteurs inconnus — mesurer le cold start est une
    autre question que mesurer la qualité des recommandations.
    """
    cible = (clicks_eval.groupby("user_id")["click_article_id"]
             .apply(lambda s: {int(a) for a in s}))
    connus = [int(u) for u in cible.index if int(u) in reco.user_clicks][:max_users]
    return connus, cible


def metrics(fonction, users: list[int], cible: pd.Series, n: int = 5,
            n_articles: int = 364047) -> dict:
    """HitRate, Recall, couverture et personnalisation d'une stratégie.

    - HitRate@n : au moins un article recommandé a été lu ;
    - Recall@n : part des articles réellement lus qui figuraient dans le top-n ;
    - couverture : part du catalogue apparaissant dans les recommandations ;
    - personnalisation : 1 − recouvrement moyen entre deux listes de lecteurs.
      Une valeur basse signale une méthode qui sert presque la même liste à tous.
    """
    succes = rappel = 0.0
    listes = []
    for u in users:
        attendu = cible[u]
        recs = fonction(u, n)
        trouves = len(attendu & set(recs))
        succes += trouves > 0
        rappel += trouves / len(attendu)
        listes.append(set(recs))

    couverture = len({a for liste in listes for a in liste}) / n_articles
    paires = list(itertools.islice(itertools.combinations(range(len(listes)), 2), 3000))
    recouvrement = float(np.mean([len(listes[i] & listes[j]) / n for i, j in paires])) \
        if paires else 0.0
    return {f"HitRate@{n}": round(succes / len(users), 4),
            f"Recall@{n}": round(rappel / len(users), 4),
            "couverture %": round(couverture * 100, 3),
            "personnalisation %": round((1 - recouvrement) * 100, 1)}


def compare(configurations: dict, users: list[int], cible: pd.Series, n: int = 5,
            n_articles: int = 364047) -> pd.DataFrame:
    """Applique `metrics` à un dictionnaire {nom: fonction} et renvoie un tableau."""
    lignes = []
    for nom, fonction in configurations.items():
        ligne = {"configuration": nom}
        ligne.update(metrics(fonction, users, cible, n=n, n_articles=n_articles))
        lignes.append(ligne)
    return pd.DataFrame(lignes).set_index("configuration")


# ------------------------------------------------------------------ stratégies
def make_popularity(pool: np.ndarray):
    """Les articles les plus lus de la fenêtre, identiques pour tout le monde."""
    def strategie(user_id: int, n: int) -> list[int]:
        return [int(a) for a in pool[:n]]
    return strategie


def make_content(reco, pool: np.ndarray, last_k: int | None = None):
    """Similarité de contenu, restreinte au vivier `pool`.

    `last_k` limite le profil aux **k derniers** articles lus : sur un flux
    d'actualité, un intérêt d'il y a dix jours n'a pas la même valeur qu'un intérêt
    d'hier. `None` utilise tout l'historique (comportement de `Recommender`).
    """
    def strategie(user_id: int, n: int) -> list[int]:
        vus = reco.user_clicks.get(int(user_id))
        if vus is None or len(vus) == 0:
            return []
        if last_k is not None:
            vus = vus[-last_k:]
        profil = reco.embeddings[vus].mean(axis=0)
        norme = np.linalg.norm(profil)
        if norme == 0:
            return []
        scores = reco.embeddings[pool] @ (profil / norme)
        return [int(a) for a in pool[np.argsort(-scores)[:n]]]
    return strategie


def make_als(reco, pool: np.ndarray):
    """Facteurs ALS déjà chargés par `Recommender`, restreints au vivier."""
    garde = np.isin(reco.cf_item_ids, pool)
    ids = reco.cf_item_ids[garde]

    def strategie(user_id: int, n: int) -> list[int]:
        row = reco.cf_user_index.get(int(user_id))
        if row is None or ids.size < n:
            return []
        scores = (reco.cf_item_factors[garde] @ reco.cf_user_factors[row])
        return [int(a) for a in ids[np.argsort(-scores)[:n]]]
    return strategie


def make_svd(reco, pool: np.ndarray):
    """Facteurs SVD (Surprise) déjà chargés, restreints au vivier."""
    garde = np.isin(reco.svd_item_ids, pool)
    ids = reco.svd_item_ids[garde]

    def strategie(user_id: int, n: int) -> list[int]:
        row = reco.svd_user_index.get(int(user_id))
        if row is None or ids.size < n:
            return []
        scores = (reco.svd_global_mean + reco.svd_user_bias[row]
                  + reco.svd_item_bias[garde]
                  + reco.svd_item_factors[garde] @ reco.svd_user_factors[row])
        return [int(a) for a in ids[np.argsort(-scores)[:n]]]
    return strategie


def make_mix(principale, secondaire, places_secondaire: int = 1):
    """Liste mixte : on réserve `places_secondaire` places à la seconde stratégie.

    Sert à mesurer le coût d'exposition : chaque place donnée à la personnalisation
    est une place retirée à la stratégie la plus précise.
    """
    def strategie(user_id: int, n: int) -> list[int]:
        garde = max(0, n - places_secondaire)
        out = list(principale(user_id, garde))
        for article in secondaire(user_id, n * 2):
            if len(out) >= n:
                break
            if article not in out:
                out.append(article)
        return out[:n]
    return strategie


# --------------------------------------------------- ré-entraînement ALS ciblé
def train_als_window(clicks_train: pd.DataFrame, hours: float | None,
                     factors: int = 50, iterations: int = 15):
    """Entraîne un ALS sur les `hours` dernières heures seulement.

    Question posée : un modèle collaboratif appris sur dix jours d'actualité est-il
    battu par le même modèle appris sur les dernières 24 heures ? Les artefacts du
    dépôt utilisent toute la période, ce qui n'est pas forcément le bon choix pour
    un flux.

    Renvoie une fonction de stratégie, restreinte plus tard au vivier via `pool`.
    """
    from scipy.sparse import coo_matrix

    if hours is not None:
        fin = int(clicks_train["click_timestamp"].max())
        clicks_train = clicks_train[clicks_train["click_timestamp"] >= fin - hours * HEURE_MS]

    users = clicks_train["user_id"].to_numpy(dtype=np.int64)
    items = clicks_train["click_article_id"].to_numpy(dtype=np.int64)
    uniq_u, idx_u = np.unique(users, return_inverse=True)
    uniq_i, idx_i = np.unique(items, return_inverse=True)

    matrice = coo_matrix((np.ones(len(clicks_train), dtype=np.float32), (idx_u, idx_i)),
                         shape=(uniq_u.size, uniq_i.size)).tocsr()

    from implicit.als import AlternatingLeastSquares
    try:
        from threadpoolctl import threadpool_limits
        limite = threadpool_limits(1, "blas")
    except ImportError:
        from contextlib import nullcontext
        limite = nullcontext()
    with limite:
        modele = AlternatingLeastSquares(factors=factors, regularization=0.05,
                                         iterations=iterations, random_state=42)
        modele.fit(matrice)

    index_u = {int(u): i for i, u in enumerate(uniq_u)}
    facteurs_u = np.asarray(modele.user_factors, dtype=np.float32)
    facteurs_i = np.asarray(modele.item_factors, dtype=np.float32)
    print(f"[als] fenêtre {hours or 'complète'} h : {uniq_u.size:,} users x "
          f"{uniq_i.size:,} items, {len(clicks_train):,} clics")

    def make(pool: np.ndarray):
        garde = np.isin(uniq_i, pool)
        ids = uniq_i[garde]

        def strategie(user_id: int, n: int) -> list[int]:
            row = index_u.get(int(user_id))
            if row is None or ids.size < n:
                return []
            scores = facteurs_i[garde] @ facteurs_u[row]
            return [int(a) for a in ids[np.argsort(-scores)[:n]]]
        return strategie

    return make
