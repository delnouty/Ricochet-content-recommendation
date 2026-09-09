# Traceability Matrix (RTM)

| Field | Value |
|-------|--------|
| Document ID | MC-RTM-001 |
| Version | 0.2 |
| Status | DRAFT — for QA review |
| System | Ricochet — article recommendation system |
| Issue date | 2026-09-08 |
| Supersedes | Version 0.1 of 2026-07-20 |

> **Assistive supporting material — to be reviewed and approved by QA/CSV before
> use.**

Bidirectional traceability: requirement (URS) → functional specification (FS) →
risk (RA) → verification (OQ/PQ/IQ and the unit tests in `tests/`).

| URS | FS | Risk | Qualification test | Unit test (evidence) |
|-----|-----|--------|-----------------------|------------------------|
| URS-001 | FS-001, FS-015 | R-02, R-07 | OQ-01, OQ-07 | `test_recommend_returns_exactly_n`, `test_n_larger_than_catalog_is_capped`, `test_invalid_method_raises` |
| URS-002 | FS-001 | R-02 | OQ-01 | `test_recommend_returns_exactly_n` |
| URS-003 | FS-002 | — | OQ-02 | `test_content_ranks_most_similar_first` |
| URS-004 | FS-003, FS-027 | R-04, R-17 | OQ-06, OQ-15 | `test_collaborative_ranks_by_factor_score`, `test_deux_variantes_ne_s_ecrasent_pas`, `test_variante_etoiles_exige_les_etoiles` |
| URS-005 | FS-004 | — | OQ-03 | `test_hybrid_without_cf_behaves_like_content`, `test_hybrid_with_cf_excludes_seen` |
| URS-006 | FS-005 | R-03 | OQ-05 | `test_unknown_user_falls_back_to_popularity`, `test_jamais_de_liste_vide`, `test_new_user_gets_regional_popularity`, `test_unknown_region_falls_back_to_global` |
| URS-007 | FS-006 | R-01 | OQ-04 | `test_content_excludes_already_seen`, `test_popularity_fallback_excludes_seen`, `test_regional_ranking_excludes_seen_articles` |
| URS-008 | FS-007 | — | OQ-17 | `test_new_article_is_recommendable_immediately`, `test_new_article_projects_without_refitting`, `test_existing_vectors_are_untouched` |
| URS-009 | FS-008 | — | OQ-09 | (manual interface test — screenshots) |
| URS-010 | FS-009, FS-026, FS-028 | R-06 | OQ-10, IQ-01, IQ-04/05, PQ-04 | `test_deployed_copies_in_sync` |
| URS-011 | FS-010, FS-028 | R-08 | IQ-01, PQ-01 | — |
| URS-012 | FS-011, FS-012, FS-024 | R-05, R-13 | IQ-03, OQ-12 | `test_meme_taille_mais_blob_plus_recent`, `test_blob_sans_date` |
| URS-013 | FS-011 | R-05 | PQ-03 | `test_projection_matches_fitted_pca`, `test_projection_artifacts_written` |
| URS-014 | FS-012 | — | IQ-02 | — |
| URS-015 | FS-013 | R-16 | PQ-02, PQ-06 | — |
| URS-016 | FS-014 | R-09, R-10 | PQ-02 | — |
| URS-017 | FS-016 | R-11 | OQ-08 | — |
| **URS-018** | FS-020, FS-021 | R-14 | OQ-13 | `test_identifiant_hors_catalogue_injecte_apres_chargement`, `test_historique_hors_catalogue_filtre_au_chargement` |
| **URS-019** | FS-005, FS-017, FS-018, FS-019 | R-12 | OQ-11, OQ-16, PQ-07 | `test_toutes_les_strategies_respectent_le_vivier`, `test_mix_reserve_une_place_au_contenu`, `test_fresh_only_desactivable`, `test_classement_par_popularite_dans_la_fenetre` |
| **URS-020** | FS-023, FS-024 | R-12, R-13 | OQ-12, PQ-07 | `test_meme_taille_mais_blob_plus_recent`, `test_tolerance_d_une_seconde` |
| **URS-021** | FS-025 | R-15 | OQ-14 | — |
| **URS-022** | FS-022 | — | OQ-13 | (manual verification: the ephemerality banner, persistence after a restart) |

## Coverage check

- Every URS traces to ≥ 1 FS **and** ≥ 1 verification. ✔
- Every FS traces to ≥ 1 URS. ✔
- **High**-class risks: R-03, R-09, R-12, R-13, R-16.
  - R-03, R-12, R-13: covered by automated unit tests. ✔
  - R-09 (model drift) and R-16 (biased evaluation) are **not coverable by a unit
    test**: they concern the measurement protocol and behaviour over time. They
    are covered by PQ-02 and by the non-regression guard (FS-025). For QA to
    rule on.
- Cells marked "—": no automated unit test; verification through IQ/OQ/PQ or a
  documented review.

## Revision history

| Version | Date | Changes | Reason |
|---------|------|---------------|-------|
| 0.1 | 2026-07-20 | Initial issue (URS-001 to URS-017). | — |
| 0.2 | 2026-09-08 | Added rows URS-018 to URS-022. Linked FS-017 to FS-028 and risks R-12 to R-17. URS-008 traced to OQ-17 (a dedicated case) instead of OQ-02. Broadened the unit-test evidence for URS-001, 004, 006, 007, 012 and 013 to the tests added since. | Alignment with FS v0.2 and URS v0.2; v0.1 traced no verification at all for freshness, reader sign-up or the non-regression guard. |
