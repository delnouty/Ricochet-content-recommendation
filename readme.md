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

## Two independent deployments

One core (`src/recommender.py`), two self-sufficient solutions — neither calls the other:

| Solution | Serving | Artifacts loaded from |
|---|---|---|
| **Azure** — `azure_function/` + `app/` | HTTP Azure Function (serverless, no dedicated API) | Blob Storage container |
| **Hugging Face** — `spaces/` | Streamlit Space that embeds the recommender and computes locally | HF Hub model repo (`snapshot_download`) |

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
├── scripts/
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

### 3. Run the Azure Function locally

```bash
cd azure_function
cp local.settings.json.example local.settings.json   # then set MODELS_DIR=../models
func start                                            # requires Azure Functions Core Tools
```

Test: `curl "http://localhost:7071/api/recommend?user_id=0&n=5&method=hybrid"`

### 4. Run the demo app

```bash
pip install -r app/requirements.txt
FUNCTION_URL=http://localhost:7071/api/recommend streamlit run app/streamlit_app.py
```

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
the catalogue), and the sync check between the deployed copies of the core.

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

- [docs/architecture.md](docs/architecture.md) — MVP architecture, alternatives considered, target architecture.
- `docs/My_Content_presentation.pptx` / `.pdf` — stakeholder deck, generated by `docs/build_presentation.py`.
- `docs/gxp/` — GAMP 5 / CSV documentation pack (VP, URS, FS, RA, RTM, IQ/OQ/PQ, VSR), **DRAFT**.
  GxP impact assessed as low: consumer-facing application, no patient or clinical data.
  These are assistive supporting documents and must be reviewed by a QA/CSV professional
  before any use.
