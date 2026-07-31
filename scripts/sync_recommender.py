"""Synchronise le cœur de reco vers les deux solutions de déploiement.

Source unique de vérité : `src/recommender.py`.
Cibles (copies embarquées, chacune rendant sa solution autonome) :
  - azure_function/shared_code/recommender.py   (solution Azure)
  - spaces/recommender.py                        (solution Hugging Face)
  - local/recommender.py                         (solution locale, sans cloud)

Chaque copie reçoit un en-tête « généré, ne pas éditer » puis le code identique
de la source (tout ce qui suit `from __future__ import annotations`).

Usage :
    python scripts/sync_recommender.py           # met à jour les copies
    python scripts/sync_recommender.py --check    # échoue si une copie diffère (CI)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "recommender.py"
MARKER = "from __future__ import annotations"

TARGETS = {
    ROOT / "azure_function" / "shared_code" / "recommender.py": "solution Azure",
    ROOT / "spaces" / "recommender.py": "solution Hugging Face",
    ROOT / "local" / "recommender.py": "solution locale",
}

HEADER = '''"""Cœur de recommandation — COPIE DÉPLOYÉE ({label}).

⚠️  GÉNÉRÉ par scripts/sync_recommender.py — NE PAS ÉDITER ICI.
    Source unique de vérité : src/recommender.py.
    Régénérer après toute modification : python scripts/sync_recommender.py

À l'inférence : dépend uniquement de numpy + pickle (stdlib).
"""


'''


def _rendered(label: str) -> str:
    """Contenu attendu d'une copie pour l'étiquette donnée."""
    src = SOURCE.read_text(encoding="utf-8")
    idx = src.find(MARKER)
    if idx == -1:
        raise RuntimeError(f"Marqueur '{MARKER}' introuvable dans {SOURCE}")
    return HEADER.format(label=label) + src[idx:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="ne rien écrire ; code de sortie 1 si une copie diffère")
    args = parser.parse_args()

    stale = []
    for path, label in TARGETS.items():
        expected = _rendered(label)
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == expected:
            print(f"[ok]    {path.relative_to(ROOT)}")
            continue
        if args.check:
            stale.append(path.relative_to(ROOT))
            print(f"[stale] {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")
            print(f"[write] {path.relative_to(ROOT)}")

    if args.check and stale:
        print(f"\n{len(stale)} copie(s) désynchronisée(s) — lancer "
              "`python scripts/sync_recommender.py`")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
