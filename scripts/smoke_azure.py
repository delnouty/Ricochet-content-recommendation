"""Vérifie que le service déployé sert bien le modèle attendu.

Pourquoi cette vérification existe, alors que la CI passe déjà et que le service
répond : parce que **répondre ne prouve rien**. Deux incidents l'ont montré sur
ce projet, et aucun des deux ne levait d'erreur :

  - un chargeur d'artefacts suivant une liste figée servait la popularité de
    tout l'historique au lieu de celle de la dernière heure — HitRate@5 de
    0,0010 au lieu de 0,2525 ;
  - un cache local jugé sur la seule taille des fichiers gardait un modèle
    périmé : le service répondait avec **deux modèles différents** selon
    l'instance touchée, six réponses sur dix avec le nouveau.

Les deux ont été trouvés à la main, en comparant la réponse distante à la
réponse locale. Ce script fait cette comparaison automatiquement.

Il ne recalcule rien : les artefacts pèsent 253 Mo et ne sont pas versionnés.
Il compare donc à un **relevé de référence** (`scripts/smoke_expected.json`),
mis à jour délibérément quand les artefacts changent — la même discipline que
`models/baseline_metrics.json`.

Utilisation :

    $env:FUNCTION_URL = "https://<app>.azurewebsites.net/api/recommend"
    $env:FUNCTION_KEY = "<clé>"

    python scripts/smoke_azure.py            # vérifier
    python scripts/smoke_azure.py --record   # figer l'état actuel comme référence

Aucun accès Azure n'est requis : seul le ticket HTTP (la clé de fonction). Le
script n'utilise que la bibliothèque standard, pour que la CI n'ait rien à
installer.

Codes de sortie : 0 = conforme, 1 = écart, 2 = service injoignable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REFERENCE = Path(__file__).resolve().parent / "smoke_expected.json"

# Trois appels, choisis pour emprunter trois chemins de code différents. Un seul
# appel « qui marche » ne dirait rien des deux autres.
CAS = [
    {
        "nom": "lecteur connu, stratégie de production",
        "params": {"user_id": 0, "n": 5, "method": "mix"},
        "verifie": "le classement issu des artefacts publiés",
    },
    {
        "nom": "lecteur inconnu — cascade de repli",
        "params": {"user_id": 999999999, "n": 5, "method": "mix"},
        "verifie": "le cold start : aucune requête ne renvoie de liste vide",
    },
    {
        "nom": "lecteur inconnu avec historique transmis",
        "params": {"user_id": 999999999, "n": 5, "method": "mix",
                   "history": "157541,96210,160974"},
        "verifie": "le service sans état : le profil vient de la requête",
    },
]

# Nombre d'appels identiques pour détecter des instances désaccordées. Dix
# appels avaient révélé six réponses neuves et quatre périmées : c'est ce
# déséquilibre-là qu'on cherche, et il ne se voit pas sur un appel unique.
APPELS_COHERENCE = 15


def appeler(url: str, cle: str, params: dict, timeout: int = 120) -> list[int]:
    requete = dict(params)
    if cle:
        requete["code"] = cle
    adresse = f"{url}?{urllib.parse.urlencode(requete)}"
    with urllib.request.urlopen(adresse, timeout=timeout) as reponse:
        charge = json.load(reponse)
    return [int(a) for a in charge["recommendations"]]


def rechauffer(url: str, cle: str) -> float:
    """Premier appel, pour absorber le démarrage à froid (~8 s, 253 Mo à lire).

    Sans cela, le premier cas mesuré porterait la latence du démarrage et non
    celle du service.
    """
    debut = time.time()
    appeler(url, cle, {"user_id": 0, "n": 1})
    return time.time() - debut


def verifier(url: str, cle: str, attendu: dict) -> tuple[list[str], list[str]]:
    """Renvoie (écarts, lignes de rapport)."""
    ecarts, rapport = [], []

    for cas in CAS:
        obtenu = appeler(url, cle, cas["params"])
        reference = attendu["cas"].get(cas["nom"])

        if reference is None:
            ecarts.append(f"{cas['nom']} : absent du relevé de référence "
                          f"(lancer --record)")
            continue
        if obtenu != reference:
            ecarts.append(f"{cas['nom']}\n"
                          f"      attendu : {reference}\n"
                          f"      obtenu  : {obtenu}")
        else:
            rapport.append(f"  ok   {cas['nom']} — {obtenu}")

    # Cohérence entre instances : le même appel, répété.
    distinctes = {tuple(appeler(url, cle, CAS[0]["params"]))
                  for _ in range(APPELS_COHERENCE)}
    if len(distinctes) > 1:
        ecarts.append(
            f"{APPELS_COHERENCE} appels identiques ont donné "
            f"{len(distinctes)} réponses différentes : des instances servent "
            f"des artefacts différents.\n"
            + "".join(f"      {list(d)}\n" for d in distinctes))
    else:
        rapport.append(f"  ok   {APPELS_COHERENCE} appels identiques, "
                       f"une seule réponse — instances accordées")

    return ecarts, rapport


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--record", action="store_true",
                        help="écrire l'état actuel du service comme référence. "
                             "Acte délibéré, à faire après un ré-entraînement — "
                             "sinon la vérification ne protège plus de rien")
    parser.add_argument("--url", default=os.environ.get("FUNCTION_URL", ""))
    parser.add_argument("--key", default=os.environ.get("FUNCTION_KEY", ""))
    args = parser.parse_args()

    if not args.url:
        print("FUNCTION_URL absent (variable d'environnement ou --url).",
              file=sys.stderr)
        return 2

    try:
        latence = rechauffer(args.url, args.key)
    except urllib.error.HTTPError as exc:
        detail = {401: " — clé de fonction absente ou incorrecte"}.get(exc.code, "")
        print(f"service injoignable : HTTP {exc.code}{detail}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"service injoignable : {type(exc).__name__} {exc}", file=sys.stderr)
        return 2

    print(f"[smoke] premier appel : {latence:.1f} s "
          f"({'démarrage à froid' if latence > 2 else 'instance chaude'})")

    if args.record:
        releve = {
            "url": args.url.split("/api/")[0],
            "releve_le": time.strftime("%Y-%m-%d %H:%M:%S"),
            "cas": {cas["nom"]: appeler(args.url, args.key, cas["params"])
                    for cas in CAS},
        }
        REFERENCE.write_text(json.dumps(releve, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        print(f"[smoke] référence écrite dans {REFERENCE.name} :")
        for nom, ids in releve["cas"].items():
            print(f"  {nom} — {ids}")
        return 0

    if not REFERENCE.exists():
        print(f"{REFERENCE} absent : lancer d'abord --record.", file=sys.stderr)
        return 2

    attendu = json.loads(REFERENCE.read_text(encoding="utf-8"))
    ecarts, rapport = verifier(args.url, args.key, attendu)

    print(f"[smoke] référence relevée le {attendu.get('releve_le', '?')}")
    for ligne in rapport:
        print(ligne)

    if ecarts:
        print(f"\n{len(ecarts)} écart(s) — le service ne sert pas le modèle "
              f"attendu :\n", file=sys.stderr)
        for e in ecarts:
            print(f"  !! {e}", file=sys.stderr)
        print("\nSi les artefacts ont été ré-entraînés délibérément, mettre la "
              "référence à jour : `python scripts/smoke_azure.py --record`.\n"
              "Sinon, c'est un déploiement qui sert autre chose que ce qui est "
              "publié — voir docs/azure_deployment.md, étape 11.", file=sys.stderr)
        return 1

    print("\nle service déployé sert bien le modèle de référence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
