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

# Les appâts sont **assemblés à l'exécution**, jamais écrits en un seul morceau.
# Écrits en clair, ils feraient échouer le détecteur sur son propre fichier de
# test — et la CI serait rouge en permanence. L'alternative, exclure ce chemin
# du balayage, serait une porte laissée ouverte qu'on finirait par oublier :
# mieux vaut qu'aucun fichier suivi ne contienne de chaîne en forme de secret.
_HF = "hf" + "_" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
_GITHUB = "ghp" + "_" + "AbCdEfGhIjKlMnOpQrStUvWxYz01234"
_AWS = "AKIA" + "IOSFODNN7EXAMPLE"
_PRIVEE = "-----BEGIN RSA PRIVATE" + " KEY-----"
_COMPTE = "AccountKey" + "=" + COMPTE_FACTICE
_SAS = "https://x.blob.core.windows.net/c/b?si" + "g=" + "a" * 40

A_DETECTER = [
    ("chaîne de connexion complète",
     f"DefaultEndpointsProtocol=https;AccountName=stfaux;"
     f"{_COMPTE};EndpointSuffix=core.windows.net"),
    ("clé de compte seule", _COMPTE),
    ("clé de fonction dans une URL",
     f'curl "https://x.azurewebsites.net/api/recommend?user_id=0&code={CLE_FACTICE}"'),
    ("jeton Hugging Face", f"token = {_HF}"),
    ("jeton GitHub", _GITHUB),
    ("identifiant AWS", _AWS),
    ("clé privée", _PRIVEE),
    ("secret nommé en dur", f'FUNCTION_KEY = "{CLE_FACTICE}"'),
    # Format `.env` : pas de guillemets. C'est la forme la plus probable d'une
    # fuite accidentelle, et une première version du détecteur exigeait les
    # guillemets — elle serait passée à côté.
    ("secret nommé, format .env", f"FUNCTION_KEY={CLE_FACTICE}"),
    ("chaîne de connexion en .env",
     "AZURE_STORAGE_CONNECTION_STRING=" + _COMPTE),
    ("signature SAS", _SAS),
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
    # Ces trois formes vivent dans `.env.example`, les workflows et la doc :
    # les signaler rendrait la vérification inutilisable.
    ("gabarit .env", "FUNCTION_KEY=<votre-cle-de-fonction>"),
    ("valeur vide en .env", "FUNCTION_KEY="),
    ("substitution GitHub Actions", "FUNCTION_KEY: ${{ secrets.FUNCTION_KEY }}"),
    ("affectation depuis une variable", "FUNCTION_KEY = $nouveau"),
    # Une référence Terraform est la **bonne** pratique : le secret est lu comme
    # attribut de la ressource et n'existe nulle part en clair. Le détecteur l'a
    # signalée quand les guillemets sont devenus optionnels ; découragerait
    # exactement ce qu'on veut voir.
    ("référence Terraform",
     "AZURE_STORAGE_CONNECTION_STRING = "
     "azurerm_storage_account.ricochet.primary_connection_string"),
    ("lecture depuis l'environnement",
     'FUNCTION_KEY = os.environ.get'),
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


def test_liste_d_acceptation_ecarte_par_empreinte():
    """Un constat inscrit dans `.secretsignore` est écarté — et compté.

    L'empreinte porte sur la valeur exacte : accepter un appât ne doit pas
    accepter un secret voisin. Les deux moitiés sont vérifiées ici.
    """
    from check_secrets import empreinte, examiner as ex

    ligne = f'FUNCTION_KEY = "{CLE_FACTICE}"'
    assert ex(ligne, "essai.md"), "sans liste, le constat doit remonter"

    acceptes = {empreinte(CLE_FACTICE): "appât de test"}
    avant = ex.ignores
    assert ex(ligne, "essai.md", acceptes) == [], "le constat accepté remonte encore"
    assert ex.ignores == avant + 1, "l'écart n'a pas été compté"

    # Une valeur différente ne doit pas bénéficier de l'acceptation.
    # Assemblé, et non écrit en f-string : `f'... "{X[:-4]}ZZ=="'` laisserait
    # dans ce fichier un littéral de 22 caractères que le détecteur signalerait.
    # C'est ce test-ci qui l'a montré, en échouant sur son propre fichier.
    autre = 'FUNCTION_KEY = "' + CLE_FACTICE[:-4] + 'ZZ' + '=="'
    assert ex(autre, "essai.md", acceptes), "une valeur voisine a été acceptée"


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
