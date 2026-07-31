"""Préparation hors-ligne des artefacts de recommandation.

Lit les données brutes (Globo.com) et produit dans `models/` des artefacts
légers, chargés ensuite par `Recommender` (et par l'Azure Function) :

  - articles_embeddings_pca.npy : embeddings réduits par ACP (astuce de Julien
    pour tenir dans les limites du free tier Azure) ;
  - user_clicks.pkl             : dict user_id -> np.ndarray des article_id lus ;
  - popular_articles.npy        : article_id triés par popularité (cold start) ;
  - cf_*.npy / cf_*.pkl         : facteurs ALS du filtrage collaboratif.

Usage :
    python -m src.prepare_model --data-dir data/raw --out-dir models --pca 50
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import numpy as np
import pandas as pd


def load_clicks(data_dir: Path) -> pd.DataFrame:
    """Charge tous les clics depuis un dossier `clicks/` ou un CSV échantillon."""
    clicks_dir = data_dir / "clicks"
    if clicks_dir.is_dir():
        files = sorted(clicks_dir.glob("clicks_hour_*.csv"))
        if not files:
            raise FileNotFoundError(f"Aucun fichier clicks_hour_*.csv dans {clicks_dir}")
        frames = [pd.read_csv(f, usecols=["user_id", "click_article_id", "click_timestamp"])
                  for f in files]
        return pd.concat(frames, ignore_index=True)

    sample = data_dir / "clicks_sample.csv"
    if sample.exists():
        return pd.read_csv(sample, usecols=["user_id", "click_article_id", "click_timestamp"])

    raise FileNotFoundError(
        f"Ni {clicks_dir} ni {sample} trouvés. Voir data/README.md pour l'arborescence."
    )


def build_embeddings_pca(data_dir: Path, out_dir: Path, n_components: int) -> np.ndarray:
    """Réduit la matrice d'embeddings par ACP et la sérialise."""
    from sklearn.decomposition import PCA

    with open(data_dir / "articles_embeddings.pickle", "rb") as f:
        emb = pickle.load(f)
    emb = np.asarray(emb, dtype=np.float32)

    n_components = min(n_components, emb.shape[1])
    reduced = PCA(n_components=n_components, random_state=42).fit_transform(emb)
    reduced = reduced.astype(np.float32)

    np.save(out_dir / "articles_embeddings_pca.npy", reduced)
    print(f"[embeddings] {emb.shape} -> ACP {reduced.shape} "
          f"(~{reduced.nbytes / 1e6:.1f} Mo)")
    return reduced


def build_user_artifacts(clicks: pd.DataFrame, out_dir: Path) -> None:
    """Construit l'historique par utilisateur et le classement de popularité."""
    # Historique de clics (ordre chronologique), dédupliqué par utilisateur.
    clicks = clicks.sort_values("click_timestamp")
    user_clicks: dict[int, np.ndarray] = {}
    for user_id, grp in clicks.groupby("user_id"):
        articles = pd.unique(grp["click_article_id"].to_numpy())
        user_clicks[int(user_id)] = articles.astype(np.int64)
    with open(out_dir / "user_clicks.pkl", "wb") as f:
        pickle.dump(user_clicks, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[user_clicks] {len(user_clicks)} utilisateurs")

    # Popularité globale (cold start).
    popular = (clicks["click_article_id"].value_counts().index.to_numpy().astype(np.int64))
    np.save(out_dir / "popular_articles.npy", popular)
    print(f"[popular_articles] {popular.size} articles classés")


def build_collaborative(clicks: pd.DataFrame, out_dir: Path, factors: int) -> None:
    """Entraîne un modèle ALS (feedback implicite) et sauvegarde les facteurs."""
    try:
        from implicit.als import AlternatingLeastSquares
    except ImportError:
        print("[collab] 'implicit' non installé -> filtrage collaboratif ignoré.")
        return

    from scipy.sparse import coo_matrix

    # Encodage dense des identifiants (les article_id/user_id sont creux).
    user_ids = clicks["user_id"].astype(np.int64)
    item_ids = clicks["click_article_id"].astype(np.int64)

    uniq_users, u_idx = np.unique(user_ids, return_inverse=True)
    uniq_items, i_idx = np.unique(item_ids, return_inverse=True)

    # Matrice user x item, valeur = nombre de clics (confiance implicite).
    data = np.ones(len(clicks), dtype=np.float32)
    ui = coo_matrix((data, (u_idx, i_idx)),
                    shape=(uniq_users.size, uniq_items.size)).tocsr()

    model = AlternatingLeastSquares(factors=factors, regularization=0.05,
                                    iterations=15, random_state=42)
    model.fit(ui)

    np.save(out_dir / "cf_user_factors.npy", model.user_factors.astype(np.float32))
    np.save(out_dir / "cf_item_factors.npy", model.item_factors.astype(np.float32))
    np.save(out_dir / "cf_item_ids.npy", uniq_items)  # colonne -> article_id
    user_index = {int(uid): int(row) for row, uid in enumerate(uniq_users)}
    with open(out_dir / "cf_user_index.pkl", "wb") as f:
        pickle.dump(user_index, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[collab] ALS entraîné : {uniq_users.size} users x {uniq_items.size} items, "
          f"{factors} facteurs")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/raw", type=Path)
    parser.add_argument("--out-dir", default="models", type=Path)
    parser.add_argument("--pca", default=50, type=int, help="dimensions après ACP")
    parser.add_argument("--factors", default=50, type=int, help="facteurs latents ALS")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    build_embeddings_pca(args.data_dir, args.out_dir, args.pca)
    clicks = load_clicks(args.data_dir)
    print(f"[clicks] {len(clicks):,} interactions chargées")
    build_user_artifacts(clicks, args.out_dir)
    build_collaborative(clicks, args.out_dir, args.factors)
    print("\nArtefacts prêts dans", args.out_dir.resolve())


if __name__ == "__main__":
    main()
