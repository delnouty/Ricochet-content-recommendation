# User Requirements Specification (URS)

| Field | Value |
|-------|--------|
| Document ID | MC-URS-001 |
| Version | 0.2 |
| Status | DRAFT — for QA review |
| System | Ricochet — article recommendation system |
| Issue date | 2026-09-08 |
| Supersedes | Version 0.1 of 2026-07-20 |

> **Assistive supporting material — to be reviewed and approved by QA/CSV and by
> the business before use.**

## Approval table

| Role | Name | Signature | Date |
|------|-----|-----------|------|
| Business owner (CEO) | | | |
| System owner (CTO) | | | |
| Quality / QA review | | | |

## Conventions

- Criticality: **H** (high), **M** (medium), **L** (low).
- Type: F (functional), P (performance), D (data / integrity), R (regulatory /
  quality).

## Requirements

| ID | Type | Crit. | Requirement |
|----|------|-------|----------|
| URS-001 | F | H | For a given user identifier, the system returns a selection of recommended articles. |
| URS-002 | F | H | The number of articles returned is configurable, with a default of **5**. |
| URS-003 | F | H | The system recommends on the basis of what has already been read (a *content-based* approach). |
| URS-004 | F | M | The system exploits collective behaviour (*collaborative filtering*). |
| URS-005 | F | M | The system combines the approaches (a *hybrid* strategy) and allows the strategy to be chosen. |
| URS-006 | F | H | A user with no usable history receives a fallback recommendation (popular articles — *cold start*). |
| URS-007 | F | H | Articles the user has already read are not recommended again. |
| URS-008 | F | M | A new article can be taken into account without re-training, through its embedding. |
| URS-009 | F | M | The system is reachable through an application interface (a demonstration). |
| URS-010 | F | M | The system is deployable as **three independent solutions**: Azure serverless, a Hugging Face Space, and local execution with no network. |
| URS-011 | P | M | Recommendation response time is compatible with interactive use (target: < 2 s outside a cold start). |
| URS-012 | D | H | Model artifacts are **versioned and traceable** (integrity, reproducibility). |
| URS-013 | D | M | The model preparation pipeline is **reproducible** from the data and documented parameters. |
| URS-014 | R | M | Source code is managed under version control (Git/GitHub). |
| URS-015 | F | M | Recommendation quality is **measurable** through documented metrics covering both accuracy and the variety of what is offered (accuracy alone always points to the least personalised strategy). |
| URS-016 | R | M | The behaviour of the AI/ML model can be re-assessed over time (drift monitoring, controlled re-training). |
| URS-017 | D | M | The system processes no sensitive or regulated data (no patient or clinical data). |
| URS-018 | F | H | A **new reader** can be registered in the application and receives recommendations immediately, with no re-training of the model. |
| URS-019 | F | H | Recommendations favour **recent** articles. The length of the recency window is a documented, modifiable product parameter. |
| URS-020 | P | M | A new recency window takes effect **without a service interruption**. |
| URS-021 | D | H | A model version whose performance degrades beyond a defined threshold **cannot be published** (a non-regression guard against a versioned reference). |
| URS-022 | F | M | The reads of a registered reader are **retained** from one session to the next where the hosting allows it; where it does not, the application says so explicitly to the visitor. |

## Assumptions and constraints

- Input data: the Globo.com dataset (user ↔ article interactions), treated as
  development data.
- Hosting: managed Azure Functions and Hugging Face Spaces (free tier) services,
  plus a local execution with no network.

## Revision history

| Version | Date | Changes | Reason |
|---------|------|---------------|-------|
| 0.1 | 2026-07-20 | Initial issue. | — |
| 0.2 | 2026-09-08 | URS-010: two solutions → **three** (local execution is a solution in its own right). URS-015 reworded: quality is not assessed on accuracy alone. Added **URS-018 to URS-022**: registering a new reader, the recency window, updating without interruption, the non-regression guard, and persistence of reads. | The measurements carried out between July and September made **recency** a product need rather than an implementation detail; registering a new reader, absent from v0.1, is an explicit expectation of the assignment. |
