# Risk Assessment (RA)

| Field | Value |
|-------|--------|
| Document ID | MC-RA-001 |
| Version | 0.2 |
| Status | DRAFT — for QA review |
| System | Ricochet — article recommendation system |
| Issue date | 2026-09-08 |
| Supersedes | Version 0.1 of 2026-07-20 |

> **Assistive supporting material — to be reviewed and approved by QA/CSV before
> use.**

## 1. Methodology

A risk-based functional risk assessment (GAMP 5). For each function:
**Severity (S)** × **Probability (P)** = risk class, then **Detectability (D)**
is taken into account for test priority.

Scales: S/P/D ∈ {1 low, 2 medium, 3 high}. Priority = the S×P combination
(class 1–3) modulated by D.

## 2. GxP impact assessment (overall)

The system **processes no GxP data** (patient, clinical, product quality) — see
URS-017. It has **no direct impact** on patient safety, on the efficacy of a
health product, or on the integrity of regulated data. **Overall GxP impact:
LOW.** Test effort is prioritised on functional accuracy, artifact integrity and
reproducibility.

## 3. Functional risk assessment

| Risk ID | Function (FS) | Hazard / failure | S | P | D | Class | Control / mitigation | Test |
|-----------|---------------|----------------------|---|---|---|--------|-----------------------|------|
| R-01 | FS-006 | Recommending an already-read article | 2 | 2 | 2 | Medium | Exclusion plus `-inf` filtering; non-regression test | OQ-04, UT `test_content_excludes_already_seen` |
| R-02 | FS-001 | Number of articles returned ≠ expected | 2 | 1 | 1 | Low | Function contract; cardinality test | OQ-01, UT `test_recommend_returns_exactly_n` |
| R-03 | FS-005 | A new user left with no recommendation (cold-start failure) | 3 | 2 | 2 | High | Systematic popularity fallback | OQ-05, UT `test_unknown_user_falls_back_to_popularity` |
| R-04 | FS-003 | Wrong collaborative score (bad id ↔ factor mapping) | 2 | 2 | 3 | Medium | Explicit `cf_*` indices; ranking test | OQ-06, UT `test_collaborative_ranks_by_factor_score` |
| R-05 | FS-011 | Artifacts not reproducible or not versioned | 2 | 2 | 2 | Medium | Fixed `random_state`; versioning in Blob / HF Hub | IQ-03, PQ-03 |
| R-06 | FS-009 | Deployed copies of the core out of step (Azure ≠ HF) | 2 | 2 | 3 | Medium | `sync_recommender.py --check`; CI test | UT `test_deployed_copies_in_sync` |
| R-07 | FS-015 | Invalid input unhandled (crash) | 1 | 2 | 1 | Low | Input validation plus HTTP 400 | OQ-07, UT `test_invalid_method_raises` |
| R-08 | FS-010 | Excessive latency on a cold start | 1 | 3 | 1 | Low | Model cache; slimmed PCA artifacts | PQ-01 |
| R-09 | AI/ML model | **Model drift**: relevance falling over time | 2 | 3 | 3 | High | Metric monitoring plus scheduled re-training (target architecture) | PQ-02 |
| R-10 | AI/ML model | Bias / lack of diversity (filter bubble) | 2 | 2 | 3 | Medium | Hybrid strategy; diversity and coverage monitoring (backlog) | PQ-02 |
| R-11 | FS-016 | Inadvertent processing of sensitive data | 3 | 1 | 2 | Low | Inputs are anonymous identifiers only; design review | OQ-08 |
| R-12 | FS-018, FS-023 | **A stale freshness window served**: artifacts not republished, or a failed binding read | 3 | 2 | 3 | **High** | Binding re-read on every invocation (no restart required); window metadata displayed in the interface; fallback logged | OQ-11, UT `test_artefact_absent_sans_effet`, `test_elargissement_automatique` |
| R-13 | FS-024 | **The wrong model served from a local cache** judged valid on file size alone | 3 | 2 | 3 | **High** | Validity judged on the size **and** the date of the blob; replacing a heavy artifact is followed by a redeployment, not merely a restart | OQ-12, UT `test_meme_taille_mais_blob_plus_recent` |
| R-14 | FS-020, FS-021 | A registered reader given popularity only (profile not passed to the stateless service) | 2 | 2 | 2 | Medium | The `history` request parameter; injection of registered histories into the in-memory engine | OQ-13, UT `test_identifiant_hors_catalogue_injecte_apres_chargement` |
| R-15 | FS-025 | A degraded model version published | 2 | 2 | 3 | Medium | Quality gate against a versioned reference; the reference is promoted deliberately | OQ-14 |
| R-16 | FS-013 | **A design decision based on a biased evaluation** | 3 | 2 | 3 | **High** | Temporal 60/20/20 split; settings chosen on validation, test left untouched; **joint** sweep of the settings | PQ-02 |
| R-17 | FS-027 | An unsuitable model variant shipped by default | 1 | 2 | 3 | Low | Defaults aligned with the retained variant; the rejected variant reachable only through an explicit flag | OQ-15, UT `test_variante_etoiles_exige_les_etoiles` |

## 4. Data integrity — ALCOA+

| Principle | Application to this system |
|----------|------------------------|
| **A**ttributable | Code changes traced through Git (author, timestamp). |
| **L**egible | Artifacts and code readable and documented; open formats (npy, pkl, csv). |
| **C**ontemporaneous | Timestamped execution logs (Application Insights on the Azure side). |
| **O**riginal | Source data retained; artifacts regenerable from the source. |
| **A**ccurate | Verified by unit tests and the OQ; `random_state` fixed. |
| + Complete / Consistent / Enduring / Available | Versioning in Blob and HF Hub; Git repository; supplier backups. |

## 5. Residual risks

After mitigation, the residual risks are judged **acceptable** in view of the low
GxP impact. The AI/ML risks (R-09, R-10) require **monitoring in operation**
(drift monitoring), carried by the target architecture. The acceptance decision
is for QA to rule on.

One residual risk is flagged for R-12: the freshness window is currently
recomputed by the **offline** job, not by a continuous stream. An interruption of
that periodic job is not detected by the service itself; only the date carried by
`recent_window.json` makes it visible.

## 6. Observed failures — the justification for risks R-12, R-13 and R-16

Three of the risks added in version 0.2 are not hypothetical: they were
**observed and then corrected** during development. They are documented here
because an observed risk is worth more than a supposed one, and because their
measured detectability (D = 3, low) is the important point.

| Risk | What happened | How it was detected |
|--------|----------------------|----------------------------|
| R-12 | An artifact loader following a frozen list did not fetch the freshness files added after it. The service answered **with no error at all**, serving popularity over the whole history: a HitRate@5 of 0.0010 instead of 0.2525. | Comparing the deployed service's response with the local service's (a step mandated before any deployment). |
| R-13 | An SVD model rebuilt with a different rating definition occupied **exactly the same size**; instances whose cache had survived never downloaded it again. The service served two different models depending on which instance was hit — 6 responses out of 10 with the new one, 4 with the old. | Repeating the same call after the artifact had been replaced. |
| R-16 | A *leave-last-out* evaluation on complete data, with the model having already seen the click to be predicted, gave 0.2415 for ALS against **0.0415** under a temporal split — a factor of 5.8 of imaginary accuracy. Two settings optimised separately turned out, once combined, to be the **worst** of the configurations. | Introducing the temporal split, then sweeping the settings jointly. |

The lesson common to all three: **a system that answers is not a system that is
correct.** None of these failures raised an error. That is what justifies the
detectability rating of D = 3, and the use of comparative checks rather than the
mere absence of an exception.
