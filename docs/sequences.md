# Sequence diagrams — the three solutions

One recommendation request, end to end, in each of the three deployments. The
diagrams follow the code (`azure_function/function_app.py`, `spaces/app.py`,
`local/app.py`, `src/app_ui.py`) rather than an intention: the method names are
the ones that actually exist.

What these three sequences bring out, and a component diagram cannot:

- **where the computation happens** — inside the UI process (local, Hugging
  Face) or behind a network call (Azure);
- **what a cold start costs**, and what it only costs once;
- **how a reader who signed up a second ago** gets recommendations from a
  service that has never heard of them.

The recommendation core is the same everywhere (`src/recommender.py`, numpy
only); the deployed copies are generated, and CI checks that they match.

---

## 1. Local — everything in one process

```mermaid
sequenceDiagram
    autonumber
    actor U as Reader
    participant ST as Streamlit<br/>local/app.py
    participant UI as ui.run<br/>(copy of src/app_ui.py)
    participant DB as SQLite<br/>local/clients.db
    participant FS as Disk<br/>models/
    participant R as Recommender<br/>(numpy)

    U->>ST: streamlit run local/app.py
    ST->>ST: resolve_models_dir()
    Note over ST: tries $MODELS_DIR, then ../models, then ./models
    ST->>UI: run(models_dir, clients_db)

    rect rgb(240, 246, 250)
    Note over UI,R: Cold start — once only (st.cache_resource)
    UI->>R: Recommender(models_dir)
    R->>FS: read the 22 artifacts (253 MB)
    FS-->>R: numpy arrays and dictionaries
    UI->>DB: UserStore(clients_db)
    UI->>DB: all_histories()
    DB-->>UI: {user_id: [article_id]}
    UI->>R: sync_store_into_model()
    Note over R: readers who signed up enter user_clicks,<br/>so the content model uses them with no re-training
    end

    U->>UI: picks a reader and a strategy, clicks "Recommend"
    UI->>R: recommend(user_id, n=5, method="mix", fresh_only=True)
    R->>R: freshness candidate pool, then ranking
    R-->>UI: [5 article_id]
    UI-->>U: 5 rows, with stars and reader counts

    opt The reader marks an article as read
    UI->>DB: add_read(user_id, article_id)
    UI->>R: user_clicks[user_id] updated
    Note over UI: the next recommendation changes,<br/>with no re-training and no redeployment
    end
```

**What this diagram shows**: no network call at all, and the model living inside
the UI process. This is the solution that works on a train, and the one used as
the correctness reference for the other two (step 2 of the deployment tutorial).

---

## 2. Hugging Face — same code, remote artifacts

```mermaid
sequenceDiagram
    autonumber
    actor V as Visitor
    participant SP as Space (Docker SDK)<br/>spaces/app.py
    participant ML as model_loader
    participant HUB as HF Hub<br/>DaryaEL/ricochet-models
    participant UI as ui.run<br/>(copy of src/app_ui.py)
    participant DB as SQLite in /tmp<br/>(ephemeral)
    participant R as Recommender<br/>(numpy)

    Note over SP: image built by the Dockerfile,<br/>Streamlit is no longer a built-in SDK

    V->>SP: opens https://daryael-ricochet.hf.space
    SP->>ML: ensure_models()
    alt MODELS_DIR set (local test)
        ML-->>SP: local directory
    else HF_MODEL_REPO set (the Space)
        ML->>HUB: snapshot_download(*.npy, *.pkl, recent_window.json)
        HUB-->>ML: 253 MB into the huggingface_hub cache
        ML-->>SP: path to the cache
    else neither is set
        ML-->>SP: explicit RuntimeError
        Note over ML,SP: fail and say so, rather than guess a repository
    end

    SP->>DB: open_store() -> SQLite in /tmp
    Note over DB: a Space is ephemeral: the database is lost on restart<br/>and shared between visitors -> warning banner
    SP->>UI: run(models_dir, clients_db, banner, store)
    UI->>R: Recommender(models_dir)

    V->>UI: clicks "Recommend"
    UI->>R: recommend(user_id, n=5, method="mix")
    R-->>UI: [5 article_id]
    UI-->>V: 5 rows

    opt Secret AZURE_STORAGE_CONNECTION_STRING present
    Note over DB: open_store() picks Azure Table Storage instead:<br/>readers survive restarts, and the banner changes
    end
```

**What this diagram shows**: the only difference from the local solution is where
the artifacts come from. The computation stays inside the Space process — no call
to Azure, the two solutions are independent. Since the disk is not persistent,
the 253 MB are downloaded again on every cold start.

---

## 3. Azure — architecture 2, computation behind the network

```mermaid
sequenceDiagram
    autonumber
    actor U as Reader
    participant APP as app/app_full.py<br/>(Streamlit)
    participant TS as Azure Table Storage<br/>ricochetclients / ricochetreads
    participant AR as ApiRecommender<br/>(app/api_client.py)
    participant FN as Azure Function<br/>/api/recommend
    participant BL as Blob Storage<br/>container models
    participant R as Recommender<br/>(inside the Function)

    U->>APP: opens the application
    APP->>TS: list_clients(), all_histories()
    TS-->>APP: registered readers and their reads
    APP->>AR: light artifacts (36 MB: histories, stars, popularity)
    Note over AR: no embeddings on the client side:<br/>only the service needs them to compute

    U->>APP: clicks "Recommend"
    APP->>AR: recommend(user_id, n, method, region, fresh_only)
    opt user_id >= 1 000 000 (reader registered in the app)
    AR->>AR: history = that reader's reads
    Note over AR: passed as a parameter: the service is stateless<br/>and has never seen this reader
    end
    AR->>FN: GET /api/recommend — user_id, n, method, region, fresh_only, history, code

    rect rgb(250, 245, 235)
    Note over FN,BL: Bindings — on EVERY invocation, about 2 ms
    BL-->>FN: popular_recent.npy, candidates_recent.npy, recent_window.json (23 kB)
    end

    alt Cold start (first invocation on this instance)
        FN->>BL: ensure_models() — enumerates the container
        BL-->>FN: 22 artifacts, 253 MB into /tmp
        Note over FN,BL: cache validity judged on size AND blob date
        FN->>R: Recommender(models_dir)
    else Warm invocation
        FN->>R: instance already cached (module global)
    end

    FN->>R: set_freshness(popular_recent, candidates_recent, window)
    Note over FN,R: a failed binding read is logged and the engine keeps<br/>the window it started with — no HTTP 500
    FN->>R: recommend(user_id, n, method, region, fresh_only, history)
    R-->>FN: [5 article_id]
    FN-->>AR: 200 {"user_id", "method", "recommendations"}
    AR-->>APP: [5 article_id] plus the measured latency
    APP-->>U: 5 rows

    opt The reader marks an article as read
    APP->>TS: add_read(user_id, article_id)
    Note over TS: PartitionKey = reader, so a history is one<br/>partition query
    end
```

**What this diagram shows**: the two ways into Blob Storage, and why they are not
in the same place. The 23 kB of freshness go through *bindings* that are re-read
on every call, so a new hourly window applies **without a restart**. The 253 MB
go through the SDK with a cache: a binding there would cost 8 s per call instead
of 0.2 s.

The `history` parameter is what makes the service usable for a reader who signed
up one second earlier: the Function holds no state, so the caller brings the
profile with it.

---

## The three sequences compared

| | Local | Hugging Face | Azure |
|---|---|---|---|
| Where ranking is computed | UI process | Space process | Azure Function |
| Where artifacts come from | disk | HF Hub (downloaded at start-up) | Blob Storage (binding + cache) |
| Network calls per recommendation | 0 | 0 | 1 |
| Registered readers | persistent SQLite | SQLite in `/tmp`, ephemeral | Table Storage, persistent |
| Cold-start cost | disk read | 253 MB downloaded | 253 MB downloaded, about 7.5 s |
| Warm recommendation | immediate | immediate | about 0.2 s |
| Updating the freshness window | regenerate the artifacts | republish the model repository | **immediate**, no restart |

The table reads in one direction: the closer you get to Azure, the further the
model sits from the interface — and the more operable the whole thing becomes.
Freshness updated without an interruption, scaling, and one model serving several
clients.
