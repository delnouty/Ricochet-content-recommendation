"""Fraîcheur du cache d'artefacts de la Function.

Ces tests couvrent le défaut qui a fait servir deux modèles différents par le même
service : la validité du cache local était jugée sur le **nom et la taille** du
fichier. Un SVD reconstruit avec une autre définition de note garde exactement la
même taille — même nombre de lecteurs, même nombre de facteurs — donc les
instances dont le cache avait survécu ne le retéléchargeaient jamais.

Mesuré avant correction : sur dix appels identiques, six réponses venaient du
nouveau modèle et quatre de l'ancien, sans qu'aucune erreur ne se lève.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "azure_function"))

from shared_code.blob_utils import _a_jour  # noqa: E402


class BlobFactice:
    """Le minimum de l'interface `BlobProperties` utilisé par `_a_jour`."""

    def __init__(self, size: int, last_modified: datetime | None):
        self.size = size
        self.last_modified = last_modified


def _fichier(tmp_path: Path, octets: int, age_secondes: float = 0) -> Path:
    chemin = tmp_path / "artefact.npy"
    chemin.write_bytes(b"\0" * octets)
    if age_secondes:
        quand = chemin.stat().st_mtime - age_secondes
        os.utime(chemin, (quand, quand))
    return chemin


def test_absent_donc_a_telecharger(tmp_path):
    blob = BlobFactice(10, datetime.now(tz=timezone.utc))
    assert not _a_jour(tmp_path / "jamais_ecrit.npy", blob)


def test_taille_differente_donc_a_telecharger(tmp_path):
    chemin = _fichier(tmp_path, 10)
    blob = BlobFactice(20, datetime.now(tz=timezone.utc) - timedelta(days=1))
    assert not _a_jour(chemin, blob)


def test_meme_taille_mais_blob_plus_recent(tmp_path):
    """Le cas du défaut : taille identique, contenu différent.

    Sans la comparaison de dates, ce test échoue — et c'est exactement ce qui
    s'est produit en production.
    """
    chemin = _fichier(tmp_path, 10, age_secondes=3600)
    blob = BlobFactice(10, datetime.now(tz=timezone.utc))
    assert not _a_jour(chemin, blob)


def test_meme_taille_et_cache_a_jour(tmp_path):
    """Cas normal d'une invocation à chaud : rien à retélécharger."""
    chemin = _fichier(tmp_path, 10)
    blob = BlobFactice(10, datetime.now(tz=timezone.utc) - timedelta(hours=1))
    assert _a_jour(chemin, blob)


def test_tolerance_d_une_seconde(tmp_path):
    """Une seconde d'écart ne déclenche pas un téléchargement inutile.

    Les horodatages HTTP et ceux du système de fichiers n'ont pas la même
    résolution ; sans tolérance, chaque démarrage retéléchargerait 253 Mo.
    """
    chemin = _fichier(tmp_path, 10)
    blob = BlobFactice(10, datetime.fromtimestamp(chemin.stat().st_mtime + 0.5,
                                                  tz=timezone.utc))
    assert _a_jour(chemin, blob)


def test_blob_sans_date(tmp_path):
    """Sans date côté service, la taille est la seule information disponible."""
    chemin = _fichier(tmp_path, 10)
    assert _a_jour(chemin, BlobFactice(10, None))
    assert not _a_jour(chemin, BlobFactice(11, None))
