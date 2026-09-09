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

    python scripts/check_secrets.py                          # fichiers suivis
    python scripts/check_secrets.py --staged                 # contenu indexé
    python scripts/check_secrets.py --range origin/main..HEAD  # ce qui part au
                                                             # push (hook pre-push)
    python scripts/check_secrets.py --history                # tous les commits
                                                             # (avant publication)

Code de sortie : 0 = rien trouvé, 1 = secret probable.

Un constat examiné et jugé inoffensif s'inscrit dans `.secretsignore`, par son
**empreinte** (jamais sa valeur) et avec sa justification. Le nombre de constats
ainsi écartés est affiché à chaque exécution.

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
     # Les guillemets sont **optionnels** : dans un fichier `.env`, la valeur
     # n'en porte pas. Une première version les exigeait et aurait donc laissé
     # passer un `.env` indexé par erreur — le format le plus probable pour ce
     # genre de fuite.
     re.compile(r"(?:AZURE_STORAGE_CONNECTION_STRING|FUNCTION_KEY|HF_TOKEN|"
                r"RECO_API_KEY)\s*[:=]\s*[\"']?([^\"'\s#]{16,})[\"']?"),
     "affectation en dur d'un secret connu du projet"),
]

# Valeurs qui ne sont pas des secrets : gabarits de documentation, et
# **références** — un secret lu depuis une variable, un attribut de ressource ou
# un secret de CI est précisément la bonne pratique ; le signaler découragerait
# ce qu'on veut encourager.
GABARITS = re.compile(
    r"^(?:"
    r"<[^>]+>|\.{3}|x{3,}|hf_\.{3}|REDACTED|CHANGEME|placeholder|"
    r"votre[-_ ].*|your[-_ ].*|mauvaise|fake|dummy|test"
    # `azurerm_storage_account.x.primary_connection_string`, `os.environ.get`,
    # `var.cle`, `secrets.FUNCTION_KEY` : un identifiant pointé, pas une valeur.
    r"|[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+"
    # `$nouveau`, `${KEY}`, `%KEY%` : substitution par le shell.
    r"|[$%][A-Za-z0-9_{}().:]+"
    r")$", re.I)

# Fichiers dont le contenu n'est pas du texte utile à inspecter.
EXTENSIONS_IGNOREES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".npy", ".pkl",
                       ".db", ".woff", ".woff2", ".ttf", ".ico", ".zip"}


FICHIER_IGNORE = Path(".secretsignore")


def empreinte(valeur: str) -> str:
    """Empreinte courte d'une valeur trouvée, pour la lister sans l'écrire."""
    import hashlib

    return hashlib.sha256(valeur.strip().encode()).hexdigest()[:16]


def charger_acceptes() -> dict[str, str]:
    """Constats déjà examinés et acceptés (`.secretsignore`) : empreinte -> motif.

    Pourquoi une liste d'acceptation : l'historique contient des appâts factices
    (les anciennes données de `tests/test_check_secrets.py`, avant qu'elles ne
    soient assemblées à l'exécution). Sans cette liste, `--history` signalerait
    éternellement les mêmes quatre constats, et une vraie fuite se perdrait dans
    le bruit — une alarme permanente est une alarme ignorée.

    Le fichier ne contient que des **empreintes**, jamais les valeurs : il peut
    donc être versionné sans rien publier. Et comme l'empreinte porte sur la
    valeur exacte, accepter un appât n'accepte pas un secret voisin.
    """
    if not FICHIER_IGNORE.exists():
        return {}
    acceptes = {}
    for ligne in FICHIER_IGNORE.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        empreinte_lue, _, motif = ligne.partition("#")
        acceptes[empreinte_lue.strip()] = motif.strip() or "sans justification"
    return acceptes


def fichiers_suivis() -> list[str]:
    sortie = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                            check=True).stdout
    return [f for f in sortie.splitlines()
            if Path(f).suffix.lower() not in EXTENSIONS_IGNOREES]


def _masquer(valeur: str) -> str:
    """N'affiche jamais le secret en entier : la sortie de CI est publique."""
    return valeur[:6] + "…" + valeur[-4:] if len(valeur) > 14 else "…"


def examiner(texte: str, origine: str,
             acceptes: dict[str, str] | None = None) -> list[str]:
    """Constats trouvés dans `texte`, hors gabarits et hors liste d'acceptation.

    `acceptes` est incrémenté d'un compteur : les constats écartés sont comptés
    et annoncés, jamais tus. Une suppression invisible est précisément le défaut
    que ce dépôt a rencontré plusieurs fois.
    """
    acceptes = acceptes if acceptes is not None else {}
    trouves = []
    for numero, ligne in enumerate(texte.splitlines(), start=1):
        for nom, motif, consequence in MOTIFS:
            m = motif.search(ligne)
            if not m:
                continue
            valeur = m.group(1) if m.groups() else m.group(0)
            if GABARITS.match(valeur.strip()):
                continue
            if empreinte(valeur) in acceptes:
                examiner.ignores += 1
                continue
            trouves.append(f"{origine}:{numero}  {nom} — {consequence}\n"
                           f"    {_masquer(valeur)}   empreinte {empreinte(valeur)}")
    return trouves


examiner.ignores = 0


def examiner_arbre() -> list[str]:
    acceptes = charger_acceptes()
    trouves = []
    for chemin in fichiers_suivis():
        try:
            texte = Path(chemin).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        trouves += examiner(texte, chemin, acceptes)
    return trouves


def examiner_index() -> list[str]:
    """Examine le contenu **indexé**, c'est-à-dire ce qui part au commit.

    Ni l'arbre de travail ni HEAD : un secret peut être indexé puis retiré du
    fichier avant le commit — il partirait quand même. On lit donc les blobs de
    l'index (`git show :fichier`), et seulement les fichiers ajoutés ou modifiés.
    """
    sortie = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True, text=True, check=True).stdout
    acceptes = charger_acceptes()
    trouves = []
    for chemin in sortie.splitlines():
        if not chemin or Path(chemin).suffix.lower() in EXTENSIONS_IGNOREES:
            continue
        blob = subprocess.run(["git", "show", f":{chemin}"], capture_output=True)
        if blob.returncode != 0:
            continue
        texte = blob.stdout.decode("utf-8", errors="ignore")
        trouves += examiner(texte, chemin, acceptes)
    return trouves


def examiner_objets(*revisions: str, etiquette: str = "historique") -> list[str]:
    """Balaie chaque version de chaque fichier des révisions données.

    `revisions` est passé tel quel à `git rev-list --objects` : `--all` pour tout
    l'historique, ou `origin/main..HEAD` pour les seuls commits sur le départ.

    Un secret retiré dans un commit ultérieur reste lisible dans l'historique :
    rendre le dépôt public le publierait.
    """
    # `rev-list --objects` liste les objets sous la forme « oid chemin ». On
    # récupère ensuite les contenus en **un seul** `cat-file --batch` : une
    # première version lançait trois processus git par version de fichier et
    # prenait plusieurs minutes, ce qui décourage d'exécuter la vérification au
    # moment où elle compte.
    lancement = subprocess.run(["git", "rev-list", "--objects", *revisions],
                               capture_output=True, text=True)
    if lancement.returncode != 0:
        print(f"[{etiquette}] plage illisible ({' '.join(revisions)}) — "
              f"{lancement.stderr.strip().splitlines()[:1]}")
        return []
    objets = lancement.stdout

    a_lire: dict[str, str] = {}          # oid -> chemin (le premier rencontré)
    for ligne in objets.splitlines():
        oid, _, chemin = ligne.partition(" ")
        if not chemin or Path(chemin).suffix.lower() in EXTENSIONS_IGNOREES:
            continue
        a_lire.setdefault(oid, chemin)

    if not a_lire:
        print(f"[{etiquette}] aucun fichier texte à examiner")
        return []

    lot = subprocess.run(["git", "cat-file", "--batch"],
                         input="\n".join(a_lire).encode(),
                         capture_output=True)
    acceptes = charger_acceptes()
    flux, trouves = lot.stdout, []
    position = 0
    while position < len(flux):
        fin_entete = flux.find(b"\n", position)
        if fin_entete == -1:
            break
        entete = flux[position:fin_entete].decode("utf-8", errors="ignore").split()
        position = fin_entete + 1
        if len(entete) < 3 or entete[1] != "blob":
            continue                     # objet manquant, ou arbre/commit
        oid, taille = entete[0], int(entete[2])
        contenu = flux[position:position + taille]
        position += taille + 1           # + le saut de ligne final
        texte = contenu.decode("utf-8", errors="ignore")
        trouves += examiner(texte, f"{etiquette}:{a_lire.get(oid, oid[:8])}",
                            acceptes)

    print(f"[{etiquette}] {len(a_lire)} versions de fichiers examinées")
    return trouves


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    groupe = parser.add_mutually_exclusive_group()
    groupe.add_argument("--history", action="store_true",
                        help="examiner tous les commits, et pas seulement "
                             "l'état courant (à faire avant de rendre le dépôt "
                             "public : l'historique reste lisible)")
    groupe.add_argument("--staged", action="store_true",
                        help="examiner le contenu indexé (avant un commit)")
    groupe.add_argument("--range", metavar="PLAGE",
                        help="examiner les objets d'une plage de révisions, "
                             "p. ex. « origin/main..HEAD » — utilisé par le hook "
                             "pre-push pour ne contrôler que ce qui part")
    args = parser.parse_args()

    if args.history:
        trouves = examiner_objets("--all")
    elif args.range:
        trouves = examiner_objets(*args.range.split(), etiquette="plage")
    elif args.staged:
        trouves = examiner_index()
    else:
        trouves = examiner_arbre()

    if trouves:
        print(f"\n{len(trouves)} secret(s) probable(s) :\n")
        for t in trouves:
            print(f"  {t}")
        print("\nSi la valeur est réelle : la **révoquer** d'abord (une valeur "
              "retirée d'un fichier reste dans l'historique git), puis "
              "remplacer par une variable d'environnement.")
        if args.staged:
            print("Si c'est un faux positif : `git commit --no-verify`.")
        return 1

    perimetre = ("tout l'historique" if args.history else
                 f"la plage {args.range}" if args.range else
                 "le contenu indexé" if args.staged else
                 "les fichiers suivis")
    print(f"aucun secret détecté dans {perimetre}")
    if examiner.ignores:
        # Annoncé, jamais tu : une suppression silencieuse ferait de cette
        # vérification une vérification qu'on croit avoir.
        print(f"({examiner.ignores} constat(s) écarté(s) par {FICHIER_IGNORE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
