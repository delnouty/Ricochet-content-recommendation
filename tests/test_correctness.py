"""Défauts de correction identifiés par audit, et leurs correctifs.

Chaque test correspond à un défaut réellement observé sur les artefacts complets.
Ils servent de garde-fou : le comportement corrigé n'est pas évident, et une
réécriture future pourrait le perdre sans que rien ne le signale.
"""

import json
import pickle

import numpy as np
import pytest

from recommender import Recommender


def _vivier(models_dir, articles):
    np.save(models_dir / "popular_recent.npy", np.array(articles, dtype=np.int64))
    (models_dir / "recent_window.json").write_text(
        json.dumps({"window_hours_effective": 6}), encoding="utf-8")


def _regions(models_dir, mapping):
    with open(models_dir / "popular_by_region.pkl", "wb") as f:
        pickle.dump({k: np.array(v, dtype=np.int64) for k, v in mapping.items()}, f)


# --------------------------------------------------------------------- défaut 1
def test_jamais_de_liste_vide(models_dir_cf):
    """Un lecteur ayant tout lu dans la fenêtre recevait une liste **vide**.

    Observé sur les artefacts complets : hybrid, content, collab et le repli
    renvoyaient tous `[]`. La cascade de repli doit maintenant aller jusqu'à la
    popularité sur tout l'historique.
    """
    _vivier(models_dir_cf, [2, 3])
    reco = Recommender(models_dir_cf)
    reco.user_clicks[500] = np.array([2, 3], dtype=np.int64)   # a lu tout le vivier

    for methode in ("hybrid", "content", "collab", "svd"):
        recs = reco.recommend(500, n=3, method=methode)
        assert recs, f"{methode} renvoie une liste vide"
        assert not ({2, 3} & set(recs)), f"{methode} recommande un article déjà lu"


def test_complement_jusqu_a_n(models_dir_cf):
    """Une stratégie qui épuise son vivier doit être complétée, pas tronquée."""
    _vivier(models_dir_cf, [2, 3, 4])
    reco = Recommender(models_dir_cf)
    reco.user_clicks[501] = np.array([2, 3], dtype=np.int64)

    recs = reco.recommend(501, n=4, method="content")
    assert len(recs) == 4, f"attendu 4 articles, obtenu {recs}"
    assert len(set(recs)) == 4, "doublons dans la réponse"


# --------------------------------------------------------------------- défaut 2
def test_region_croisee_avec_la_fraicheur(models_dir):
    """La région était purement ignorée dès que le vivier existait.

    Le correctif croise les deux signaux : articles de la région **présents dans la
    fenêtre**, dans l'ordre de popularité régionale.
    """
    _vivier(models_dir, [0, 1, 2, 3, 4])
    _regions(models_dir, {7: [5, 3, 1, 0]})     # 5 est hors du vivier
    reco = Recommender(models_dir)

    recs = reco.recommend(999, n=3, region=7)

    assert recs == [3, 1, 0], f"croisement région × fraîcheur incorrect : {recs}"
    assert 5 not in recs, "article régional hors fenêtre retenu"


def test_region_seule_si_pas_de_vivier(models_dir):
    """Sans artefact de fraîcheur, la région reste le signal utilisé."""
    _regions(models_dir, {7: [4, 2, 1]})
    reco = Recommender(models_dir)

    recs = reco.recommend(999, n=3, region=7)
    assert recs == [4, 2, 1], f"classement régional attendu, obtenu {recs}"


# --------------------------------------------------------------------- défaut 3
def test_le_vivier_n_est_jamais_contourne(models_dir_cf):
    """`collab` retombait sur tout le catalogue quand le vivier était étroit.

    Conséquence : un appel avec `fresh_only=True` renvoyait des articles anciens.
    Renvoyer moins d'articles frais est correct ; en servir des périmés ne l'est pas.
    """
    _vivier(models_dir_cf, [2, 3])          # 2 articles seulement, on demande 5
    reco = Recommender(models_dir_cf)

    for methode in ("collab", "svd", "content", "hybrid"):
        recs = reco._candidates(True, 5)
        # Le vivier est plus petit que n : `_candidates` le refuse volontairement.
        assert recs is None

    # Appel direct avec un vivier étroit : la stratégie doit s'y tenir.
    frais = reco._collaborative(100, 5, np.array([2, 3], dtype=np.int64))
    assert set(frais) <= {2, 3}, f"collab est sorti du vivier : {frais}"


# --------------------------------------------------------------------- défaut 4
def test_article_inconnu_du_collaboratif_ne_bat_pas_un_article_deconseille(models_dir_cf):
    """Dans l'hybride, les articles absents des facteurs ALS recevaient 0.

    Or 43 % des scores ALS réels sont négatifs : un article inconnu se classait donc
    devant ceux que le modèle déconseille. Il reçoit désormais le minimum de
    l'échelle.
    """
    reco = Recommender(models_dir_cf)
    row = reco.cf_user_index[100]
    cf_raw = reco.cf_item_factors @ reco.cf_user_factors[row]

    cf_full = np.full(reco.n_articles, cf_raw.min(), dtype=np.float32)
    cf_full[reco.cf_item_ids] = cf_raw
    absents = np.setdiff1d(np.arange(reco.n_articles), reco.cf_item_ids)

    if absents.size:
        assert (cf_raw >= cf_full[absents[0]]).all(), \
            "un article connu est noté sous la valeur attribuée aux inconnus"


# --------------------------------------------------------------------- défaut 5
def test_identifiant_hors_catalogue_injecte_apres_chargement(models_dir_cf):
    """`user_clicks` est alimenté après coup par l'application (clients inscrits).

    Un identifiant obsolète provoquait un `IndexError` à l'indexation des
    embeddings. Le filtrage est donc fait dans `_seen`, seul point d'accès.
    """
    reco = Recommender(models_dir_cf)
    reco.user_clicks[502] = np.array([reco.n_articles + 10, 0], dtype=np.int64)

    for methode in ("hybrid", "content", "collab", "svd"):
        recs = reco.recommend(502, n=2, method=methode)   # ne doit pas lever
        assert all(0 <= a < reco.n_articles for a in recs)

    assert reco._seen(502).tolist() == [0], "l'identifiant hors catalogue subsiste"


def test_historique_hors_catalogue_filtre_au_chargement(models_dir, capsys):
    """Un artefact d'historique désynchronisé est nettoyé au chargement, avec trace."""
    with open(models_dir / "user_clicks.pkl", "wb") as f:
        pickle.dump({300: np.array([0, 9999], dtype=np.int64)}, f)

    reco = Recommender(models_dir)

    assert reco.user_clicks[300].tolist() == [0]
    assert "hors catalogue" in capsys.readouterr().out
