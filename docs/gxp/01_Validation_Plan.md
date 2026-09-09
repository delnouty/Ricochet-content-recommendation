# Validation Plan (VP)

| Field | Value |
|-------|--------|
| Document ID | MC-VAL-001 |
| Version | 0.2 |
| Status | DRAFT — for QA review |
| System | Ricochet — article recommendation system |
| Issue date | 2026-07-20 |
| Author | Technical team (CTO) |

> **Assistive supporting material — to be reviewed and approved by QA/CSV before
> use.**

## Approval table

| Role | Name | Signature | Date |
|------|-----|-----------|------|
| Author (system owner) | | | |
| Technical review | | | |
| Quality / QA review | | | |
| Approval | | | |

## 1. Purpose

To define the strategy, scope, responsibilities and deliverables for validating
the Ricochet software, following a risk-based GAMP 5 approach.

## 2. Scope

**In scope**: the recommendation engine (`src/recommender.py`), the artifact
preparation pipeline (`src/prepare_model.py`), the Azure solution
(`azure_function/`, `app/`), the Hugging Face solution (`spaces/`), and the model
artifacts and their management.

**Out of scope**: managed infrastructure (Azure services, Hugging Face, Git
hosting), covered by the suppliers' service agreements (GAMP category 1); and the
construction of the source dataset (Globo.com), treated as input data.

## 3. System description

A recommendation system returning a selection of articles (5 by default) for a
reader identifier, from **five strategies**: content, collaborative ALS,
collaborative SVD, hybrid, and the **mixed strategy served in production** (four
recent-popularity slots and one content slot). A reader with no usable profile is
handled by a **fallback cascade**, running from the popularity of their region
crossed with the freshness window down to popularity over the whole history.

Deployed as **three independent solutions**: serverless Azure Functions, a
Hugging Face Space (Docker SDK), and local execution with no network.

See `docs/architecture.md` (static view) and `docs/sequences.md` (sequence
diagrams of the three solutions).

## 4. Validation approach (risk-based)

- GAMP classification (see the index): the application core is category 5.
- Validation effort modulated by the **risk assessment** (MC-RA-001).
- V-model: URS → FS → design/code → IQ → OQ → PQ.
- Reuse of the **automated unit tests** (`tests/`) as verification evidence
  (leveraging supplier/developer testing).

## 5. Validation deliverables

VP, URS, FS, RA, RTM, the IQ/OQ/PQ protocols, and the VSR (see the MC-VAL
index).

## 6. Roles and responsibilities

| Role | Responsibility |
|------|----------------|
| System owner / CTO | Steering, technical accuracy, test execution |
| Development | Implementation, unit tests, configuration management |
| QA / CSV | Review, approval, methodological compliance |
| Business owner (CEO) | Approval of the user requirements |

## 7. Configuration and change management

- Code under version control (Git + GitHub); model artifacts versioned (Blob /
  HF Hub).
- The recommendation core is kept as a single source (`src/`) and synchronised to
  the deployed copies by `scripts/sync_recommender.py` (checked with `--check`).
- Any significant change triggers an impact assessment and targeted
  re-validation.

## 8. Acceptance criteria

Validation is declared if: every critical OQ/PQ case is **PASS**, deviations are
documented and closed (or justified), and the RTM demonstrates complete URS →
test coverage. Formalised in the VSR (MC-VSR-001).

## 9. Deviation management

Any non-conforming result is recorded as a deviation (description, criticality,
root-cause analysis, corrective action, status) and ruled on before the VSR is
issued.

## 10. Maintaining the validated state

Periodic review, incident management, re-assessment on change (a new model, a
new dependency version), and for AI/ML specifically: monitoring of **model
drift** and controlled re-training (see MC-RA-001).
