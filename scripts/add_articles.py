"""Intègre de nouveaux articles au catalogue, sans ré-entraînement.

Ferme le chemin d'ajout décrit en §4.b de docs/architecture.md :

    embedding brut (250 dim) ─▶ projection ACP persistée ─▶ catalogue réduit (50 dim)

Ce que fait le script :
  1. lit une matrice d'embeddings bruts (`.npy` ou `.pickle`) ;
  2. la projette avec `pca_mean.npy` / `pca_components.npy` — l'ACP n'est **pas**
     réajustée, la base reste celle du catalogue existant ;
  3. l'ajoute à `articles_embeddings_pca.npy` par écriture atomique ;
  4. affiche les `article_id` attribués.

Les `article_id` sont les indices de ligne du catalogue : les nouveaux articles
reçoivent donc les identifiants suivants, à la queue de la matrice.

Ce que le script ne fait **pas**, volontairement :
  - il ne touche pas `popular_articles.npy` : un article sans clic n'a aucune
    popularité, il sera recommandé par similarité de contenu et par là seulement ;
  - il ne touche pas `articles_metadata.csv` (donnée source, pas artefact) : les
    applications afficheront « Article #<id> » sans catégorie ni date ;
  - il ne recharge pas les services : les artefacts sont lus au démarrage, il faut
    redémarrer l'application (et republier vers Blob / HF Hub pour les solutions
    Azure et Hugging Face).

Usage :
    python scripts/add_articles.py --embeddings nouveaux.npy
    python scripts/add_articles.py --embeddings nouveaux.npy --dry-run
    python scripts/add_articles.py --embeddings nouveaux.npy --models-dir /autre/models
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pickle
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.prepare_model import project_embeddings  # noqa: E402

CATALOGUE = "articles_embeddings_pca.npy"


def load_embeddings(path: Path) -> np.ndarray:
    """Charge une matrice d'embeddings bruts depuis un .npy ou un .pickle."""
    if path.suffix == ".npy":
        raw = np.load(path)
    elif path.suffix in {".pickle", ".pkl"}:
        with open(path, "rb") as f:
            raw = pickle.load(f)
    else:
        raise ValueError(f"Format non géré : {path.suffix} (attendu .npy ou .pickle)")

    emb = np.atleast_2d(np.asarray(raw, dtype=np.float32))
    if emb.ndim != 2:
        raise ValueError(f"Matrice attendue en 2 dimensions, obtenu {emb.ndim}")
    if not np.isfinite(emb).all():
        raise ValueError("La matrice contient des valeurs non finies (NaN / inf).")
    return emb


def _row_hashes(matrix: np.ndarray) -> set[bytes]:
    """Empreintes des lignes, pour détecter un ajout déjà effectué."""
    return {hashlib.sha1(row.tobytes()).digest() for row in matrix}


def append_to_catalogue(vectors: np.ndarray, models_dir: Path,
                        catalogue: np.ndarray | None = None) -> tuple[int, int]:
    """Ajoute `vectors` au catalogue réduit. Renvoie (premier_id, dernier_id).

    Écriture atomique : la nouvelle matrice est écrite à côté puis substituée, afin
    qu'une interruption ne laisse pas un artefact de 73 Mo tronqué.

    `catalogue` permet de réutiliser une matrice déjà chargée. Ne jamais passer un
    tableau ouvert en `mmap_mode` : sous Windows, la substitution d'un fichier
    encore mappé échoue avec `PermissionError`.
    """
    catalogue_path = models_dir / CATALOGUE
    if catalogue is None:
        catalogue = np.load(catalogue_path)
    first_id = catalogue.shape[0]

    merged = np.concatenate([catalogue, vectors.astype(catalogue.dtype)], axis=0)

    # Écriture via un descripteur : `np.save` ajouterait sinon un `.npy` au nom du
    # fichier temporaire, et la substitution porterait sur un chemin inexistant.
    tmp = catalogue_path.with_name(catalogue_path.name + ".tmp.npy")
    try:
        with open(tmp, "wb") as handle:
            np.save(handle, merged)
        os.replace(tmp, catalogue_path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

    return first_id, merged.shape[0] - 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--embeddings", required=True, type=Path,
                        help="matrice d'embeddings bruts des nouveaux articles")
    parser.add_argument("--models-dir", default=ROOT / "models", type=Path)
    parser.add_argument("--dry-run", action="store_true",
                        help="projette et affiche, sans rien écrire")
    parser.add_argument("--allow-duplicates", action="store_true",
                        help="ajouter même si des vecteurs identiques existent déjà")
    args = parser.parse_args()

    models_dir: Path = args.models_dir
    for required in (CATALOGUE, "pca_mean.npy", "pca_components.npy"):
        if not (models_dir / required).exists():
            print(f"Artefact manquant : {models_dir / required}\n"
                  "Générez les artefacts d'abord :\n"
                  "  python -m src.prepare_model --data-dir data/raw --out-dir models",
                  file=sys.stderr)
            return 1

    try:
        emb = load_embeddings(args.embeddings)
        vectors = project_embeddings(emb, models_dir)
    except (ValueError, OSError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1

    # Lecture complète (et non mmap) : le descripteur doit être refermé avant la
    # substitution atomique du fichier.
    catalogue = np.load(models_dir / CATALOGUE)
    print(f"[entrée]    {emb.shape[0]} article(s), {emb.shape[1]} dimensions "
          f"-> projeté en {vectors.shape[1]}")
    print(f"[catalogue] {catalogue.shape[0]:,} articles avant ajout")

    if not args.allow_duplicates:
        existing = _row_hashes(catalogue)
        duplicates = [i for i, row in enumerate(vectors)
                      if hashlib.sha1(row.tobytes()).digest() in existing]
        if duplicates:
            print(f"\n{len(duplicates)} vecteur(s) déjà présent(s) dans le catalogue "
                  f"(lignes d'entrée : {duplicates[:10]}"
                  f"{'…' if len(duplicates) > 10 else ''}).\n"
                  "Ces articles ont probablement déjà été ajoutés. Relancez avec "
                  "--allow-duplicates pour forcer l'ajout.", file=sys.stderr)
            return 1

    if args.dry_run:
        first = catalogue.shape[0]
        print(f"\n[dry-run]   aucune écriture. Les article_id attribués seraient "
              f"{first} à {first + vectors.shape[0] - 1}.")
        return 0

    first_id, last_id = append_to_catalogue(vectors, models_dir, catalogue=catalogue)
    print(f"[ajout]     article_id attribués : {first_id} à {last_id}")
    print(f"[catalogue] {last_id + 1:,} articles après ajout")
    print("\nÀ faire ensuite :")
    print("  - redémarrer l'application (les artefacts sont lus au démarrage) ;")
    print("  - republier models/ vers Blob (solution Azure) et/ou le HF Hub "
          "(python spaces/upload_artifacts.py …) ;")
    print("  - les nouveaux articles sont recommandables par similarité de contenu ;")
    print("    ils n'apparaîtront en repli popularité qu'après des clics réels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
