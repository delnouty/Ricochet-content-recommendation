# Ricochet — article recommendation engine (My Content)

Article recommendation engine: popularity, content-based, ALS, SVD and a mixed
production strategy behind one interface, with an explicit cold-start cascade.
Offline training / numpy-only inference keeps the deployed function
ML-dependency-free; one core ships to an Azure Function (Blob artifacts), to a
Hugging Face Space and to a network-free local app. Temporal-split evaluation,
59 unit tests, MLOps guard rails, architecture and validation notes.

MVP for the **My Content** start-up: recommend **5 articles** per user, built on the
public *News Portal User Interactions by Globo.com* dataset (no proprietary data yet).

## How it works

```
data/news-portal-user/     2 988 181 clicks, 364 047 articles, embeddings of 250 dim
        |
        |  offline    src/prepare_model.py + src/collaborative_surprise.py
        |             PCA 250 -> 50, ALS, SVD, sliding freshness windows
        v
models/                    22 artifacts, 253 MB
        |
        |  online     src/recommender.py -- numpy only
        |             4 most-read of the last hour + 1 content pick from a 6 h pool
        v
top-5 articles             per reader, 0.2 s on the deployed function
```

The split is deliberate: everything expensive (PCA, ALS and SVD training) runs offline
and is serialised into artifacts, so the inference path depends on `numpy` + `pickle`
only. The deployed unit carries no scikit-learn, no `implicit` and no `surprise`, which
keeps the package small and cold starts cheap.

Five ranking strategies sit behind one interface:

| `method` | Ranking signal |
|---|---|
| `mix` (default — **served in production**) | 4 slots to the most-read articles of the last hour, 1 slot to the content pick; the trade-off measured to be best across precision *and* catalogue coverage |
| `content` | user profile = mean of the PCA-reduced embeddings of read articles, then cosine over the candidate pool |
| `collab` | `item_factors · user_factors` from an ALS model trained on implicit feedback |
| `svd` | Surprise SVD on binary ratings with sampled negatives (the article-rating variant does not rank — see [notebooks/06_exp_svd.ipynb](notebooks/06_exp_svd.ipynb)) |
| `hybrid` | min-max normalised blend of content and ALS (`alpha=0.5`); degrades to content-only when the reader is unknown to the CF model |

Already-read articles are always excluded. A reader without usable history goes through a
**four-level fallback cascade** — regional popularity crossed with the freshness window,
then freshness alone, then region alone, then the full history — so no request ever
returns an empty list.

Recency turned out to be the strongest lever in the project: counting clicks over one
hour instead of the whole history multiplies precision by **42** on the test period,
without changing a line of algorithm. That is why the target architecture keeps the
*window* fresh rather than chasing a better model.

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
# Download the Globo.com dataset into data/news-portal-user/ (see data/README.md)
```

### 2. Build the model artifacts

```bash
python -m src.prepare_model --data-dir data/news-portal-user --out-dir models
python -m src.collaborative_surprise --data-dir data/news-portal-user --out-dir models
```

Together they produce the **22 artifacts** (253 MB): the PCA catalogue and its projection,
per-reader histories, popularity rankings (global, regional and over the sliding freshness
windows), article star ratings, and the ALS and SVD factors. Count on about twenty minutes.

If `implicit` is not installed the collaborative step is skipped with a warning instead of
failing — `collab`/`hybrid` then degrade gracefully. The same holds for every optional
artifact: a missing one disables its strategy, and the app says so, rather than failing.

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

Parameters are accepted in the query string or in a JSON body.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `user_id` | — (required) | reader identifier |
| `n` | 5 | number of articles |
| `method` | `mix` | `mix` \| `content` \| `collab` \| `svd` \| `hybrid` |
| `region` | — | region code; affects cold start only |
| `fresh_only` | true | restrict to recent articles; `0`/`false` widens to the whole catalogue |
| `history` | — | comma-separated article ids — the caller's profile, which lets this **stateless** service serve a reader it has never seen |
| `code` | — (required) | function key |

Response: `{"user_id": 0, "method": "mix", "recommendations": [id1, …, id5]}`

Errors: `400` on a missing/non-integer parameter or an unknown `method`, `401` on a bad
key, `500` on an internal failure. The recommender is instantiated once per worker and
reused; only the freshness window is re-read on every call, through a Blob input binding.

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
afterwards. The local solution reads the folder directly; the Azure and Hugging Face
solutions need `models/` re-published to Blob Storage or the HF Hub — and for Azure,
**redeploy rather than restart**: a restart does not guarantee every instance drops its
artifact cache ([docs/deploiement_azure.md](docs/deploiement_azure.md) step 11).

Verified on the real catalogue: three added articles took ids 364047–364049 and entered a
matching user's top-5 immediately, with no model retrained. Rationale and the scheduled
PCA refit that bounds this approach: [docs/architecture.md](docs/architecture.md) §4.b.

## Evaluation

**Temporal 60/20/20 split** on the click timestamp: settings are tuned on the validation
period, the test period is measured once. A random split — or a leave-last-out over the
full data — lets a model learn from clicks that come *after* the ones it must predict.
Measured, that inflates ALS precision from 0.0415 to 0.2415, a factor of **5.8**
(`python scripts/mesure_fuite.py`).

Four criteria, because precision alone always elects the least personalised strategy:

| Configuration | HitRate@5 | Coverage | Personalisation |
|---|---|---|---|
| popularity, 1 h window | **0.2525** | 0.003 % | 4 % |
| **mix — 4 popular + 1 content** | **0.2500** | 0.116 % | 22 % |
| ALS (24 h, 16 factors) | 0.0415 | 0.015 % | 95 % |
| SVD (binary + 4 negatives) | 0.0220 | 0.010 % | 56 % |
| content (6 h pool) | 0.0200 | **0.268 %** | **96 %** |

`mix` is served in production: the slot given to content costs 1 % of precision and
multiplies catalogue coverage by 38.

These values live in [models/baseline_metrics.json](models/baseline_metrics.json) and are
reproduced by `python -m src.evaluate --split test`. A CI quality gate blocks publication
when HitRate@5 or Recall@5 falls more than 10 % below that reference.

Limits, stated rather than hidden: **cold start is not measured** (only readers known at
training time are evaluated), and every number here is offline — the click-through rate on
real recommendations remains the only true judge. Details and the per-approach experiments:
[docs/mlops.md](docs/mlops.md), [notebooks/](notebooks/).

## Tests

Unit tests run on synthetic artifacts — no real data required:

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q

# One-time, per clone: install the pre-push hook. It refuses a push whose
# commits carry a secret in clear text, or whose unit tests fail. Versioned
# under scripts/hooks/, so it stays in sync with the repo.
git config core.hooksPath scripts/hooks
```

78 tests. Coverage: all five ranking strategies including the composition of `mix`,
exclusion of already-read articles, the four-level fallback cascade and regional cold
start, the freshness window (anchor robust to outlier timestamps, automatic widening,
`fresh_only` toggle), the two SVD rating variants, artifact-cache freshness, robustness
(invalid method, `n` larger than the catalogue, ids outside the catalogue injected at
runtime), the sync check between the deployed copies of the core, the persisted PCA
projection, and new-article integration (id assignment, existing vectors left untouched,
immediate recommendability).

Several of these tests exist because the corresponding defect **shipped silently first** —
a service that answers is not a service that is right. See
[docs/gxp/04_Risk_Assessment.md](docs/gxp/04_Risk_Assessment.md) § 6.

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
- [docs/release-v1.0.0.md](docs/release-v1.0.0.md) — what `v1.0.0` delivered and what it measured, as published on the release page.
- `docs/gxp/` — GAMP 5 / CSV documentation pack (VP, URS, FS, RA, RTM, IQ/OQ/PQ, VSR), **DRAFT**.
  GxP impact assessed as low: consumer-facing application, no patient or clinical data.
  These are assistive supporting documents and must be reviewed by a QA/CSV professional
  before any use.
