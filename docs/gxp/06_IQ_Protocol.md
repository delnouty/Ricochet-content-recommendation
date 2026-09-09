# Installation Qualification protocol (IQ)

| Field | Value |
|-------|--------|
| Document ID | MC-IQ-001 |
| Version | 0.2 |
| Status | DRAFT — for execution after approval |
| System | Ricochet — article recommendation system |
| Issue date | 2026-09-08 |
| Supersedes | Version 0.1 of 2026-07-20 |

> **Assistive supporting material — to be reviewed and approved by QA/CSV before
> execution.**

## 1. Purpose and prerequisites

To verify that the environment and the components are correctly installed and
configured. Prerequisites: VP, URS, FS and RA approved; the target environment
available; the model artifacts generated.

## 2. Qualification cases

| ID | Verification | Method | Acceptance criterion | Result (P/F) | Evidence | Executed by / date |
|----|--------------|---------|-----------------------|----------------|--------|----------------|
| IQ-01 | Python version | `python --version` locally; `az functionapp config show --query linuxFxVersion` for the Function | In line with **FS-028**: Python 3.13 for the Function (Flex Consumption plan), ≥ 3.11 locally | | screenshots | |
| IQ-02 | Code repository cloned and versioned | `git log -1` | An identifiable commit (hash, author, date) | | screenshot | |
| IQ-03 | Model artifacts present and named | List `models/` (or the Blob container / the HF Hub repository) | `articles_embeddings_pca.npy`, `user_clicks.pkl`, `popular_articles.npy` present (plus `cf_*` if collaborative) | | listing | |
| IQ-04 | Dependencies installed (prototyping environment) | `pip install -r requirements.txt` | Installation completes without error | | log | |
| IQ-05 | Azure solution — Function dependencies | Check the deployed `azure_function/requirements.txt` | `azure-functions`, `numpy`, `azure-storage-blob` present | | log | |
| IQ-06 | Azure solution — configuration | Check the variables (`MODELS_DIR` or `AZURE_STORAGE_CONNECTION_STRING`, `MODELS_CONTAINER`) | Variables set, and no secret exposed to the repository | | screenshot | |
| IQ-07 | HF solution — Space configuration | Check the `spaces/README.md` front matter (`sdk: docker`, `app_port: 7860`) and the `HF_MODEL_REPO` variable | Space configured with the Docker SDK — Streamlit is no longer a built-in SDK — and the variable present | | screenshot | |
| IQ-08 | Integrity of the recommendation-core copies | `python scripts/sync_recommender.py --check` | Exit code 0 (copies in step) | | log | |
| IQ-09 | Exclusion of sensitive items | Check `.gitignore`, then run `python scripts/check_secrets.py` | `data/`, artifacts, `local.settings.json` and `.env` excluded; the secret check reports nothing | | screenshot, log | |

## 3. Deviations

| Deviation ID | Case | Description | Criticality | Resolution | Status |
|----------|--------------|-------------|-----------|------------|--------|
| | | | | | |

## 4. IQ conclusion

IQ declared **conforming / non-conforming** (to be ruled on). Signatures:

| Role | Name | Signature | Date |
|------|-----|-----------|------|
| Executed by | | | |
| QA review | | | |
