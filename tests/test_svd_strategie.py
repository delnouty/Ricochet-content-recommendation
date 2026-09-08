"""`svd_strategie` : entraîner un SVD pour la mesure, sans toucher aux artefacts.

Ces tests couvrent le défaut qui a motivé la fonction. Le notebook 07 affichait une
ligne « SVD (étoiles) » dont les chiffres provenaient en réalité de la variante
binaire, parce que la ligne lisait `models_split/` au lieu d'entraîner la variante
qu'elle annonçait. Aucune erreur ne se levait : seule l'étiquette était fausse.

Le point délicat de la correction est la **copie superficielle** du
`Recommender` : sans elle, construire une seconde variante écraserait les facteurs
de la première, et deux lignes d'un même tableau mesureraient le même modèle.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.evaluate import svd_strategie
from src.recommender import Recommender


@pytest.fixture
def clics() -> pd.DataFrame:
    """Clics jouets : deux groupes de lecteurs aux goûts opposés.

    Les lecteurs 100 à 103 lisent les articles 0-1, les lecteurs 200 à 203 les
    articles 2-3. De quoi donner au SVD un signal à factoriser.
    """
    lignes = []
    for lecteur in (100, 101, 102, 103):
        for article in (0, 1):
            lignes.append((lecteur, article))
    for lecteur in (200, 201, 202, 203):
        for article in (2, 3):
            lignes.append((lecteur, article))
    # Quelques clics sur 4 et 5, pour que le vivier ait des articles non lus.
    for lecteur in (100, 200):
        lignes.append((lecteur, 4))
    return pd.DataFrame(lignes, columns=["user_id", "click_article_id"])


def test_classement_reste_dans_le_vivier(models_dir, clics):
    """La stratégie ne propose que des articles du vivier fourni."""
    reco = Recommender(models_dir)
    vivier = np.array([2, 3, 4, 5], dtype=np.int64)

    strategie = svd_strategie(reco, clics, vivier, negatives=2, factors=2, epochs=5)
    propositions = strategie(200, 3)

    assert propositions, "le SVD doit classer quelque chose pour un lecteur connu"
    assert set(propositions) <= set(vivier.tolist())


def test_deux_variantes_ne_s_ecrasent_pas(models_dir, clics):
    """Construire une seconde variante ne doit pas modifier la première.

    C'est la garantie qu'apporte la copie superficielle. Sans elle, les deux
    stratégies partageraient les facteurs du dernier entraînement, et un tableau
    comparant deux variantes comparerait deux fois la même.
    """
    reco = Recommender(models_dir)
    vivier = np.array([0, 1, 2, 3, 4, 5], dtype=np.int64)

    # Deux entraînements volontairement dissemblables : peu de négatifs contre
    # beaucoup, ce qui déplace nettement les scores.
    premiere = svd_strategie(reco, clics, vivier, negatives=1, factors=2, epochs=5)
    avant = premiere(100, 5)

    seconde = svd_strategie(reco, clics, vivier, negatives=8, factors=4, epochs=20)
    seconde(100, 5)

    assert premiere(100, 5) == avant, (
        "la première stratégie a changé de réponse après la construction de la "
        "seconde : les facteurs sont partagés")


def test_le_recommender_d_origine_reste_intact(models_dir, clics):
    """Les artefacts chargés ne sont pas remplacés par l'entraînement de mesure.

    `models_dir` ne contient aucun artefact SVD : après l'appel, le
    `Recommender` doit toujours l'ignorer, sinon la stratégie « svd » de
    l'application se mettrait à répondre avec un modèle de mesure.
    """
    reco = Recommender(models_dir)
    assert not reco._has_svd

    svd_strategie(reco, clics, np.array([0, 1, 2], dtype=np.int64),
                  negatives=1, factors=2, epochs=5)

    assert not reco._has_svd, "l'entraînement de mesure a fui dans le Recommender"


def test_variante_etoiles_exige_les_etoiles(models_dir, clics):
    """Sans `models_dir`, la variante « étoiles » refuse plutôt que de deviner."""
    reco = Recommender(models_dir)
    with pytest.raises(ValueError, match="étoiles"):
        svd_strategie(reco, clics, np.array([0, 1], dtype=np.int64), negatives=0)
