# Ricochet — article recommendation engine (My Content)

Article recommendation engine: content-based, ALS collaborative and hybrid ranking,
with an explicit cold-start path. Offline training / numpy-only inference keeps the
deployed function ML-dependency-free; one core ships to Azure Functions (Blob
artifacts) and to a self-contained Streamlit Space. Offline eval, unit tests,
architecture notes.

MVP for the **My Content** start-up: recommend **5 articles** per user, built on the
public *News Portal User Interactions by Globo.com* dataset (no proprietary data yet).

## How it works

```
data/raw/  ──[ offline: src/prepare_model.py ]──▶  models/  ──[ online: src/recommender.py ]──▶  top-5
   clicks + embeddings        PCA 250→50, ALS         lightweight artifacts        numpy only
```

The split is deliberate: everything expensive (PCA, ALS training) runs offline and is
serialised into artifacts, so the inference path depends on `numpy` + `pickle` only.
The deployed unit therefore carries no scikit-learn and no `implicit`, which keeps the
package small enough for the Azure free tier and makes cold starts cheap.

Three ranking strategies sit behind one interface:

| `method` | Ranking signal |
|---|---|
| `content` | user profile = mean of the PCA-reduced embeddings of read articles, then cosine over the whole catalogue |
| `collab` | `item_factors · user_factors` from an ALS model trained on implicit feedback |
| `hybrid` (default) | min-max normalised blend of both (`alpha=0.5`); degrades to content-only when the user is unknown to the CF model |

Already-clicked articles are always excluded, and any user without usable history falls
back to the global popularity ranking — the cold-start baseline the target architecture
builds on.

## Three independent deployments

One core (`src/recommender.py`), three self-sufficient solutions — none calls another:

| Solution | Serving | Artifacts from | Cloud dependencies |
|---|---|---|---|
| **Azure** — `azure_function/` + `app/` | HTTP Azure Function (serverless, no dedicated API) | Blob Storage container | `azure-functions`, `azure-storage-blob` |
| **Hugging Face** — `spaces/` | Streamlit Space embedding the recommender | HF Hub model repo (`snapshot_download`) | `huggingface_hub` |
| **Local** — `local/` | Streamlit app computing in-process | folder on disk | **none** |

The `local/` solution is the one to run when you just want the engine working on your
machine: no account, no network call, no cloud SDK — `streamlit` + `numpy` only. Details:
[local/README.md](local/README.md).

Architecture rationale and the **target architecture** (onboarding new users and
articles): [docs/architecture.md](docs/architecture.md).

## Repository layout

```
├── src/
│   ├── recommender.py       # inference core (numpy only) — single source of truth
│   └── prepare_model.py     # offline pipeline -> artifacts in models/
├── notebooks/
│   └── 01_exploration_modelisation.ipynb   # EDA, artifact build, evaluation
├── azure_function/          # serverless service (Python v2 programming model)
│   ├── function_app.py
│   └── shared_code/         # deployed copy of recommender.py + Blob access
├── app/
│   └── streamlit_app.py     # demo UI: user_id -> calls the Function -> 5 articles
├── spaces/                  # standalone Hugging Face Space (embeds the core)
├── local/                   # standalone local solution — no cloud at all
│   ├── app.py               # Streamlit app computing in-process
│   └── recommender.py       # embedded copy of the core
├── scripts/
│   ├── serve_local.py       # local endpoint, same contract as the Function (no Core Tools)
│   ├── run_local.ps1        # one-command local stack: endpoint + Streamlit app
│   ├── add_articles.py      # integrates new articles — projection, no retraining
│   └── sync_recommender.py  # regenerates the deployed copies of the core
├── tests/                   # unit tests on synthetic artifacts
├── docs/                    # architecture, presentation, GxP/CSV pack
├── data/                    # raw data (not versioned — see data/README.md)
└── models/                  # generated artifacts
```

## Quick start

### 1. Data and environment

```bash
pip install -r requirements.txt
# Download the Globo.com dataset into data/raw/ (see data/README.md)
```

### 2. Build the model artifacts

```bash
python -m src.prepare_model --data-dir data/raw --out-dir models --pca 50 --factors 50
```

Produces `articles_embeddings_pca.npy`, `user_clicks.pkl`, `popular_articles.npy` and the
`cf_*` ALS factors. If `implicit` is not installed the collaborative step is skipped with a
warning instead of failing — `collab`/`hybrid` then degrade gracefully.

It also writes `pca_mean.npy` + `pca_components.npy` (~51 KB): the PCA projection itself,
without which a **new article** could not be placed in the reduced space without refitting
the PCA over the whole catalogue and invalidating every stored vector. `project_embeddings()`
uses them to embed a new article in minutes, numpy-only — see
[docs/architecture.md](docs/architecture.md) §4.b.

### 3. Run the local solution — no cloud, no HTTP

```powershell
pip install -r local/requirements.txt
streamlit run local/app.py
```

That's the whole thing. The app embeds the recommender, reads `models/` from disk and
computes in-process; there is no service to start and nothing to configure. It shows the
selected user's reading history alongside the recommendations, and enriches article ids
with category / length / publication date when `articles_metadata.csv` is available.
See [local/README.md](local/README.md) for `MODELS_DIR` / `DATA_DIR` overrides and for
running the folder outside this repo.

### 4. Exercise the HTTP contract locally (optional)

Only useful to test the *Azure-shaped* path — the `app/` UI talking to an endpoint over
HTTP — without installing Azure Functions Core Tools:

```powershell
pip install -r app/requirements.txt
.\scripts\run_local.ps1
```

Starts `scripts/serve_local.py`, waits for the artifacts to load, then opens
`app/streamlit_app.py` pointed at it; stopping Streamlit stops the server. That script
serves the **same route, parameters, response shape and error codes** as the Azure
Function, on stdlib + `numpy` only. It is a development harness, not a deployment
target: no authentication, no Blob access, single process.

Two terminals instead:

```powershell
python scripts/serve_local.py                 # terminal 1 — http://127.0.0.1:7071
$env:FUNCTION_URL = "http://127.0.0.1:7071/api/recommend"
streamlit run app/streamlit_app.py            # terminal 2
```

```powershell
curl "http://127.0.0.1:7071/api/recommend?user_id=0&n=5&method=hybrid"
```

### 5. Run the real Azure Function locally (optional)

Only needed to validate the Azure runtime itself — bindings, `host.json`, cold start.
Requires [Azure Functions Core Tools](https://learn.microsoft.com/azure/azure-functions/functions-run-local):

```powershell
winget install Microsoft.Azure.FunctionsCoreTools
cd azure_function
# local.settings.json already sets MODELS_DIR=../models (copy from the .example if absent)
func start
```

Same test URL as above — `func start` also listens on port 7071.

### Or run the Hugging Face solution instead

```bash
pip install -r spaces/requirements.txt
MODELS_DIR=models streamlit run spaces/app.py    # local artifacts, no Hub round-trip
```

Publishing to the Hub and the Space secrets (`HF_MODEL_REPO`, `HF_TOKEN`):
[spaces/README.md](spaces/README.md).

## API

`GET/POST /api/recommend` (auth level `FUNCTION` — a function key is required once deployed)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `user_id` | — (required) | user identifier |
| `n` | 5 | number of articles |
| `method` | `hybrid` | `content` \| `collab` \| `hybrid` |

Response: `{"user_id": 0, "method": "hybrid", "recommendations": [id1, …, id5]}`

Errors: `400` on a missing/non-integer `user_id` or an unknown `method`, `500` on an
internal failure. The recommender is instantiated once per worker and reused.

## Adding new articles (no retraining)

A newly published article must be recommendable without rebuilding anything. Because the
PCA projection is persisted, its 250-dim embedding can be placed in the existing 50-dim
basis directly:

```powershell
python scripts/add_articles.py --embeddings nouveaux.npy --dry-run   # preview ids
python scripts/add_articles.py --embeddings nouveaux.npy             # integrate
```

Accepts `.npy` or `.pickle` holding an `(n, 250)` matrix. It projects, appends to
`articles_embeddings_pca.npy` with an **atomic write**, and prints the assigned
`article_id`s — which are the catalogue row indices. Re-running is refused if the same
vectors are already present (row fingerprints), so a repeated run can't silently duplicate
articles; override with `--allow-duplicates`.

What it deliberately leaves alone: `popular_articles.npy` (an article with no clicks has no
popularity — it surfaces through content similarity only) and `articles_metadata.csv` (source
data, not an artifact, so apps show `Article #<id>` until it's updated). Restart the app
afterwards, and re-publish `models/` to Blob or the HF Hub for those two solutions.

Verified on the real catalogue: three added articles took ids 364047–364049 and entered a
matching user's top-5 immediately, with no model retrained. Rationale and the scheduled
PCA refit that bounds this approach: [docs/architecture.md](docs/architecture.md) §4.b.

## Evaluation

Offline **leave-last-out** protocol (notebook section 4): for every user with enough
history, the last click is masked and we check whether it appears in the top-N —
**Hit Rate@5**, equal to Recall@5 here since there is a single relevant item per user.

Known limit, stated rather than hidden: the ALS factors are **not** retrained without the
held-out click, so `collab` and the collaborative half of `hybrid` have seen that item
during training and score optimistically. The comparison is indicative, not a rigorous
benchmark.

## Tests

Unit tests run on synthetic artifacts — no real data required:

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

Coverage: content-based / collaborative / hybrid ranking, exclusion of already-seen
articles, popularity fallback on cold start, robustness (invalid method, `n` larger than
the catalogue), the sync check between the deployed copies of the core, the persisted PCA
projection, and new-article integration (id assignment, existing vectors left untouched,
immediate recommendability).

After editing `src/recommender.py`, regenerate the deployed copies:

```bash
python scripts/sync_recommender.py           # update azure_function/shared_code/ and spaces/
python scripts/sync_recommender.py --check   # CI mode: fails if a copy is stale
```

## Azure deployment (summary)

1. Upload the contents of `models/` to a Blob container (`models`).
2. Create a Python Function App plus its Storage account.
3. Set `AZURE_STORAGE_CONNECTION_STRING` and `MODELS_CONTAINER`; leave `MODELS_DIR` unset
   in production (it is the local-development override).
4. `func azure functionapp publish <app-name>` from `azure_function/`.

## Documentation

- [docs/presentation.tex](docs/presentation.tex) — defence deck (Beamer, compile with `xelatex`). Slide budget follows the required structure: 8 slides
  for the modelling approaches (10 min), 5 for the in-app features (6 min), 2 for
  the target architecture (2 min), 1 for the demo (2 min).
- [docs/deploiement_azure.md](docs/deploiement_azure.md) — **step-by-step Azure deployment**: resource creation through to a verified live endpoint, with the errors actually hit and their causes.
- [docs/mlops.md](docs/mlops.md) — temporal split, MLflow tracking, model registry, metric gate, CI.
- [docs/architecture.md](docs/architecture.md) — MVP architecture, alternatives considered, target architecture.
- [docs/sequences.md](docs/sequences.md) — UML sequence diagrams for the three deployments: where the ranking is computed, what a cold start costs, and how a just-registered reader is served by a stateless API.
- `docs/gxp/` — GAMP 5 / CSV documentation pack (VP, URS, FS, RA, RTM, IQ/OQ/PQ, VSR), **DRAFT**.
  GxP impact assessed as low: consumer-facing application, no patient or clinical data.
  These are assistive supporting documents and must be reviewed by a QA/CSV professional
  before any use.
