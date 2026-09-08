# Diagrammes de séquence — les trois solutions

Une requête de recommandation, de bout en bout, dans chacun des trois
déploiements. Les diagrammes suivent le code (`azure_function/function_app.py`,
`spaces/app.py`, `local/app.py`, `src/app_ui.py`) et non une intention : les noms
de méthodes sont ceux qui existent.

Ce que ces trois séquences font ressortir, et qui n'apparaît pas sur un schéma de
composants :

- **où le calcul a lieu** — dans le processus de l'interface (local, Hugging Face)
  ou derrière un appel réseau (Azure) ;
- **ce que coûte un démarrage à froid** et ce qu'il ne coûte qu'une fois ;
- **comment un lecteur inscrit à l'instant est recommandé** par un service qui ne
  le connaît pas.

Le cœur de recommandation est le même partout (`src/recommender.py`, numpy seul) ;
les copies déployées sont générées et la CI le vérifie.

---

## 1. Solution locale — tout dans un processus

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilisateur
    participant ST as Streamlit<br/>local/app.py
    participant UI as ui.run<br/>(copie de src/app_ui.py)
    participant DB as SQLite<br/>local/clients.db
    participant FS as Disque<br/>models/
    participant R as Recommender<br/>(numpy)

    U->>ST: streamlit run local/app.py
    ST->>ST: resolve_models_dir()
    Note over ST: cherche $MODELS_DIR, puis ../models, puis ./models
    ST->>UI: run(models_dir, clients_db)

    rect rgb(240, 246, 250)
    Note over UI,R: Démarrage à froid — une seule fois (st.cache_resource)
    UI->>R: Recommender(models_dir)
    R->>FS: lecture des 22 artefacts (253 Mo)
    FS-->>R: tableaux numpy et dictionnaires
    UI->>DB: UserStore(clients_db)
    UI->>DB: all_histories()
    DB-->>UI: {user_id: [article_id]}
    UI->>R: sync_store_into_model()
    Note over R: les clients inscrits entrent dans user_clicks,<br/>donc le contenu les prend en compte sans ré-entraînement
    end

    U->>UI: choisit un lecteur, une stratégie, clique « Recommander »
    UI->>R: recommend(user_id, n=5, method="mix", fresh_only=True)
    R->>R: vivier de fraîcheur, puis classement
    R-->>UI: [5 article_id]
    UI-->>U: 5 lignes, avec étoiles et nombre de lecteurs

    opt L'utilisateur marque un article comme lu
    UI->>DB: add_read(user_id, article_id)
    UI->>R: user_clicks[user_id] mis à jour
    Note over UI: la recommandation suivante change,<br/>sans ré-entraînement ni redéploiement
    end
```

**Ce que montre ce diagramme** : aucun appel réseau, et le modèle vit dans le
processus de l'interface. C'est la solution qui fonctionne dans un train, et celle
qui sert de référence de correction pour les deux autres (étape 2 du tutoriel de
déploiement).

---

## 2. Solution Hugging Face — même code, artefacts distants

```mermaid
sequenceDiagram
    autonumber
    actor V as Visiteur
    participant SP as Space (SDK Docker)<br/>spaces/app.py
    participant ML as model_loader
    participant HUB as HF Hub<br/>DaryaEL/ricochet-models
    participant UI as ui.run<br/>(copie de src/app_ui.py)
    participant DB as SQLite /tmp<br/>(éphémère)
    participant R as Recommender<br/>(numpy)

    Note over SP: image construite par le Dockerfile,<br/>Streamlit n'est plus un SDK intégré

    V->>SP: ouvre https://daryael-ricochet.hf.space
    SP->>ML: ensure_models()
    alt MODELS_DIR défini (test local)
        ML-->>SP: dossier local
    else HF_MODEL_REPO défini (Space)
        ML->>HUB: snapshot_download(*.npy, *.pkl, recent_window.json)
        HUB-->>ML: 253 Mo dans le cache huggingface_hub
        ML-->>SP: chemin du cache
    else aucune des deux
        ML-->>SP: RuntimeError explicite
        Note over ML,SP: échouer en le disant, plutôt que de deviner un dépôt
    end

    SP->>DB: open_store() → SQLite dans /tmp
    Note over DB: un Space est éphémère : la base est perdue au redémarrage<br/>et partagée entre visiteurs → bannière d'avertissement
    SP->>UI: run(models_dir, clients_db, banniere, store)
    UI->>R: Recommender(models_dir)

    V->>UI: clique « Recommander »
    UI->>R: recommend(user_id, n=5, method="mix")
    R-->>UI: [5 article_id]
    UI-->>V: 5 lignes

    opt Secret AZURE_STORAGE_CONNECTION_STRING présent
    Note over DB: open_store() choisit Azure Table Storage :<br/>les clients survivent aux redémarrages, la bannière change
    end
```

**Ce que montre ce diagramme** : la seule différence avec la solution locale est
l'origine des artefacts. Le calcul reste dans le processus du Space — aucun appel
à Azure, les deux solutions sont indépendantes. Le disque n'étant pas persistant,
les 253 Mo sont retéléchargés à chaque démarrage à froid.

---

## 3. Solution Azure — architecture 2, calcul derrière le réseau

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilisateur
    participant APP as app/app_full.py<br/>(Streamlit)
    participant TS as Azure Table Storage<br/>ricochetclients / ricochetreads
    participant AR as ApiRecommender<br/>(app/api_client.py)
    participant FN as Azure Function<br/>/api/recommend
    participant BL as Blob Storage<br/>conteneur models
    participant R as Recommender<br/>(dans la Function)

    U->>APP: ouvre l'application
    APP->>TS: list_clients(), all_histories()
    TS-->>APP: clients inscrits et leurs lectures
    APP->>AR: artefacts légers (36 Mo : historiques, étoiles, popularité)
    Note over AR: pas d'embeddings côté client :<br/>seul le service en a besoin pour calculer

    U->>APP: clique « Recommander »
    APP->>AR: recommend(user_id, n, method, region, fresh_only)
    opt user_id >= 1 000 000 (client inscrit dans l'application)
    AR->>AR: history = lectures du client
    Note over AR: transmis en paramètre : le service est sans état<br/>et ne connaît pas ce lecteur
    end
    AR->>FN: GET /api/recommend — user_id, n, method, region, fresh_only, history, code

    rect rgb(250, 245, 235)
    Note over FN,BL: Bindings — à CHAQUE invocation, ~2 ms
    BL-->>FN: popular_recent.npy, candidates_recent.npy, recent_window.json (23 Ko)
    end

    alt Démarrage à froid (première invocation de l'instance)
        FN->>BL: ensure_models() — énumère le conteneur
        BL-->>FN: 22 artefacts, 253 Mo vers /tmp
        Note over FN,BL: validité du cache jugée sur taille ET date du blob
        FN->>R: Recommender(models_dir)
    else Invocation à chaud
        FN->>R: instance en cache (variable globale)
    end

    FN->>R: set_freshness(popular_recent, candidates_recent, window)
    Note over FN,R: une lecture de binding qui échoue est journalisée,<br/>le moteur garde la fenêtre du démarrage — pas d'erreur 500
    FN->>R: recommend(user_id, n, method, region, fresh_only, history)
    R-->>FN: [5 article_id]
    FN-->>AR: 200 {"user_id", "method", "recommendations"}
    AR-->>APP: [5 article_id] + latence mesurée
    APP-->>U: 5 lignes

    opt L'utilisateur marque un article comme lu
    APP->>TS: add_read(user_id, article_id)
    Note over TS: PartitionKey = lecteur → l'historique se lit<br/>en une requête de partition
    end
```

**Ce que montre ce diagramme** : les deux accès à Blob Storage, et pourquoi ils ne
sont pas au même endroit. Les 23 Ko de fraîcheur passent par des *bindings* relus à
chaque appel — une nouvelle fenêtre horaire s'applique **sans redémarrage**. Les
253 Mo passent par le SDK avec cache : un binding coûterait 8 s par appel au lieu
de 0,2 s.

Le paramètre `history` est ce qui rend le service utilisable pour un lecteur
inscrit une seconde plus tôt : la Function n'a aucun état, l'appelant apporte le
profil.

---

## Comparaison des trois séquences

| | Locale | Hugging Face | Azure |
|---|---|---|---|
| Où le classement est calculé | processus de l'interface | processus du Space | Azure Function |
| Origine des artefacts | disque | HF Hub (téléchargés au démarrage) | Blob Storage (binding + cache) |
| Appels réseau par recommandation | 0 | 0 | 1 |
| Clients inscrits | SQLite persistant | SQLite `/tmp`, éphémère | Table Storage, persistant |
| Coût du démarrage à froid | lecture disque | 253 Mo téléchargés | 253 Mo téléchargés, ~7,5 s |
| Recommandation à chaud | immédiate | immédiate | ~0,2 s |
| Mise à jour de la fenêtre de fraîcheur | régénérer les artefacts | republier le dépôt de modèle | **immédiate**, sans redémarrage |

Le tableau se lit dans un sens : plus on va vers Azure, plus le modèle est loin de
l'interface — et plus l'exploitation devient possible (mise à jour de la fraîcheur
sans interruption, mise à l'échelle, un seul modèle pour plusieurs clients).
