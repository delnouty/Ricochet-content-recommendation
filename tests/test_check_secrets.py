"""Le détecteur de secrets doit détecter — et se taire sur les gabarits.

Une vérification de sécurité sans test est une vérification qu'on croit avoir.
Celle-ci a remplacé un contrôle trop étroit (il ne cherchait que des affectations
`AZURE_STORAGE_CONNECTION_STRING=` dans les `.py` et `.ipynb`) : ces tests
fixent ce qu'elle doit attraper, pour qu'un futur allègement d'expression
régulière ne rétrécisse pas la couverture en silence.

Les valeurs ci-dessous sont **factices** : elles ont la forme d'un secret, pas la
valeur d'un secret.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "scripts"))

from check_secrets import examiner  # noqa: E402

CLE_FACTICE = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCdEfGh=="
COMPTE_FACTICE = "A" * 84 + "=="

A_DETECTER = [
    ("chaîne de connexion complète",
     f"DefaultEndpointsProtocol=https;AccountName=stfaux;"
     f"AccountKey={COMPTE_FACTICE};EndpointSuffix=core.windows.net"),
    ("clé de compte seule", f"AccountKey={COMPTE_FACTICE}"),
    ("clé de fonction dans une URL",
     f'curl "https://x.azurewebsites.net/api/recommend?user_id=0&code={CLE_FACTICE}"'),
    ("jeton Hugging Face", "token = hf_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"),
    ("jeton GitHub", "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz01234"),
    ("identifiant AWS", "AKIAIOSFODNN7EXAMPLE"),
    ("clé privée", "-----BEGIN RSA PRIVATE KEY-----"),
    ("secret nommé en dur", f'FUNCTION_KEY = "{CLE_FACTICE}"'),
    ("signature SAS", "https://x.blob.core.windows.net/c/b?sig=" + "a" * 40),
]

A_IGNORER = [
    ("variable shell", 'curl "https://x/api/recommend?user_id=0&code=$key"'),
    ("variable PowerShell", 'curl "https://x/api/recommend?user_id=0&code=${KEY}"'),
    ("gabarit entre chevrons", 'curl "https://x/api/recommend?code=<CLE>"'),
    ("jeton tronqué dans la doc", 'HF_TOKEN = "hf_..."'),
    ("gabarit en français", 'AZURE_STORAGE_CONNECTION_STRING = "<votre-chaine>"'),
    ("nom de variable seul", "définir AZURE_STORAGE_CONNECTION_STRING avant de lancer"),
    ("commande az sans valeur",
     "az functionapp function keys list --query default -o tsv"),
]


@pytest.mark.parametrize("libelle,ligne", A_DETECTER,
                         ids=[x[0] for x in A_DETECTER])
def test_detecte(libelle, ligne):
    assert examiner(ligne, "essai.md"), f"non détecté : {libelle}"


@pytest.mark.parametrize("libelle,ligne", A_IGNORER,
                         ids=[x[0] for x in A_IGNORER])
def test_ignore_les_gabarits(libelle, ligne):
    trouves = examiner(ligne, "essai.md")
    assert not trouves, f"faux positif sur {libelle} : {trouves}"


def test_la_sortie_ne_revele_pas_le_secret():
    """La sortie de CI est publique : le secret doit être masqué.

    Signaler une fuite en la recopiant intégralement dans un journal de build
    consultable la rendrait pire.
    """
    trouves = examiner(f'FUNCTION_KEY = "{CLE_FACTICE}"', "essai.md")
    assert trouves
    assert CLE_FACTICE not in "\n".join(trouves), "le secret apparaît en clair"
    assert "…" in "\n".join(trouves), "aucun masquage visible"


def test_le_numero_de_ligne_est_juste():
    texte = "\n".join(["ligne propre", "autre ligne", f'FUNCTION_KEY = "{CLE_FACTICE}"'])
    trouves = examiner(texte, "essai.md")
    assert trouves and trouves[0].startswith("essai.md:3"), trouves


def test_le_depot_reel_est_propre():
    """Test de non-régression sur le dépôt lui-même.

    Il échoue le jour où un secret est ajouté à un fichier suivi — c'est-à-dire
    avant qu'un `git push` ne le publie.
    """
    from check_secrets import examiner_arbre

    import os
    ancien = os.getcwd()
    os.chdir(RACINE)
    try:
        assert examiner_arbre() == []
    finally:
        os.chdir(ancien)
