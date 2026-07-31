# Protocole de Qualification Opérationnelle (OQ)

| Champ | Valeur |
|-------|--------|
| ID document | MC-OQ-001 |
| Version | 0.1 |
| Statut | DRAFT — pour exécution après approbation |
| Système | My Content — système de recommandation d'articles |
| Date d'émission | 2026-07-20 |

> **Support assistif — à réviser et approuver par l'AQ/CSV avant exécution.**

## 1. Objet

Démontrer que le système fonctionne conformément à la FS sur l'ensemble des
fonctions, dans l'environnement qualifié (IQ prononcée conforme).

## 2. Stratégie de test

Les fonctions du cœur de reco sont vérifiées par une **suite de tests unitaires
automatisée** (`tests/`, sur artefacts synthétiques maîtrisés), exécutée comme
preuve OQ, complétée par des tests d'interface / de bout en bout.

Exécution de référence : `python -m pytest tests/ -q` → **résultat attendu :
tous PASS**.

## 3. Cas de qualification

| ID | Réf. FS/URS | Cas de test | Étapes | Critère d'acceptation | P/F | Preuve |
|----|-------------|-------------|--------|-----------------------|-----|--------|
| OQ-01 | FS-001 / URS-001,002 | Cardinalité du résultat | Appeler `recommend(user, n)` | Exactement `n` id (ou moins si catalogue épuisé), jamais plus | | `test_recommend_returns_exactly_n`, `test_n_larger_than_catalog_is_capped` |
| OQ-02 | FS-002 / URS-003 | Pertinence content-based | Utilisateur ayant lu un article | Le plus similaire arrive en tête | | `test_content_ranks_most_similar_first` |
| OQ-03 | FS-004 / URS-005 | Stratégie hybride | Appeler `method="hybrid"` avec/sans CF | Résultat cohérent, articles vus exclus | | `test_hybrid_without_cf_behaves_like_content`, `test_hybrid_with_cf_excludes_seen` |
| OQ-04 | FS-006 / URS-007 | Exclusion des articles lus | Utilisateur avec historique | Aucun article déjà lu dans le résultat | | `test_content_excludes_already_seen`, `test_popularity_fallback_excludes_seen` |
| OQ-05 | FS-005 / URS-006 | Cold start | `user_id` inconnu | Retour = articles populaires, dans l'ordre | | `test_unknown_user_falls_back_to_popularity` |
| OQ-06 | FS-003 / URS-004 | Classement collaboratif | Utilisateur connu du modèle CF | Article de meilleur score latent en tête | | `test_collaborative_ranks_by_factor_score` |
| OQ-07 | FS-015 / URS-001 | Robustesse entrée | `method` invalide | Erreur explicite (`ValueError` / HTTP 400), pas de crash | | `test_invalid_method_raises` |
| OQ-08 | FS-016 / URS-017 | Absence de données sensibles | Revue des entrées/sorties | Seuls des identifiants numériques anonymes sont manipulés | | revue documentée |
| OQ-09 | FS-008 / URS-009 | Interface de démonstration | Lancer l'app, choisir un `user_id`, cliquer « Recommander » | 5 articles affichés sans erreur | | capture d'écran |
| OQ-10 | FS-009 / URS-010 | Endpoint serverless (Azure) | `GET /api/recommend?user_id=..&n=5` | HTTP 200 + JSON `recommendations` de taille 5 | | capture réponse |

## 4. Écarts

| ID écart | Cas | Description | Criticité | Résolution | Statut |
|----------|-----|-------------|-----------|------------|--------|
| | | | | | |

## 5. Conclusion OQ

| Rôle | Nom | Signature | Date |
|------|-----|-----------|------|
| Exécutant | | | |
| Revue AQ | | | |
