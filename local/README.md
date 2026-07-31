# Ricochet — solution locale autonome

Troisième solution de déploiement du dépôt, **indépendante des deux autres** et
**sans aucun service cloud** : l'application Streamlit embarque le moteur de
recommandation et calcule le top-N dans son propre processus.

```
Streamlit (local/app.py)
   └── Recommender (local/recommender.py)  ──lit──▶  models/*.npy, *.pkl
        aucun HTTP · aucun SDK Azure · aucun HF Hub
```

Comparaison avec les deux autres solutions :

| Solution | Service | Artefacts | Dépendances |
|---|---|---|---|
| `azure_function/` + `app/` | Azure Function (HTTP) | Blob Storage | `azure-functions`, `azure-storage-blob`, `requests` |
| `spaces/` | Hugging Face Space | dépôt de modèle HF Hub | `huggingface_hub` |
| **`local/`** | **aucun — tout en processus** | **dossier du disque** | **`streamlit`, `numpy`** |

## Lancement

Depuis la racine du dépôt :

```powershell
pip install -r local/requirements.txt
streamlit run local/app.py
```

Aucune configuration n'est nécessaire si `models/` est présent à la racine.

## Inscrire un client et le recommander

Onglet **Nouveau client** : nom + centres d'intérêt (catégories) → le client reçoit
un `user_id` (à partir de 1 000 000) et un profil de départ constitué des articles
les plus récents de ces catégories.

Onglet **Recommandations** : sélectionnez-le, puis le bouton **Lu** en face d'une
recommandation enregistre la lecture. Le profil s'enrichit, les recommandations
changent — sans aucun ré-entraînement, le content-based n'ayant besoin que d'un
historique.

Les clients et leurs lectures sont stockés dans `local/clients.db` (SQLite,
bibliothèque standard), donc ils survivent au redémarrage. Ce fichier n'est pas
versionné.

Un client inscrit est **absent des facteurs ALS** : le collaboratif l'ignore et
retombe sur le contenu jusqu'au prochain ré-entraînement (`src/prepare_model.py`).
L'application l'indique explicitement.

## Configuration optionnelle

| Variable | Rôle | Défaut |
|---|---|---|
| `MODELS_DIR` | dossier des artefacts | `../models`, puis `./models` |
| `DATA_DIR` | dossier contenant `articles_metadata.csv`, pour afficher catégorie / longueur / date de publication | `data/raw/`, puis `data/news-portal-user/` |
| `CLIENTS_DB` | base SQLite des clients inscrits | `local/clients.db` |

Sans `articles_metadata.csv`, l'application affiche les identifiants d'articles :
c'est un enrichissement d'affichage, pas une dépendance.

```powershell
$env:MODELS_DIR = "D:\artefacts\ricochet"
streamlit run local/app.py
```

## Utiliser ce dossier hors du dépôt

`local/` est autoportant. Pour l'exécuter ailleurs, copiez le dossier et placez
les artefacts à côté :

```
mon-deploiement/
├── app.py
├── recommender.py
├── requirements.txt
└── models/            <- les 7 fichiers générés par src/prepare_model.py
```

```powershell
cd mon-deploiement
pip install -r requirements.txt
$env:MODELS_DIR = "models"
streamlit run app.py
```

## Fichiers

- `app.py` — application Streamlit autonome (sélection d'utilisateur, historique de
  lecture, top-N, mode cold start).
- `recommender.py` — copie du cœur de reco. **Généré** : la source de vérité est
  `src/recommender.py`. Après toute modification de celle-ci :
  `python scripts/sync_recommender.py`.
- `requirements.txt` — `streamlit` + `numpy`, rien d'autre.

## Ce que cette solution n'est pas

Une démo mono-utilisateur, pas un service : pas d'authentification, pas de montée
en charge, pas de mise à jour d'artefacts à chaud. Les artefacts sont chargés une
fois au démarrage (`st.cache_resource`) ; pour les régénérer, relancez
`src/prepare_model.py` puis l'application.
