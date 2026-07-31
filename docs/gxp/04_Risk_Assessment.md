# Analyse de Risque (RA)

| Champ | Valeur |
|-------|--------|
| ID document | MC-RA-001 |
| Version | 0.1 |
| Statut | DRAFT — pour revue AQ |
| Système | My Content — système de recommandation d'articles |
| Date d'émission | 2026-07-20 |

> **Support assistif — à réviser et approuver par l'AQ/CSV avant usage.**

## 1. Méthodologie

Analyse de risque fonctionnelle basée sur le risque (GAMP 5). Pour chaque
fonction : **Sévérité (S)** × **Probabilité (P)** = classe de risque, puis prise
en compte de la **Détectabilité (D)** pour la priorité de test.

Échelles : S/P/D ∈ {1 Faible, 2 Moyen, 3 Élevé}. Priorité = combinaison
S×P (classe 1–3) modulée par D.

## 2. Évaluation d'impact GxP (global)

Le système **ne traite aucune donnée GxP** (patient, clinique, qualité produit)
— cf. URS-017. Il n'a **pas d'impact direct** sur la sécurité patient, l'efficacité
d'un produit de santé, ni sur l'intégrité de données réglementées.
**Impact GxP global : FAIBLE.** L'effort de test est priorisé sur la
justesse fonctionnelle, l'intégrité des artefacts et la reproductibilité.

## 3. Analyse de risque fonctionnelle

| ID risque | Fonction (FS) | Danger / défaillance | S | P | D | Classe | Maîtrise / mitigation | Test |
|-----------|---------------|----------------------|---|---|---|--------|-----------------------|------|
| R-01 | FS-006 | Recommander un article déjà lu | 2 | 2 | 2 | Moyen | Exclusion + filtrage `-inf` ; test de non-régression | OQ-04, UT `test_content_excludes_already_seen` |
| R-02 | FS-001 | Nombre d'articles renvoyés ≠ attendu | 2 | 1 | 1 | Faible | Contrat de fonction ; test de cardinalité | OQ-01, UT `test_recommend_returns_exactly_n` |
| R-03 | FS-005 | Nouvel utilisateur sans recommandation (échec cold start) | 3 | 2 | 2 | Élevé | Repli popularité systématique | OQ-05, UT `test_unknown_user_falls_back_to_popularity` |
| R-04 | FS-004 | Score collaboratif erroné (mauvais mapping id↔facteurs) | 2 | 2 | 3 | Moyen | Index explicites `cf_*` ; test de classement | OQ-06, UT `test_collaborative_ranks_by_factor_score` |
| R-05 | FS-011 | Artefacts non reproductibles / non versionnés | 2 | 2 | 2 | Moyen | `random_state` fixés ; versionnage Blob/HF Hub | IQ-03, PQ-03 |
| R-06 | FS-009 | Copies déployées du cœur de reco désynchronisées (Azure ≠ HF) | 2 | 2 | 3 | Moyen | `sync_recommender.py --check` ; test CI | UT `test_deployed_copies_in_sync` |
| R-07 | FS-015 | Entrée invalide non gérée (crash) | 1 | 2 | 1 | Faible | Validation d'entrée + code HTTP 400 | OQ-07, UT `test_invalid_method_raises` |
| R-08 | FS-010 | Latence excessive au démarrage à froid | 1 | 3 | 1 | Faible | Cache modèle ; artefacts ACP allégés | PQ-01 |
| R-09 | Modèle IA/ML | **Dérive du modèle** : baisse de pertinence dans le temps | 2 | 3 | 3 | Élevé | Suivi de métrique + ré-entraînement planifié (archi cible) | PQ-02 |
| R-10 | Modèle IA/ML | Biais / manque de diversité (effet bulle) | 2 | 2 | 3 | Moyen | Stratégie hybride ; suivi diversité/couverture (backlog) | PQ-02 |
| R-11 | FS-016 | Traitement involontaire de données sensibles | 3 | 1 | 2 | Faible | Entrées = identifiants anonymes uniquement ; revue de conception | OQ-08 |

## 4. Intégrité des données — ALCOA+

| Principe | Application au système |
|----------|------------------------|
| **A**ttribuable | Modifications de code tracées via Git (auteur, horodatage). |
| **L**isible | Artefacts et code lisibles/documentés ; formats ouverts (npy, pkl, csv). |
| **C**ontemporain | Journaux d'exécution horodatés (Application Insights côté Azure). |
| **O**riginal | Données source conservées ; artefacts régénérables depuis la source. |
| **A**ccurate (exact) | Vérifié par tests unitaires et OQ ; `random_state` fixés. |
| +Complet / Cohérent / Durable / Disponible | Versionnage Blob/HF Hub ; dépôt Git ; sauvegardes fournisseur. |

## 5. Risques résiduels

Après mitigations, les risques résiduels sont jugés **acceptables** au regard de
l'impact GxP faible. Les risques IA/ML (R-09, R-10) requièrent un **suivi en
exploitation** (monitoring de dérive) porté par l'architecture cible.
Décision d'acceptation à statuer par l'AQ.
