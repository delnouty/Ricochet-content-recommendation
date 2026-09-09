# Functional Specification (FS)

| Field | Value |
|-------|--------|
| Document ID | MC-FS-001 |
| Version | 0.2 |
| Status | DRAFT — for QA review |
| System | Ricochet — article recommendation system |
| Issue date | 2026-09-08 |
| Supersedes | Version 0.1 of 2026-07-20 |

> **Assistive supporting material — to be reviewed and approved by QA/CSV before
> use.**

## Approval table

| Role | Name | Signature | Date |
|------|-----|-----------|------|
| Author (technical) | | | |
| Quality / QA review | | | |

## 1. Software architecture (recap)

A single recommendation core, `Recommender` (`src/recommender.py`, **numpy only**
at inference time), fed by artifacts pre-computed offline and exposed by **three
independent deployments**. The deployed copies of the core are **generated** from
`src/` and never hand-edited.

No machine-learning library is required at inference time: scikit-learn (PCA),
`implicit` (ALS) and `surprise` (SVD) serve only to produce the artifacts.

References: `docs/architecture.md` (static), `docs/sequences.md` (dynamic — the
sequence diagrams of the three solutions).

## 2. Functional specifications

| ID | Covers (URS) | Specification |
|----|--------------|---------------|
| FS-001 | URS-001, URS-002 | `Recommender.recommend(user_id, n=5, method)` returns a list of at most `n` `article_id`, never more, and never with a duplicate. `n` is exposed by the API and the interface, default **5**, range 1–10 in the interface. |
| FS-002 | URS-003 | Method `content`: profile = mean of the embeddings (PCA-reduced) of the articles read; score = cosine similarity against the catalogue; sorted descending. |
| FS-003 | URS-004 | Method `collab`: score = product of the latent reader × article factors (pre-trained ALS, `cf_*` artifacts). |
| FS-004 | URS-005 | The `method` parameter selects the strategy among **`mix`, `content`, `collab`, `svd`, `hybrid`**. Default: **`mix`** (the strategy served in production, see FS-017). `hybrid` combines content and collaborative through min-max normalisation. Any other value is refused (see FS-015). |
| FS-005 | URS-006, URS-019 | **Fallback cascade** for a reader with no usable profile, in this order: (1) the popularity of their region crossed with the freshness window, (2) the freshness window alone, (3) the popularity of their region alone, (4) popularity over the whole history. A partial list is completed by the next level. **No request ever returns an empty list.** |
| FS-006 | URS-007 | The `article_id` values present in the reader's history are excluded from every result (score forced to `-inf`, then non-finite scores filtered out). The exclusion applies to every strategy, including the popularity slots of `mix`. |
| FS-007 | URS-008 | The PCA projection (`pca_mean.npy`, `pca_components.npy`) is **serialised alongside the catalogue**. A new article that has an embedding is projected, appended to the catalogue, and becomes recommendable through the content route **without re-fitting the PCA** and without re-training. |
| FS-008 | URS-009, URS-018 | A three-tab Streamlit interface: **Recommendations** (choice of reader, strategy, number of articles, freshness checkbox, "Read" marking), **Browse articles** (the full catalogue, four sort orders, filter by rating, hiding of read articles), **New reader** (sign-up). Each row shows the identifier, a star rating, the number of readers, the category, the length and the date. |
| FS-009 | URS-010 | Three independent solutions: **Azure** — `azure_function/function_app.py`, `GET/POST /api/recommend`, artifacts read from Blob Storage; **Hugging Face** — `spaces/app.py`, a **Docker SDK** Space, `Recommender` embedded, artifacts loaded from an HF Hub model repository; **local** — `local/app.py`, artifacts on disk, **no network access**. |
| FS-010 | URS-011 | The artifacts are loaded **once** per instance (the `_recommender` module global on the Azure side, `st.cache_resource` in the interfaces) and then reused. Inference is vectorised (numpy). |
| FS-011 | URS-012, URS-013 | `src/prepare_model.py` produces named, deterministic artifacts (`random_state=42` for PCA and ALS); `src/collaborative_surprise.py` produces the SVD artifacts. The 22 artifacts are published to Blob Storage and to HF Hub. |
| FS-012 | URS-014 | A Git repository; `.gitignore` excludes raw data, large artifacts and secrets. The two measurement records (`models/baseline_metrics.json`, `models/freshness_sweep.json`) are **explicitly versioned**: they serve as references. |
| FS-013 | URS-015 | **Evaluation protocol**: a **temporal 60 / 20 / 20** split on the click timestamp. Settings are chosen on the validation period, and the test period serves only for the final measurement. Four metrics are produced: HitRate@5, Recall@5, catalogue coverage, personalisation. The candidate pool and the collaborative models are recomputed from **everything that precedes** the period being evaluated. Command: `python -m src.evaluate --split test`. |
| FS-014 | URS-016 | Re-training is reproducible through `prepare_model.py` / `collaborative_surprise.py`. Every run is recorded in **MLflow** (parameters, metrics, git commit) and the artifacts are versioned in the model registry, making a rollback possible. |
| FS-015 | URS-001 | Input validation: `user_id` and `n` integers; `region` an integer or absent; `history` a comma-separated list of integers; `method` a member of the set in FS-004. Any invalid input produces an explicit error (`ValueError` internally, **HTTP 400** through the API) without interrupting the service. |
| FS-016 | URS-017 | Inputs and outputs are **anonymous numeric identifiers**. No personal or sensitive data is processed or stored. The name entered at sign-up is a display label, and the interface warns against entering personal data there. |
| **FS-017** | URS-019 | **The strategy served in production (`mix`)**: of five slots, **four** go to the most-read articles of the **one-hour window**, and **one** to the content route, chosen from the **six-hour pool**. Measured justification: the slot given to content costs no significant accuracy and multiplies the share of catalogue exposed by 38. |
| **FS-018** | URS-019 | **Freshness artifacts**, produced by `prepare_model`: `popular_recent.npy` (a popularity ranking over the ranking window), `candidates_recent.npy` (a candidate pool over the wider window), `recent_window.json` (window metadata: requested and effective durations, bounds, counts). The temporal anchor is the **0.999 quantile** of the timestamps, so that an outlying timestamp cannot move the window. If the window holds fewer than `min_articles` articles it is **widened automatically**, and the effective duration is reported in the metadata. |
| **FS-019** | URS-019 | The **`fresh_only`** parameter (default **true**) restricts every strategy to the recent pool. Disabling it widens to the whole catalogue; it is exposed in the interface and the API for comparison purposes, and is not the production configuration. |
| **FS-020** | URS-018 | **Registering a reader**: a mandatory, unique name, an **optional region**, and an optional initial profile (articles already read). Identifiers are assigned sequentially from **1 000 000**, which distinguishes them unambiguously from the dataset's readers. An empty or already-used name is refused with an explicit message. A registered reader receives recommendations **immediately**. |
| **FS-021** | URS-018 | The API's **`history`** parameter carries the reader's profile in the request. It takes **precedence** over the artifacts and lets a **stateless** service recommend to a reader it does not know. The override is local to the request and does not modify the engine's shared state. |
| **FS-022** | URS-022 | **Reader store**: SQLite for the local solution; **Azure Table Storage** as soon as a connection string is available (a shared or ephemeral deployment), falling back to SQLite if it is unavailable, which is announced in the logs. Reads are timestamped to the **microsecond**, so that their order is preserved. Where persistence is not guaranteed (a Hugging Face Space with no backing storage), the interface displays this as a banner. |
| **FS-023** | URS-020 | **Two ways into Blob Storage, according to how often things change.** The three freshness artifacts (23 kB) arrive through a ***blob input binding*** and are re-read **on every invocation**: a new window takes effect with no restart. The heavy artifacts (253 MB) are downloaded by the **SDK** at cold start and then cached. A failed binding read is logged and the engine **keeps the window it started with**: the service degrades, it does not stop. |
| **FS-024** | URS-012, URS-020 | The validity of the local artifact cache is judged on **both the size *and* the date** of the blob. An artifact rebuilt to an identical size is therefore downloaded again. |
| **FS-025** | URS-021 | **Non-regression guard**: `scripts/check_metrics.py` compares a training run's metrics against `models/baseline_metrics.json` and **exits with an error** if HitRate@5 or Recall@5 drops beyond the tolerance (10 % by default), which blocks publication in CI. The reference is only updated deliberately (`--promote`). |
| **FS-026** | URS-010 | The deployed copies of the core and the interface (`azure_function/`, `spaces/`, `local/`) are **generated** from `src/` by `scripts/sync_recommender.py`. `--check` verifies that they are current and is run by CI. |
| **FS-027** | URS-004 | Method `svd`: **binary ratings with sampled negatives** (4 negatives per positive), the only variant that ranks. The variant based on article stars is kept for comparison only: since its rating depends on the article alone, it cannot rank for a given reader. |
| **FS-028** | URS-010, URS-011 | **Runtime constraints.** Azure Function: **Python 3.13** on a **Flex Consumption** plan — the Linux Consumption plan caps at Python 3.12 and its retirement is announced, and Flex Consumption is not available in every region. Hugging Face Space: a `python:3.13-slim` image, the container run as UID 1000, the app served on port 7860. Local environment: Python ≥ 3.11. At inference time, only **numpy** and the standard library are required. |

## 3. Interfaces

### 3.1 API (the Azure solution) — `GET/POST /api/recommend`

Parameters accepted in the query string or in the JSON body.

| Parameter | Type | Default | Required | Role |
|-----------|------|--------|-------------|------|
| `user_id` | int | — | **yes** | the reader to recommend to |
| `n` | int | 5 | no | number of articles |
| `method` | str | **`mix`** | no | strategy (see FS-004) |
| `region` | int | — | no | region code; only affects the cold start |
| `fresh_only` | bool | **true** | no | restrict to recent articles (see FS-019) |
| `history` | str | — | no | comma-separated `article_id` (see FS-021) |
| `code` | str | — | **yes** | function key (authorisation level `FUNCTION`) |

Response `200`:
`{"user_id": int, "method": str, "recommendations": [article_id, …]}`

Errors: **400** (missing parameter, invalid type, unknown `method`), **401**
(missing or incorrect key), **500** (internal error, logged).

### 3.2 Artifacts (the data contract)

22 files, 253 MB, produced offline and published to Blob Storage and HF Hub.

| Group | Files | Role |
|--------|----------|------|
| Required to start | `articles_embeddings_pca.npy`, `user_clicks.pkl`, `popular_articles.npy` | their absence raises an explicit error |
| Freshness | `popular_recent.npy`, `candidates_recent.npy`, `recent_window.json` | see FS-018, FS-023 |
| Projection | `pca_mean.npy`, `pca_components.npy` | see FS-007 |
| Collaborative ALS | `cf_user_factors.npy`, `cf_item_factors.npy`, `cf_item_ids.npy`, `cf_user_index.pkl` | see FS-003 |
| Collaborative SVD | `svd_*` (7 files) | see FS-027 |
| Display and cold start | `article_stars.npy`, `article_clicks.npy`, `popular_by_region.pkl` | ratings, counts, regional fallback |

Artifacts that are absent but optional (freshness, regions, stars, SVD) do not
prevent start-up: the corresponding function is simply unavailable, and the
interface says so.

### 3.3 Reader store

| Table / file | Key | Content |
|-----------------|-----|---------|
| `ricochetclients` (Table Storage) | PartitionKey `client`, RowKey `user_id` | name, creation date, region |
| `ricochetreads` (Table Storage) | PartitionKey `user_id`, RowKey `article_id` | read timestamp |
| `clients.db` (SQLite) | — | the local equivalent, same interface |

## 4. Behaviour on failure

The rule is constant: **degrade and say so, rather than stop.**

| Failure | Specified behaviour |
|-------------|-----------------------|
| Freshness artifacts unreadable through the binding | warning logged, the start-up window kept (FS-023) |
| An optional artifact absent | the function is unavailable, and this is shown in the interface |
| A required artifact absent | an explicit error naming the file and the publication command |
| Table Storage unavailable | fall back to SQLite, message logged (FS-022) |
| No artifact source configured (Space) | an explicit error, no repository guessed |
| Unknown reader, no profile | the fallback cascade, never an empty list (FS-005) |
| Unknown `method` | HTTP 400 with the error message (FS-015) |

## 5. Revision history

| Version | Date | Changes | Reason |
|---------|------|---------------|-------|
| 0.1 | 2026-07-20 | Initial issue (FS-001 to FS-016). | — |
| 0.2 | 2026-09-08 | **Corrected**: FS-004 (the set of strategies and the default), FS-005 (a four-level cascade instead of a simple fallback), FS-008 (a three-tab interface), FS-009 (three solutions; Docker SDK for the Space), FS-013 (the evaluation protocol: a temporal split and four metrics, replacing *leave-last-out*), FS-014 (MLflow and the registry). **Added**: FS-017 to FS-028. **Added**: § 3.2 the artifact contract, § 3.3 the reader store, § 4 behaviour on failure. | v0.1 described a system with no notion of freshness, no reader sign-up, and an evaluation protocol since invalidated (*leave-last-out* on complete data overstates accuracy by a measured factor of 5.8). It could therefore no longer serve as a basis for the OQ. |

> **Note on method.** The identifiers FS-001 to FS-016 are kept: where a
> specification described the same function in a way that had become inaccurate,
> it was corrected under its original identifier. New functions receive new
> identifiers. No identifier has been reassigned to a different function.
