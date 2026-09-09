"""Refuse un dépôt qui contient un secret en clair.

Pourquoi ce script existe, alors que la CI vérifiait déjà « les notebooks ne
contiennent pas de secret » : cette vérification ne cherchait que des
affectations `AZURE_STORAGE_CONNECTION_STRING=…` ou `HF_TOKEN=…` dans les `.py`
et les `.ipynb`. Elle laissait donc passer :

  - une chaîne de connexion collée telle quelle (`DefaultEndpointsProtocol=…`) ;
  - une **clé de fonction dans une URL** (`?code=…`), qui est précisément la
    forme sous laquelle cette clé circule dans les commandes de déploiement ;
  - un jeton Hugging Face (`hf_…`) ;
  - n'importe lequel des trois dans un fichier `.md` — or les commandes de
    déploiement vivent dans la documentation.

Utilisation :

    python scripts/check_secrets.py              # fichiers suivis par git
    python scripts/check_secrets.py --history    # tous les commits (avant de
                                                 # rendre le dépôt public)

Code de sortie : 0 = rien trouvé, 1 = secret probable.

**Parti pris : pas de détection par entropie.** Un seuil d'entropie signalerait
les sorties d'images des notebooks (base64) à chaque exécution, et une
vérification qui crie tout le temps finit par être ignorée. On ne cherche donc
que des formes reconnaissables, quitte à en manquer. Pour un balayage exhaustif
avant publication, `gitleaks` reste plus complet — ce script vise la CI, où il
doit être rapide et silencieux.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# (nom, expression, ce que ça signifie). Chaque motif est ancré sur une forme
# propre au fournisseur : c'est ce qui évite les faux positifs.
MOTIFS: list[tuple[str, re.Pattern, str]] = [
    ("chaîne de connexion Azure Storage",
     re.compile(r"DefaultEndpointsProtocol=.{0,200}?AccountKey=[A-Za-z0-9+/=]{20,}"),
     "donne un accès complet au compte de stockage"),
    ("clé de compte Azure Storage",
     re.compile(r"AccountKey=[A-Za-z0-9+/]{60,}={0,2}"),
     "idem, sans le reste de la chaîne"),
    ("signature d'accès partagé (SAS)",
     re.compile(r"[?&]s(?:i)?g=[A-Za-z0-9%+/=]{30,}"),
     "accès délégué à un conteneur ou un blob"),
    ("clé de fonction Azure dans une URL",
     # Une vraie clé fait ~54 caractères et finit par `==`. On exclut les
     # variables (`$key`, `${KEY}`) et les gabarits (`<CLE>`).
     re.compile(r"[?&]code=(?!\$|%24|\{|<)[A-Za-z0-9_\-]{30,}(?:==|%3D%3D)"),
     "appel de l'endpoint sans authentification supplémentaire"),
    ("jeton Hugging Face",
     re.compile(r"\bhf_[A-Za-z0-9]{30,}"),
     "écriture sur vos dépôts de modèles et Spaces"),
    ("jeton GitHub",
     re.compile(r"\b(?:ghp_|gho_|ghs_|github_pat_)[A-Za-z0-9_]{20,}"),
     "accès à vos dépôts"),
    ("identifiant AWS",
     re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
     "accès à un compte AWS"),
    ("clé privée",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
     "clé privée en clair"),
    ("secret nommé, avec valeur",
     re.compile(r"(?:AZURE_STORAGE_CONNECTION_STRING|FUNCTION_KEY|HF_TOKEN|"
                r"RECO_API_KEY)\s*[:=]\s*[\"']([^\"'\s]{16,})[\"']"),
     "affectation en dur d'un secret connu du projet"),
]

# Valeurs manifestement factices : gabarits de documentation, exemples, tests.
GABARITS = re.compile(
    r"^(?:<[^>]+>|\.{3}|x{3,}|hf_\.{3}|REDACTED|CHANGEME|placeholder|"
    r"votre[-_ ].*|your[-_ ].*|mauvaise|fake|dummy|test)$", re.I)

# Fichiers dont le contenu n'est pas du texte utile à inspecter.
EXTENSIONS_IGNOREES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".npy", ".pkl",
                       ".db", ".woff", ".woff2", ".ttf", ".ico", ".zip"}


def fichiers_suivis() -> list[str]:
    sortie = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                            check=True).stdout
    return [f for f in sortie.splitlines()
            if Path(f).suffix.lower() not in EXTENSIONS_IGNOREES]


def _masquer(valeur: str) -> str:
    """N'affiche jamais le secret en entier : la sortie de CI est publique."""
    return valeur[:6] + "…" + valeur[-4:] if len(valeur) > 14 else "…"


def examiner(texte: str, origine: str) -> list[str]:
    trouves = []
    for numero, ligne in enumerate(texte.splitlines(), start=1):
        for nom, motif, consequence in MOTIFS:
            m = motif.search(ligne)
            if not m:
                continue
            valeur = m.group(1) if m.groups() else m.group(0)
            if GABARITS.match(valeur.strip()):
                continue
            trouves.append(f"{origine}:{numero}  {nom} — {consequence}\n"
                           f"    {_masquer(valeur)}")
    return trouves


def examiner_arbre() -> list[str]:
    trouves = []
    for chemin in fichiers_suivis():
        try:
            texte = Path(chemin).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        trouves += examiner(texte, chemin)
    return trouves


def examiner_historique() -> list[str]:
    """Balaie chaque version de chaque fichier de tous les commits.

    Un secret retiré dans un commit ultérieur reste lisible dans l'historique :
    rendre le dépôt public le publierait.
    """
    commits = subprocess.run(["git", "rev-list", "--all"], capture_output=True,
                             text=True, check=True).stdout.split()
    trouves, vus = [], set()
    for commit in commits:
        liste = subprocess.run(["git", "ls-tree", "-r", "--name-only", commit],
                               capture_output=True, text=True).stdout.splitlines()
        for chemin in liste:
            if Path(chemin).suffix.lower() in EXTENSIONS_IGNOREES:
                continue
            blob = subprocess.run(["git", "rev-parse", f"{commit}:{chemin}"],
                                  capture_output=True, text=True)
            if blob.returncode != 0:
                continue
            oid = blob.stdout.strip()
            if oid in vus:          # même contenu déjà examiné
                continue
            vus.add(oid)
            contenu = subprocess.run(["git", "cat-file", "-p", oid],
                                     capture_output=True)
            texte = contenu.stdout.decode("utf-8", errors="ignore")
            trouves += examiner(texte, f"{commit[:8]}:{chemin}")
    print(f"[historique] {len(commits)} commits, {len(vus)} versions de fichiers")
    return trouves


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--history", action="store_true",
                        help="examiner tous les commits, et pas seulement "
                             "l'état courant (à faire avant de rendre le dépôt "
                             "public : l'historique reste lisible)")
    args = parser.parse_args()

    trouves = examiner_historique() if args.history else examiner_arbre()

    if trouves:
        print(f"\n{len(trouves)} secret(s) probable(s) :\n")
        for t in trouves:
            print(f"  {t}")
        print("\nSi la valeur est réelle : la **révoquer** d'abord (une valeur "
              "retirée d'un fichier reste dans l'historique git), puis "
              "remplacer par une variable d'environnement.")
        return 1

    perimetre = "tout l'historique" if args.history else "les fichiers suivis"
    print(f"aucun secret détecté dans {perimetre}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
