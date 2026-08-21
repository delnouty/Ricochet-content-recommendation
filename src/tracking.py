"""Traçabilité des expériences : paramètres, métriques et versions de modèle (MLflow).

Sans traçage, une campagne d'expériences n'est pas reproductible : on retient la
meilleure valeur et on perd la configuration qui l'a produite. Ce module enregistre
chaque essai — réglages, métriques, artefacts — pour que le tableau final soit
reconstituable.

**MLflow est une dépendance optionnelle.** S'il est absent, les fonctions n'échouent
pas : elles préviennent et rendent la main, afin que les notebooks et la CI
fonctionnent sans lui.

Stockage par défaut : base **SQLite** `mlflow.db` à la racine du dépôt. Ce choix
n'est pas cosmétique — MLflow 3 refuse désormais le backend « dossier de fichiers »,
et le **registre de modèles** (versions, étapes staging / production) exige de toute
façon une base de données.

Consulter les résultats :

    mlflow ui --backend-store-uri sqlite:///mlflow.db

Surcharge possible par `MLFLOW_TRACKING_URI` (serveur distant partagé, par exemple).

Chaque essai porte le commit git, ce qui rattache un chiffre à un état exact du
code : sans cela, un résultat n'est pas reproductible.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Backend SQLite et non dossier de fichiers : MLflow 3 refuse le file store, et
# surtout le **registre de modèles** (versions, étapes) exige une base de données.
DEFAULT_URI = "sqlite:///" + (ROOT / "mlflow.db").as_posix()
DEFAULT_ARTIFACTS = (ROOT / "mlruns").as_uri()


def _mlflow():
    """Importe MLflow si disponible, sinon None (avec un avertissement unique)."""
    try:
        import mlflow
    except ImportError:
        if not getattr(_mlflow, "_averti", False):
            print("[tracking] mlflow absent : aucun enregistrement. "
                  "Installer avec : pip install mlflow")
            _mlflow._averti = True
        return None
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", DEFAULT_URI))
    return mlflow


def git_commit() -> str:
    """Commit courant, pour rattacher un résultat à un état du code."""
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "inconnu"
    except (OSError, subprocess.SubprocessError):
        return "inconnu"


def log_run(experiment: str, run_name: str, params: dict, metrics: dict,
            artifacts: list[Path] | tuple = (), tags: dict | None = None) -> str | None:
    """Enregistre un essai. Renvoie le `run_id`, ou None si MLflow est absent.

    `params` : réglages (fenêtre, facteurs, négatifs, type de note…).
    `metrics` : mesures numériques (HitRate, Recall, couverture…).
    `artifacts` : fichiers à conserver avec l'essai (facteurs `.npy`, etc.).
    `tags` : métadonnées libres ; le commit git est ajouté automatiquement.
    """
    mlflow = _mlflow()
    if mlflow is None:
        return None

    # Une panne de traçage ne doit jamais faire échouer une évaluation : les
    # métriques restent affichées et écrites en JSON.
    try:
        mlflow.set_experiment(experiment)
        with mlflow.start_run(run_name=run_name) as run:
            mlflow.set_tags({"git_commit": git_commit(), **(tags or {})})
            mlflow.log_params({k: v for k, v in params.items() if v is not None})
            mlflow.log_metrics({_clean(k): float(v) for k, v in metrics.items()})
            for chemin in artifacts:
                chemin = Path(chemin)
                if chemin.is_dir():
                    mlflow.log_artifacts(str(chemin), artifact_path=chemin.name)
                elif chemin.exists():
                    mlflow.log_artifact(str(chemin))
            return run.info.run_id
    except Exception as exc:  # noqa: BLE001
        print(f"[tracking] enregistrement impossible : {type(exc).__name__} : {exc}")
        return None


def _classe_modele():
    """Emballage `pyfunc` du recommandeur, requis par le registre MLflow.

    MLflow 3 ne versionne que des *modèles enregistrés*, pas un simple dossier de
    fichiers : un jeu d'artefacts `.npy` doit donc être présenté comme un modèle.
    Cet emballage n'existe que pour la traçabilité — le service de production
    continue de lire les artefacts directement, en numpy seul.
    """
    import mlflow

    class RecommandeurMLflow(mlflow.pyfunc.PythonModel):
        def load_context(self, context):
            import sys as _sys
            _sys.path.insert(0, str(Path(context.artifacts["code"]).parent))
            from src.recommender import Recommender
            self._reco = Recommender(Path(context.artifacts["artefacts"]))

        def predict(self, context, model_input, params=None):
            n = int((params or {}).get("n", 5))
            methode = (params or {}).get("method", "hybrid")
            colonne = model_input["user_id"] if hasattr(model_input, "columns") else model_input
            return [self._reco.recommend(int(u), n=n, method=methode) for u in colonne]

    return RecommandeurMLflow


def register_artifacts(nom_modele: str, dossier: Path, metrics: dict,
                       params: dict | None = None, tags: dict | None = None) -> str | None:
    """Versionne un jeu d'artefacts dans le registre de modèles MLflow.

    Le « modèle » de ce projet est un **dossier d'artefacts numpy** (facteurs,
    projection ACP, popularité, étoiles). Il est enregistré via un emballage
    `pyfunc`, ce qui donne accès au registre : chaque version conserve ses
    métriques, ses paramètres et le commit git qui l'a produite — donc la
    possibilité de revenir à une version antérieure.

    Renvoie le numéro de version, ou None si indisponible.
    """
    mlflow = _mlflow()
    if mlflow is None:
        return None
    try:
        mlflow.set_experiment(f"{nom_modele}-registry")
        with mlflow.start_run(run_name=f"{nom_modele}-{git_commit()}"):
            mlflow.set_tags({"git_commit": git_commit(), "type": "artefacts",
                             **(tags or {})})
            mlflow.log_params(params or {})
            mlflow.log_metrics({_clean(k): float(v) for k, v in metrics.items()})

            info = mlflow.pyfunc.log_model(
                name=nom_modele,
                python_model=_classe_modele()(),
                artifacts={"artefacts": str(dossier),
                           "code": str(ROOT / "src" / "recommender.py")},
                code_paths=[str(ROOT / "src")],
                registered_model_name=nom_modele,
            )
            client = mlflow.MlflowClient()
            versions = client.search_model_versions(f"name='{nom_modele}'")
            derniere = max((int(v.version) for v in versions), default=1)
            print(f"[registry] {nom_modele} version {derniere} enregistrée "
                  f"({info.model_uri})")
            return str(derniere)
    except Exception as exc:  # noqa: BLE001
        print(f"[registry] enregistrement impossible : {type(exc).__name__} : {exc}")
        return None


def log_comparison(experiment: str, tableau, params_communs: dict | None = None,
                   tags: dict | None = None) -> list[str]:
    """Enregistre un essai par ligne d'un tableau de comparaison.

    `tableau` est le DataFrame renvoyé par `experiments.compare()` : son index donne
    le nom de la configuration, ses colonnes les métriques. Chaque ligne devient un
    run distinct, ce qui permet de trier et comparer dans l'interface MLflow.
    """
    ids = []
    for configuration, ligne in tableau.iterrows():
        metriques = {k: v for k, v in ligne.items()
                     if isinstance(v, (int, float)) and not isinstance(v, bool)}
        ids.append(log_run(experiment, str(configuration),
                           {"configuration": configuration, **(params_communs or {})},
                           metriques, tags=tags))
    return [i for i in ids if i]


def _clean(nom: str) -> str:
    """MLflow n'accepte pas tous les caractères dans un nom de métrique."""
    return (nom.replace("@", "_at_").replace("%", "pct").replace(" ", "_")
            .replace("é", "e").replace("è", "e"))
