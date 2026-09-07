# MLOps — traçabilité, versionnage, intégration continue

Ce document décrit comment un résultat de ce dépôt devient reproductible, et comment
un modèle ré-entraîné est empêché de partir en production s'il dégrade le service.

## 1. Pourquoi c'était nécessaire

Les premières mesures du projet étaient fausses : les modèles étaient entraînés sur
100 % des données puis évalués sur ces mêmes données. L'ALS affichait un HitRate@5 de
**0,2300** ; avec un découpage temporel correct, il tombe à **0,0250**. Un écart de
42× qui n'était visible nulle part, parce que rien n'était tracé.

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

Deux règles, établies par les notebooks 03 à 07 :

1. **le vivier de candidats est recalculé à l'instant de la requête** — pour évaluer
   sur le test, l'historique est `entraînement + validation`. Ce n'est pas une fuite :
   un service en production connaît le passé jusqu'à la minute présente. Un vivier
   gelé à la fin de l'entraînement donne **0,0000** pour toutes les méthodes ;
2. **chaque méthode est réglée séparément** sur la validation. Comparer une méthode
   réglée à des méthodes par défaut fausse la conclusion — l'ALS passe de 0,0080 à
   0,0250 selon sa fenêtre d'entraînement.

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
| `pytest tests/` | le cœur de reco, sur artefacts synthétiques |
| `sync_recommender.py --check` | les trois copies déployées du cœur sont à jour |
| taille des fichiers | aucun fichier > 5 Mo versionné |
| artefacts | aucun `.npy` / `.pkl` / `.db` dans git |
| secrets | aucune clé en clair dans le code ou les notebooks |

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
- **fenêtre glissante en production** : `popular_articles.npy` et `article_stars.npy`
  sont calculés sur tout l'historique, alors que la fenêtre d'une heure fait un
  facteur 250 sur la précision (§4.c de `architecture.md`) ;
- **serveur MLflow partagé** plutôt qu'un fichier SQLite local, dès qu'une deuxième
  personne lance des expériences ;
- **surveillance en production** : les métriques mesurées ici sont hors-ligne. Le CTR
  réel sur les recommandations reste le seul juge.
