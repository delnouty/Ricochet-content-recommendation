"""Synchronise le code partagé vers les solutions de déploiement.

Chaque solution embarque ses propres copies, ce qui la rend autonome (un dossier
copié ailleurs fonctionne tel quel). Le revers est le risque de divergence : ce
script est la garantie, et `--check` le vérifie en CI.

Sources uniques de vérité et cibles :

  src/recommender.py  -> azure_function/shared_code/, spaces/, local/
  src/user_store.py   -> spaces/, local/            (clients inscrits, SQLite)
  src/app_ui.py       -> spaces/ui.py, local/ui.py  (interface Streamlit commune)

L'Azure Function ne reçoit que le cœur : elle n'a ni interface ni base clients.

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
MARKER = "from __future__ import annotations"

# {source: {cible: étiquette}}
SOURCES = {
    ROOT / "src" / "recommender.py": {
        ROOT / "azure_function" / "shared_code" / "recommender.py": "solution Azure",
        ROOT / "spaces" / "recommender.py": "solution Hugging Face",
        ROOT / "local" / "recommender.py": "solution locale",
    },
    ROOT / "src" / "user_store.py": {
        ROOT / "spaces" / "user_store.py": "solution Hugging Face",
        ROOT / "local" / "user_store.py": "solution locale",
    },
    ROOT / "src" / "app_ui.py": {
        ROOT / "spaces" / "ui.py": "solution Hugging Face",
        ROOT / "local" / "ui.py": "solution locale",
    },
}

HEADER = '''"""COPIE DÉPLOYÉE ({label}) — générée depuis src/{source}.

⚠️  NE PAS ÉDITER ICI : toute modification serait écrasée.
    Source unique de vérité : src/{source}
    Régénérer : python scripts/sync_recommender.py
    Vérifier  : python scripts/sync_recommender.py --check   (utilisé en CI)
"""


'''


def _rendered(source: Path, label: str) -> str:
    """Contenu attendu d'une copie : en-tête « généré » + code de la source."""
    src = source.read_text(encoding="utf-8")
    idx = src.find(MARKER)
    if idx == -1:
        raise RuntimeError(f"Marqueur '{MARKER}' introuvable dans {source}")
    return HEADER.format(label=label, source=source.name) + src[idx:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="ne rien écrire ; code de sortie 1 si une copie diffère")
    args = parser.parse_args()

    stale = []
    for source, cibles in SOURCES.items():
        for path, label in cibles.items():
            expected = _rendered(source, label)
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
