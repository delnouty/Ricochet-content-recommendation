# Performance Qualification protocol (PQ)

| Field | Value |
|-------|--------|
| Document ID | MC-PQ-001 |
| Version | 0.2 |
| Status | DRAFT — for execution after approval |
| System | Ricochet — article recommendation system |
| Issue date | 2026-09-08 |
| Supersedes | Version 0.1 of 2026-07-20 |

> **Assistive supporting material — to be reviewed and approved by QA/CSV before
> execution.**

## 1. Purpose

To demonstrate that the system, under conditions representative of real use (the
real Globo.com data, the production environment), meets the performance and
quality requirements over time.

## 2. Qualification cases

| ID | URS ref. | Case | Method | Acceptance criterion | P/F | Evidence |
|----|----------|-----|---------|-----------------------|-----|--------|
| PQ-01 | URS-011 | Response time | Measure latency over N representative requests (excluding cold starts) | Median latency < 2 s; the cold start measured and documented separately | | readings |
| PQ-02 | URS-015, URS-016 | Model quality | `python -m src.evaluate --split test`: a **temporal 60/20/20** split, settings frozen on validation, a single measurement on the test period. Four metrics: HitRate@5, Recall@5, coverage, personalisation | All four metrics produced and recorded in `models/baseline_metrics.json`; the retained strategy is the one with the best accuracy / coverage trade-off, not the best accuracy alone | | `models/baseline_metrics.json`, execution log, notebook 07 |
| PQ-03 | URS-012, URS-013 | Reproducibility | Regenerate the artifacts (`prepare_model.py`, `collaborative_surprise.py`) with the same data and parameters | Identical artifacts / stable metrics (`random_state` fixed) | | compared logs |
| PQ-04 | URS-010 | Equivalence of the three solutions | The same `user_id`, `method` and `n` on the Azure, Hugging Face and local solutions | **Identical** recommendations (same artifacts, same core generated from `src/`) | | compared captures of all three |
| PQ-05 | URS-016 | Drift monitoring (put in place) | Check the monitoring arrangement (metrics, logs) foreseen by the target architecture | A monitoring arrangement and alert thresholds are defined | | document / screenshot |
| **PQ-06** | URS-015 | **Absence of evaluation bias** | Compare the temporal-split measurement with a *leave-last-out* measurement on complete data (`python scripts/mesure_fuite.py`) | The gap is measured and documented; only the temporal-split value is retained as the result | | execution log |
| **PQ-07** | URS-019, URS-020 | **Effect and currency of the freshness window** | `python scripts/sweep_fraicheur.py`; then read the date carried by `recent_window.json` in production | The accuracy gap between the production window and the full history is measured and documented; the window being served is no older than the planned republication cadence | | `models/freshness_sweep.json`, capture of the system banner |

## 3. Monitoring in operation (maintaining the validated state)

- Monitoring: availability, latency, error rate (Application Insights / HF logs).
- Business indicator: click-through rate (CTR) on the recommended articles.
- Periodic re-assessment of model quality; **controlled re-training** in the
  event of drift, which triggers a targeted re-validation (see VP § 10).

## 4. Deviations

| Deviation ID | Case | Description | Criticality | Resolution | Status |
|----------|-----|-------------|-----------|------------|--------|
| | | | | | |

## 5. PQ conclusion

| Role | Name | Signature | Date |
|------|-----|-----------|------|
| Executed by | | | |
| QA review | | | |
