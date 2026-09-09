# Ricochet v1.0.0 — MVP

| | |
|---|---|
| Tag | `v1.0.0` |
| Date | 2026-09-09 |
| Commit | `54fa333` |
| Release page | <https://github.com/delnouty/Ricochet-content-recommendation/releases/tag/v1.0.0> |

Text published as the GitHub release description, kept here as the record
of what this version delivered and what it measured.

---

Article recommendation MVP for the **My Content** start-up: five articles per
reader, built on the public *News Portal User Interactions by Globo.com* dataset
— 2 988 181 clicks, 322 897 readers, 364 047 articles, no proprietary data.

The dataset is anonymised at source: an article has no title and no text, only a
250-dimension vector and an id. Everything below is done without reading a single
word of content.

## What ships

One recommendation core (`src/recommender.py`, **numpy only** at inference) and
one set of artifacts, behind three self-sufficient deployments — none calls
another:

| Solution | Serving | Artifacts from | Latency |
|---|---|---|---|
| **Azure** | HTTP Function, serverless, no dedicated API layer | Blob Storage | 0.2 s warm, ~7.5 s cold start |
| **Hugging Face** | Streamlit Space (Docker SDK), model embedded | HF Hub model repo | ~2 min first boot (253 MB) |
| **Local** | Streamlit app, in-process | folder on disk | instant, **no network** |

`GET/POST /api/recommend` accepts `user_id`, `n`, `method`, `region`,
`fresh_only` and `history`, and returns five article ids. The service is
**stateless**: a reader registered a second ago is served by passing their
reading history in the request.

## Measured results

Temporal **60/20/20** split on the click timestamp. Settings are tuned on the
validation period; the test period is measured once.

| Configuration | HitRate@5 | Coverage | Personalisation |
|---|---|---|---|
| popularity, 1 h window | **0.2525** | 0.003 % | 4 % |
| **mix — 4 popular + 1 content** (served) | **0.2500** | 0.116 % | 22 % |
| ALS (24 h, 16 factors) | 0.0415 | 0.015 % | 95 % |
| SVD (binary + 4 sampled negatives) | 0.0220 | 0.010 % | 56 % |
| content (6 h candidate pool) | 0.0200 | **0.268 %** | **96 %** |

Reference values live in `models/baseline_metrics.json` and are reproduced by
`python -m src.evaluate --split test`.

**The main finding is not about the model.** Counting clicks over one hour
instead of the whole history multiplies precision by **42**, without changing a
line of algorithm (`models/freshness_sweep.json`). The production strategy gives
one slot in five to content: it costs 1 % of precision and multiplies catalogue
coverage by 38 — the trade-off that a single-metric comparison would have hidden.

**A leaky evaluation flatters by 5.8×.** Trained on all clicks and measured
leave-last-out over the same data, ALS reports 0.2415 instead of 0.0415
(`python scripts/mesure_fuite.py`). That gap is the reason for the temporal
split.

## New readers and new articles

The requirement that shaped the design — both cases are **implemented**, not
just sketched:

- **New article**: the PCA projection is serialised alongside the catalogue
  (51 KB). A new article is projected and becomes recommendable immediately,
  with no PCA refit and no retraining. Verified end to end.
- **New reader**: registration in the app, then a four-level fallback cascade
  (regional popularity ∩ freshness window → freshness → region → full history).
  No request ever returns an empty list. From the first article read, the content
  profile takes over — still without retraining.

Only the collaborative part needs retraining, and it is not what production
serves.

## Try it

```bash
# Public demo, nothing to install
open https://huggingface.co/spaces/DaryaEL/ricochet

# The Azure endpoint (function key required)
curl "https://func-ricochet-darya.azurewebsites.net/api/recommend?user_id=0&n=5&code=<KEY>"

# Run it yourself, without Azure and without rebuilding artifacts
pip install -r spaces/requirements.txt
HF_MODEL_REPO=DaryaEL/ricochet-models streamlit run spaces/app.py
```

## Engineering notes

**79 unit tests**, a quality gate that blocks publication when HitRate@5 or
Recall@5 drops more than 10 % below the versioned reference, MLflow tracking with
a model registry, and a pre-push hook that refuses a push carrying a secret or
failing tests.

Several of those guards exist because the corresponding defect **shipped
silently first** — a hardcoded artifact list that made the service answer with
all-history popularity (0.0010 instead of 0.2525), an artifact cache judged on
file size that served two different models depending on the instance, a CLI
default that built the SVD variant the study had rejected. None of them raised an
error. A service that answers is not a service that is right, and that is what
the tests and the risk assessment now record.

## Scope

Implemented: the ranking engine, the three deployments, new-article ingestion,
new-reader registration, the freshness windows, evaluation and MLOps guard rails.

Designed and documented, not built: event-driven click ingestion, a profile
store, continuous recomputation of the freshness window (today an offline job),
and an ANN index to stop scoring all 364 047 articles per request. See
`docs/architecture.md` § 4 and `docs/sequences.md`.

Security: the endpoint is public and protected by a function key — appropriate
for an MVP, to be replaced by real authentication before production.
