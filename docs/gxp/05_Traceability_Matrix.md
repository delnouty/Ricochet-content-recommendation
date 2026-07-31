# Matrice de Traçabilité (RTM)

| Champ | Valeur |
|-------|--------|
| ID document | MC-RTM-001 |
| Version | 0.1 |
| Statut | DRAFT — pour revue AQ |
| Système | My Content — système de recommandation d'articles |
| Date d'émission | 2026-07-20 |

> **Support assistif — à réviser et approuver par l'AQ/CSV avant usage.**

Traçabilité bidirectionnelle : Exigence (URS) → Spéc. fonctionnelle (FS) →
Risque (RA) → Vérification (OQ/PQ et tests unitaires `tests/`).

| URS | FS | Risque | Test de qualification | Test unitaire (preuve) |
|-----|-----|--------|-----------------------|------------------------|
| URS-001 | FS-001, FS-015 | R-02 | OQ-01 | `test_recommend_returns_exactly_n` |
| URS-002 | FS-001 | R-02 | OQ-01 | `test_recommend_returns_exactly_n` |
| URS-003 | FS-002 | — | OQ-02 | `test_content_ranks_most_similar_first` |
| URS-004 | FS-003 | R-04 | OQ-06 | `test_collaborative_ranks_by_factor_score` |
| URS-005 | FS-004 | — | OQ-03 | `test_hybrid_without_cf_behaves_like_content`, `test_hybrid_with_cf_excludes_seen` |
| URS-006 | FS-005 | R-03 | OQ-05 | `test_unknown_user_falls_back_to_popularity`, `test_collaborative_unknown_user_falls_back` |
| URS-007 | FS-006 | R-01 | OQ-04 | `test_content_excludes_already_seen`, `test_popularity_fallback_excludes_seen` |
| URS-008 | FS-007 | — | OQ-02 | (couvert par la voie content-based) |
| URS-009 | FS-008 | — | OQ-09 | (test manuel interface) |
| URS-010 | FS-009 | R-06 | OQ-10, IQ-04/05 | `test_deployed_copies_in_sync` |
| URS-011 | FS-010 | R-08 | PQ-01 | — |
| URS-012 | FS-011 | R-05 | IQ-03 | — |
| URS-013 | FS-011 | R-05 | PQ-03 | — |
| URS-014 | FS-012 | — | IQ-02 | — |
| URS-015 | FS-013 | — | PQ-02 | — |
| URS-016 | FS-014 | R-09, R-10 | PQ-02 | — |
| URS-017 | FS-016 | R-11 | OQ-08 | — |

## Contrôle de couverture

- Chaque URS est tracée vers ≥ 1 FS et ≥ 1 vérification. ✔
- Chaque risque de classe **Élevé** (R-03, R-09) est couvert par un test. ✔
- Cellules « — » : pas de test unitaire automatisé (vérification par IQ/OQ/PQ
  ou revue) ; à confirmer lors de l'exécution.
