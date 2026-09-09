# Operational Qualification protocol (OQ)

| Field | Value |
|-------|--------|
| Document ID | MC-OQ-001 |
| Version | 0.2 |
| Status | DRAFT — for execution after approval |
| System | Ricochet — article recommendation system |
| Issue date | 2026-09-08 |
| Supersedes | Version 0.1 of 2026-07-20 |

> **Assistive supporting material — to be reviewed and approved by QA/CSV before
> execution.**

## 1. Purpose

To demonstrate that the system behaves in accordance with the FS across all its
functions, in the qualified environment (IQ declared conforming).

## 2. Test strategy

The functions of the recommendation core are verified by an **automated unit test
suite** (`tests/`, on controlled synthetic artifacts), executed as OQ evidence
and complemented by interface and end-to-end tests.

Reference execution: `python -m pytest tests/ -q` → **expected result: 87 tests,
all PASS**.

Cases OQ-11 to OQ-16 concern functions absent from version 0.1 of the FS. Three
of them (OQ-11, OQ-12, OQ-14) verify mechanisms whose failure **raises no
error**: their acceptance criterion is therefore a **comparison**, not the
absence of an exception (see RA § 6).

## 3. Qualification cases

| ID | FS/URS ref. | Test case | Steps | Acceptance criterion | P/F | Evidence |
|----|-------------|-------------|--------|-----------------------|-----|--------|
| OQ-01 | FS-001 / URS-001,002 | Result cardinality | Call `recommend(user, n)` | Exactly `n` ids (or fewer if the catalogue is exhausted), never more | | `test_recommend_returns_exactly_n`, `test_n_larger_than_catalog_is_capped` |
| OQ-02 | FS-002 / URS-003 | Content-based relevance | A user who has read one article | The most similar article comes first | | `test_content_ranks_most_similar_first` |
| OQ-03 | FS-004 / URS-005 | Hybrid strategy | Call `method="hybrid"` with and without CF | A coherent result, with seen articles excluded | | `test_hybrid_without_cf_behaves_like_content`, `test_hybrid_with_cf_excludes_seen` |
| OQ-04 | FS-006 / URS-007 | Exclusion of read articles | A user with a history | No already-read article in the result | | `test_content_excludes_already_seen`, `test_popularity_fallback_excludes_seen` |
| OQ-05 | FS-005 / URS-006 | Cold start and fallback cascade | An unknown `user_id`, with and without a region; a reader who has read the whole pool | A non-empty list in every case; the order is the popularity of the region crossed with freshness where available, otherwise the next level of the cascade | | `test_unknown_user_falls_back_to_popularity`, `test_new_user_gets_regional_popularity`, `test_region_croisee_avec_la_fraicheur`, `test_jamais_de_liste_vide` |
| OQ-06 | FS-003 / URS-004 | Collaborative ranking | A user known to the CF model | The article with the best latent score comes first | | `test_collaborative_ranks_by_factor_score` |
| OQ-07 | FS-015 / URS-001 | Input robustness | An invalid `method` | An explicit error (`ValueError` / HTTP 400), no crash | | `test_invalid_method_raises` |
| OQ-08 | FS-016 / URS-017 | Absence of sensitive data | Review of inputs and outputs | Only anonymous numeric identifiers are handled | | documented review |
| OQ-09 | FS-008 / URS-009 | Demonstration interface | Start the app, pick a `user_id`, click "Recommend" | 5 articles displayed with no error | | screenshot |
| OQ-10 | FS-009 / URS-010 | Serverless endpoint (Azure) | `GET /api/recommend` with `user_id` and `n=5`, without specifying `method` | HTTP 200; JSON containing `"method": "mix"` and `recommendations` of size 5 | | captured response |
| OQ-11 | FS-018, FS-019 / URS-019 | The freshness window is applied | Write a known pool, call all five strategies; then uncheck `fresh_only` | No strategy leaves the pool; disabling it visibly widens the ranking; a window that is too short is widened and the effective duration reported in `recent_window.json` | | `test_toutes_les_strategies_respectent_le_vivier`, `test_fresh_only_desactivable`, `test_elargissement_automatique`, `test_ancre_ignore_les_horodatages_aberrants` |
| OQ-12 | FS-023, FS-024 / URS-020 | A replaced artifact is picked up | Replace a freshness artifact in Blob **without restarting**; then replace a heavy artifact **of identical size** and redeploy; repeat the same call 15 times | Freshness: the response follows the new file with no restart. Heavy artifact: a **single** distinct response across 15 calls (no instance still serving the old model) | | `test_meme_taille_mais_blob_plus_recent`, `test_meme_taille_et_cache_a_jour`, captures of the 15 calls |
| OQ-13 | FS-020, FS-021 / URS-018 | Registering a reader | Register a reader (name, optional region), ask for recommendations, mark an article as read, ask again | Recommendations obtained immediately; identifier ≥ 1 000 000; the list changes after the read is recorded; an empty or already-taken name refused with a message | | `test_identifiant_hors_catalogue_injecte_apres_chargement`, `test_historique_hors_catalogue_filtre_au_chargement`, screenshot |
| OQ-14 | FS-025 / URS-021 | Non-regression guard | Submit to `check_metrics.py` a metrics file degraded beyond the tolerance, then a conforming one | A **non-zero** exit (publication blocked) in the first case, zero in the second; the report names the offending metric | | execution log of both calls |
| OQ-15 | FS-027 / URS-004 | The SVD rating variant | Build both variants within the same measurement; request the "stars" variant with no stars artifact | The two variants give distinct rankings (neither overwrites the other); the absence of the stars artifact produces an explicit error | | `test_deux_variantes_ne_s_ecrasent_pas`, `test_variante_etoiles_exige_les_etoiles`, `test_le_recommender_d_origine_reste_intact` |
| OQ-16 | FS-017 / URS-019 | Composition of the production strategy | Call `method="mix"`, `n=5`, on a known pool | The first four slots are recent popularity, in order; the fifth comes from content and is absent from the first four | | `test_mix_reserve_une_place_au_contenu` |
| OQ-17 | FS-007 / URS-008 | Publishing a new article | Add articles from their embeddings, without re-fitting the PCA | Identifiers assigned after the end of the catalogue; existing vectors unchanged; the article recommendable immediately through the content route | | `test_new_article_is_recommendable_immediately`, `test_existing_vectors_are_untouched`, `test_new_article_projects_without_refitting` |

## 4. Deviations

| Deviation ID | Case | Description | Criticality | Resolution | Status |
|----------|-----|-------------|-----------|------------|--------|
| | | | | | |

## 5. OQ conclusion

| Role | Name | Signature | Date |
|------|-----|-----------|------|
| Executed by | | | |
| QA review | | | |
