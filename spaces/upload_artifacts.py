"""Publie les artefacts de `models/` vers un dépôt de modèle HF Hub.

À lancer une fois les artefacts générés (src/prepare_model.py). Le Space HF
les téléchargera ensuite au démarrage.

Usage :
    huggingface-cli login            # ou définir HF_TOKEN
    python spaces/upload_artifacts.py --repo mon-org/my-content-models --models-dir models
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="id du dépôt HF (org/nom)")
    parser.add_argument("--models-dir", default="models", type=Path)
    parser.add_argument("--private", action="store_true", help="dépôt privé")
    args = parser.parse_args()

    from huggingface_hub import HfApi

    api = HfApi(token=os.environ.get("HF_TOKEN"))
    api.create_repo(args.repo, repo_type="model", private=args.private, exist_ok=True)
    api.upload_folder(
        folder_path=str(args.models_dir),
        repo_id=args.repo,
        repo_type="model",
        # `recent_window.json` fait partie des artefacts : sans lui, l'interface
        # ne sait pas de quand date le vivier de fraîcheur.
        allow_patterns=["*.npy", "*.pkl", "recent_window.json"],
    )
    print(f"Artefacts publiés dans https://huggingface.co/{args.repo}")


if __name__ == "__main__":
    main()
