# MLOps — traçabilité, versionnage, intégration continue

Ce document décrit comment un résultat de ce dépôt devient reproductible, et comment
un modèle ré-entraîné est empêché de partir en production s'il dégrade le service.

## 1. Pourquoi c'était nécessaire

Les premières mesures du projet étaient fausses : les modèles étaient entraînés sur
100 % des données puis évalués sur ces mêmes données. L'ALS affichait un HitRate@5 de
**0,2415** ; avec un découpage temporel correct, il tombe à **0,0415** — un facteur
**5,8** de précision imaginaire, qui n'était visible nulle part parce que rien
n'était tracé. Le chiffre est reproductible : `python scripts/mesure_fuite.py`.

Trois manques distincts :

| Manque | Conséquence |
|---|---|
| pas de découpage train / validation / test | métriques gonflées par une fuite |
| pas d'enregistrement des essais | on retient un chiffre, on perd la configuration |
| pas de porte de qualité | un ré-entraînement dégradé se publie sans alerte |

## 2. Découpage et protocole

Découpage **temporel** 60 / 20 / 20 sur `click_timestamp` (`src/evaluate.py`) — et non
aléatoire : sur un flux d'actualité, un découpage aléatoire laisse le modèle apprendre
des clics postérieurs à ceux qu'il doit prédire.

```
| 60 % entraînement | 20 % validation | 20 % test |
t0 -------------- t60 ------------ t80 --------- tfin
```

Trois règles, établies par les notebooks 03 à 07 :

1. **le vivier de candidats est recalculé à l'instant de la requête** — pour évaluer
   sur le test, l'historique est `entraînement + validation`. Ce n'est pas une fuite :
   un service en production connaît le passé jusqu'à la minute présente. Un vivier
   gelé à la fin de l'entraînement donne **0,0000** pour toutes les méthodes ;
2. **chaque méthode est réglée sur la validation**, et ses réglages sont balayés
   **ensemble**. Comparer une méthode réglée à des méthodes par défaut fausse la
   conclusion ; juxtaposer des optima partiels la fausse aussi — l'ALS varie de
   0,0110 à 0,0345 selon la combinaison fenêtre × facteurs, et la combinaison
   obtenue en prenant les deux gagnants de balayages séparés est la pire des
   quatre (notebook 05, section 3) ;
3. **les deux modèles collaboratifs sont ré-entraînés sur l'historique de la
   mesure.** L'ALS l'était, le SVD non : il tombait à 0,0005 au lieu de 0,0220,
   par manque de données et non par faiblesse du modèle.

Le réglage se fait sur la validation ; le test ne sert qu'à la mesure finale.

## 3. Traçabilité (MLflow)

`src/tracking.py`. Backend **SQLite** (`mlflow.db`) et non dossier de fichiers :
MLflow 3 refuse le file store, et le registre de modèles exige une base.

```powershell
python -m src.evaluate --out-dir models_split --split val --skip-build --track
mlflow ui --backend-store-uri sqlite:///mlflow.db      # http://127.0.0.1:5000
```

Chaque essai enregistre :

- **paramètres** : fenêtres, facteurs, négatifs, type de note, taille des périodes ;
- **métriques** : HitRate@5, Recall@5, couverture, personnalisation ;
- **tags** : `git_commit` — un chiffre est ainsi rattaché à un état exact du code.

MLflow est une dépendance **optionnelle** : absent, le traçage est ignoré avec un
avertissement, et une panne de traçage n'interrompt jamais une évaluation.

## 4. Versionnage des modèles

Le « modèle » de ce projet est un dossier d'artefacts `.npy` / `.pkl`, pas un objet
sérialisé. Il est présenté au registre via un emballage `pyfunc` :

```powershell
python -m src.evaluate --out-dir models_split --split test --skip-build `
    --register ricochet-artefacts
```

Chaque version conserve ses métriques, ses paramètres et son commit, ce qui rend
possible un retour arrière. L'emballage n'existe que pour la traçabilité : le service
de production lit les artefacts directement, en numpy seul, et n'importe ni MLflow ni
scikit-learn ni Surprise.

## 5. Porte de qualité

`scripts/check_metrics.py` — c'est la pièce qui distingue un pipeline MLOps d'un
entraînement automatisé.

```powershell
python -m src.evaluate --out-dir models_split --split test --skip-build --json metrics.json
python scripts/check_metrics.py --candidate metrics.json --tolerance 0.10
```

- compare `HitRate@5` et `Recall@5` à `models/baseline_metrics.json` ;
- **code de sortie 1** si la baisse dépasse la tolérance → la CI bloque la publication ;
- les autres métriques sont affichées à titre informatif ;
- la référence n'est mise à jour que délibérément (`--promote`) et elle est
  **versionnée dans git** : sans cela, elle suivrait la dérive du modèle et ne
  protégerait plus rien.

Référence actuelle : `popularité 1 h`, HitRate@5 = **0,2525**, Recall@5 = 0,0555
(période de test, 2 000 lecteurs). Régénérer avec :

```bash
python -m src.evaluate --split test --skip-build --json models/baseline_metrics.json
```

Ne pas la mettre à jour pour faire passer la porte : c'est le geste qui la vide de
son sens. On la met à jour quand la configuration de référence change, et on dit
laquelle.

## 6. Intégration continue

Deux workflows, séparés parce qu'ils n'ont pas les mêmes besoins.

### `.github/workflows/ci.yml` — à chaque push

Ne demande **aucune donnée** (le jeu Globo pèse 221 Mo et n'est pas versionné) :

| Étape | Vérifie |
|---|---|
| `pytest tests/` | le cœur de reco, sur artefacts synthétiques — 78 tests |
| `sync_recommender.py --check` | les trois copies déployées du cœur sont à jour |
| taille des fichiers | aucun fichier > 5 Mo versionné |
| artefacts | aucun `.npy` / `.pkl` / `.db` dans git |
| `check_secrets.py` | aucun secret en clair, **dans aucun fichier suivi** |

#### La vérification des secrets, et pourquoi elle a été refaite

La version précédente ne cherchait que des affectations
`AZURE_STORAGE_CONNECTION_STRING=` ou `HF_TOKEN=` dans les `.py` et `.ipynb`.
Elle laissait donc passer trois formes que ce projet manipule réellement :

- une chaîne de connexion collée telle quelle (`DefaultEndpointsProtocol=…`) ;
- une **clé de fonction dans une URL** (`?code=…`) — la forme sous laquelle
  cette clé circule dans toutes les commandes de déploiement ;
- n'importe laquelle des deux dans un fichier `.md`, alors que les commandes de
  déploiement vivent dans la documentation.

`scripts/check_secrets.py` couvre les chaînes de connexion et clés Azure, les
signatures SAS, les clés de fonction en URL, les jetons Hugging Face et GitHub,
les identifiants AWS et les clés privées. Il **masque** ce qu'il trouve : un
journal de build est public, et recopier une fuite en entier pour la signaler la
rendrait pire.

Deux partis pris assumés : pas de détection par entropie (les sorties d'images
des notebooks sont du base64 et déclencheraient à chaque exécution ; une alarme
permanente est une alarme ignorée), et des gabarits explicitement tolérés
(`$key`, `<CLE>`, `hf_...`) pour que la documentation reste écrivable.
`tests/test_check_secrets.py` fixe les deux côtés — 19 cas, dont un qui vérifie
que le dépôt réel est propre.

**Avant de rendre le dépôt public**, l'état courant ne suffit pas : un secret
retiré reste lisible dans l'historique. Balayer tous les commits :

```bash
python scripts/check_secrets.py --history
```

#### Le hook `pre-push` — le dernier moment où c'est encore réversible

La CI s'exécute **après** le push : à ce moment le secret est déjà chez
l'hébergeur, et l'effacer demande de réécrire un historique publié. Le hook,
lui, refuse le push.

Le choix du `pre-push` plutôt que du `pre-commit` est délibéré : un commit local
se corrige sans conséquence (`amend`, `rebase`, `reset`), et bloquer chaque
commit de travail intermédiaire coûte plus qu'il ne protège. Le push est le
moment où le contenu devient public et où l'historique cesse d'être à soi.

Une commande, une fois par clone :

```bash
git config core.hooksPath scripts/hooks
```

`scripts/hooks/pre-push` est **versionné** — contrairement à `.git/hooks/`, qui
ne suit pas le dépôt. Pointer `core.hooksPath` dessus le garde à jour sans
recopie.

Il fait deux choses, dans cet ordre :

| Contrôle | Portée | Pourquoi cette portée |
|---|---|---|
| secrets | `--range <sha distant>..<sha local>` | seuls les commits qui partent. Tout l'historique serait long à chaque push ; l'index ne dirait rien des commits déjà faits |
| tests unitaires | `pytest tests/` | aucune donnée requise, quelques secondes |

Git fournit les références poussées sur l'entrée standard, une ligne par
référence — le hook les lit toutes, et traite le cas d'une branche nouvelle en
face (`sha` distant à zéro) en comparant à ce que le distant connaît déjà.

En cas de secret, l'arrêt est immédiat : les tests ne tournent pas, et le
message rappelle que le commit existe déjà en local, donc qu'il faut révoquer la
valeur puis réécrire l'historique **local**. Faux positif :
`git push --no-verify`.

Le hook cherche l'interpréteur lui-même en préférant celui du projet (c'est lui
qui a `pytest`, et l'environnement virtuel n'est pas actif dans un hook). S'il
n'en trouve aucun, il laisse passer **en le disant** plutôt que de bloquer le
travail — la CI refera les contrôles.

Deux détails sans lesquels le hook ne servirait à rien :

- `.gitattributes` force **LF** sur `scripts/hooks/*`. Avec
  `core.autocrlf=true` (défaut sous Windows), le script serait extrait en CRLF,
  l'interpréteur lirait `#!/bin/sh\r` et le hook ne s'exécuterait pas — *sans
  erreur au moment du push*, donc sans que personne remarque sa disparition.
- Le bit exécutable est enregistré dans l'index (mode `100755`), pour que le
  hook fonctionne aussi sur un clone Linux ou macOS.

Les trois issues ont été vérifiées : plage propre (les tests tournent, tout est
vert), secret dans la plage poussée (refus, tests non exécutés), test en échec
(refus).

#### Constats acceptés (`.secretsignore`)

Un commit antérieur a versionné les appâts de `tests/test_check_secrets.py`
écrits en clair. Ils sont depuis assemblés à l'exécution, mais l'historique git
reste lisible : `--history` les retrouvera toujours. Sans liste d'acceptation,
la vérification d'avant-publication serait **définitivement rouge**, et une
vraie fuite se perdrait dans quatre constats connus.

`.secretsignore` liste donc ces constats par **empreinte** (SHA-256 tronqué de
la valeur, jamais la valeur) avec leur justification. Trois propriétés
délibérées :

- le fichier est versionnable sans rien publier ;
- l'empreinte porte sur la valeur exacte : accepter un appât n'accepte pas un
  secret voisin — c'est testé ;
- le nombre de constats écartés est **affiché à chaque exécution**, pour que la
  liste ne grossisse pas en silence.

Le balayage de l'historique lit tous les objets en un seul `git cat-file
--batch` : 350 versions de fichiers en 0,6 s. Une première version lançait trois
processus git par version de fichier et prenait plusieurs minutes — assez pour
décourager de l'exécuter au moment où elle compte.

### `.github/workflows/train.yml` — manuel

```
données -> artefacts -> évaluation (MLflow) -> PORTE -> publication Blob / HF Hub
```

La publication est conditionnée à la porte. L'étape de récupération des données est à
compléter selon l'hébergement (runner auto-hébergé, ou téléchargement depuis un
stockage) : le workflow échoue volontairement plutôt que d'entraîner sur des données
absentes.

## 7. Ce qui reste à faire

- **récupération des données dans la CI** — bloque le ré-entraînement automatique ;
- **recalcul continu de la fenêtre** : `popular_recent.npy` est aujourd'hui produit
  par le traitement hors-ligne, alors que la fenêtre d'une heure fait un facteur
  **42** sur la précision par rapport à tout l'historique
  (`models/freshness_sweep.json`) ;
- **serveur MLflow partagé** plutôt qu'un fichier SQLite local, dès qu'une deuxième
  personne lance des expériences ;
- **surveillance en production** : les métriques mesurées ici sont hors-ligne. Le CTR
  réel sur les recommandations reste le seul juge.
