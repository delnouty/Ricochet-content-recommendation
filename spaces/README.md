---
title: Ricochet - Article recommendation
emoji: 🎯
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Ricochet — public demo (Hugging Face Space)

A **self-contained** solution, independent of the Azure one: the app embeds the
recommendation engine and computes the suggestions itself. The artifacts are
downloaded at start-up from an **HF Hub model repository**.

```
HF Space (Streamlit + Recommender)  ──loads──▶  HF Hub (model repository)
        computes the recommendations in place
```

The interface is **the same as the local solution's**: it comes from `ui.py`, a
copy generated from `src/app_ui.py` by `scripts/sync_recommender.py`. The two
therefore cannot drift apart, and CI checks it (`--check`).

## What the demo exposes

| Tab | Content |
|---|---|
| Recommendations | 5 strategies — the production one (4 popular over 1 h + 1 content), then content, ALS, **SVD Surprise** and hybrid for comparison; freshness filter, stars |
| Browse articles | the full catalogue, 4 sort orders, filter by rating |
| New reader | sign-up, region, initial profile |

## Two limits that come from the hosting

**Registered readers are temporary.** A Space is ephemeral: the SQLite database
lives in `/tmp`, it is lost on every restart and it is **shared between all
visitors**. The app shows this as a banner. Do not enter any personal data.

**The freshness artifacts go stale.** The pool of recent articles is frozen at
publication time. On real data it would have to be republished regularly (see
`docs/architecture.md` § 4.f); here the dataset is static, so the demonstration
stays representative.

## Publishing and updating

```bash
# 1. generate the artifacts (from the main repository)
python -m src.prepare_model --data-dir data/news-portal-user --out-dir models
python -m src.collaborative_surprise --data-dir data/news-portal-user --out-dir models

# 2. publish the artifacts to HF Hub (about 253 MB, 22 files)
pip install huggingface_hub
$env:HF_TOKEN = "hf_..."        # PowerShell; export HF_TOKEN=... under bash
python spaces/upload_artifacts.py --repo <account>/ricochet-models --models-dir models

# 3. create the Space — SDK "docker", see the note below
python -c "from huggingface_hub import HfApi; HfApi().create_repo('<account>/ricochet', repo_type='space', space_sdk='docker', exist_ok=True)"

# 4. push the Space (hf replaces huggingface-cli as of version 0.34)
hf upload <account>/ricochet spaces/ . --repo-type space --exclude "__pycache__/*"
```

**Why Docker and not Streamlit.** Hugging Face has removed `streamlit` from its
built-in SDKs: creating a Space now only accepts `gradio`, `docker` or `static`,
and an attempt with `space_sdk="streamlit"` is rejected by the API
(`Invalid option: expected one of "gradio"|"docker"|"static" at sdk`). Streamlit
apps therefore go through the Docker SDK — see the `Dockerfile` in this
directory, which follows the platform's constraints (UID 1000 user, port 7860).

Then, **before the first start-up**, set the Space variable `HF_MODEL_REPO`
(*Settings → Variables and secrets*): without it,
`model_loader.ensure_models()` raises an explicit error rather than guessing a
repository.

## Space secrets and variables

*Settings → Variables and secrets*

| Name | Type | Role |
|-----|------|------|
| `HF_MODEL_REPO` | variable | id of the model repository (e.g. `<org>/ricochet-models`) |
| `HF_TOKEN` | secret | only required if the model repository is private |
| `CLIENTS_DB` | variable | optional: path to the reader database (default `/tmp/clients.db`) |

## Testing locally, without going through the Hub

```bash
pip install -r spaces/requirements.txt
MODELS_DIR=models streamlit run spaces/app.py
```

## Files

| File | Role |
|---|---|
| `Dockerfile` | the Space image (Docker SDK: Streamlit is no longer a built-in SDK) |
| `app.py` | entry point: downloads the artifacts, then calls `ui.run()` |
| `ui.py` | **generated** — the shared interface (source: `src/app_ui.py`) |
| `recommender.py` | **generated** — the recommendation core (source: `src/recommender.py`) |
| `user_store.py` | **generated** — registered readers (source: `src/user_store.py`) |
| `model_loader.py` | downloads the artifacts from HF Hub |
| `upload_artifacts.py` | publishes the artifacts to HF Hub |

Files marked **generated** must not be edited: run
`python scripts/sync_recommender.py` after any change under `src/`.
