"""Porte de qualité : refuse une régression de performance.

C'est la pièce qui distingue un pipeline MLOps d'un simple entraînement automatisé.
Un modèle ré-entraîné ne doit pas être publié sans preuve qu'il ne dégrade pas le
service. Ce script compare les métriques d'un entraînement aux métriques de
référence et sort en erreur si la baisse dépasse une tolérance.

Usage dans une CI :

    python -m src.evaluate --out-dir models_split --split test --json metrics.json
    python scripts/check_metrics.py --candidate metrics.json \\
        --baseline models/baseline_metrics.json --tolerance 0.10

Codes de sortie : 0 = publication autorisée, 1 = régression détectée.

La référence est un fichier versionné dans le dépôt : elle n'est mise à jour que
délibérément, par une personne, avec `--promote`. Sans cette règle, la référence
suivrait la dérive du modèle et la porte ne protégerait plus rien.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Métriques où une baisse est une régression (les autres sont informatives).
SURVEILLEES = ("HitRate@5", "Recall@5")


def charger(chemin: Path) -> dict:
    with open(chemin, encoding="utf-8") as f:
        donnees = json.load(f)
    if "metrics" not in donnees:
        raise ValueError(f"{chemin} : clé 'metrics' absente")
    return donnees


def comparer(candidat: dict, reference: dict, tolerance: float) -> tuple[bool, list[str]]:
    """Renvoie (publication_autorisée, lignes de rapport)."""
    lignes = []
    ok = True

    for metrique in SURVEILLEES:
        nouveau = candidat["metrics"].get(metrique)
        ancien = reference["metrics"].get(metrique)
        if nouveau is None or ancien is None:
            lignes.append(f"  ?  {metrique:12s} absente d'un des deux fichiers")
            continue

        if ancien == 0:
            variation = 0.0 if nouveau == 0 else 1.0
        else:
            variation = (nouveau - ancien) / ancien

        seuil_atteint = variation < -tolerance
        marque = "!!" if seuil_atteint else "ok"
        lignes.append(f"  {marque} {metrique:12s} {ancien:.4f} -> {nouveau:.4f} "
                      f"({variation:+.1%})")
        if seuil_atteint:
            ok = False

    for metrique, valeur in candidat["metrics"].items():
        if metrique not in SURVEILLEES:
            ancien = reference["metrics"].get(metrique)
            suffixe = f" (référence {ancien})" if ancien is not None else ""
            lignes.append(f"  -- {metrique:12s} {valeur}{suffixe}   [informatif]")

    return ok, lignes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidate", required=True, type=Path,
                        help="métriques du modèle fraîchement entraîné")
    parser.add_argument("--baseline", default=Path("models/baseline_metrics.json"),
                        type=Path, help="métriques de référence, versionnées")
    parser.add_argument("--tolerance", default=0.10, type=float,
                        help="baisse relative acceptée (0.10 = 10 %%)")
    parser.add_argument("--promote", action="store_true",
                        help="remplacer la référence par le candidat (acte délibéré)")
    args = parser.parse_args()

    candidat = charger(args.candidate)

    if not args.baseline.exists():
        print(f"Aucune référence en {args.baseline} : premier entraînement.")
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(candidat, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
        print("Référence initialisée. Pensez à la versionner dans git.")
        return 0

    reference = charger(args.baseline)

    print(f"candidat  : {args.candidate}  ({candidat.get('run_name', 'sans nom')})")
    print(f"référence : {args.baseline}  ({reference.get('run_name', 'sans nom')})")
    print(f"tolérance : {args.tolerance:.0%} de baisse relative\n")

    ok, lignes = comparer(candidat, reference, args.tolerance)
    print("\n".join(lignes))
    print()

    if args.promote:
        args.baseline.write_text(json.dumps(candidat, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
        print("Référence mise à jour (--promote). Commiter le fichier.")
        return 0

    if ok:
        print("PASS — pas de régression au-delà de la tolérance.")
        return 0

    print("ECHEC — régression détectée. Publication bloquée.", file=sys.stderr)
    print("Si la baisse est attendue (changement de protocole, de données), "
          "relancer avec --promote après vérification humaine.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
