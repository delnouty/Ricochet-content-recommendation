# Analyse de Risque (RA)

| Champ | Valeur |
|-------|--------|
| ID document | MC-RA-001 |
| Version | 0.2 |
| Statut | DRAFT — pour revue AQ |
| Système | My Content — système de recommandation d'articles |
| Date d'émission | 2026-09-08 |
| Remplace | Version 0.1 du 2026-07-20 |

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
| R-04 | FS-003 | Score collaboratif erroné (mauvais mapping id↔facteurs) | 2 | 2 | 3 | Moyen | Index explicites `cf_*` ; test de classement | OQ-06, UT `test_collaborative_ranks_by_factor_score` |
| R-05 | FS-011 | Artefacts non reproductibles / non versionnés | 2 | 2 | 2 | Moyen | `random_state` fixés ; versionnage Blob/HF Hub | IQ-03, PQ-03 |
| R-06 | FS-009 | Copies déployées du cœur de reco désynchronisées (Azure ≠ HF) | 2 | 2 | 3 | Moyen | `sync_recommender.py --check` ; test CI | UT `test_deployed_copies_in_sync` |
| R-07 | FS-015 | Entrée invalide non gérée (crash) | 1 | 2 | 1 | Faible | Validation d'entrée + code HTTP 400 | OQ-07, UT `test_invalid_method_raises` |
| R-08 | FS-010 | Latence excessive au démarrage à froid | 1 | 3 | 1 | Faible | Cache modèle ; artefacts ACP allégés | PQ-01 |
| R-09 | Modèle IA/ML | **Dérive du modèle** : baisse de pertinence dans le temps | 2 | 3 | 3 | Élevé | Suivi de métrique + ré-entraînement planifié (archi cible) | PQ-02 |
| R-10 | Modèle IA/ML | Biais / manque de diversité (effet bulle) | 2 | 2 | 3 | Moyen | Stratégie hybride ; suivi diversité/couverture (backlog) | PQ-02 |
| R-11 | FS-016 | Traitement involontaire de données sensibles | 3 | 1 | 2 | Faible | Entrées = identifiants anonymes uniquement ; revue de conception | OQ-08 |
| R-12 | FS-018, FS-023 | **Fenêtre de fraîcheur périmée servie** : artefacts non republiés, ou lecture de binding en échec | 3 | 2 | 3 | **Élevé** | Binding relu à chaque invocation (pas de redémarrage requis) ; métadonnées de fenêtre affichées dans l'interface ; repli journalisé | OQ-11, UT `test_artefact_absent_sans_effet`, `test_elargissement_automatique` |
| R-13 | FS-024 | **Modèle erroné servi depuis un cache local** jugé valide sur la seule taille du fichier | 3 | 2 | 3 | **Élevé** | Validité jugée sur taille **et** date du blob ; remplacement d'artefact lourd suivi d'un redéploiement, pas d'un simple redémarrage | OQ-12, UT `test_meme_taille_mais_blob_plus_recent` |
| R-14 | FS-020, FS-021 | Lecteur inscrit ne recevant que de la popularité (profil non transmis au service sans état) | 2 | 2 | 2 | Moyen | Paramètre `history` dans la requête ; injection des historiques inscrits dans le moteur en mémoire | OQ-13, UT `test_identifiant_hors_catalogue_injecte_apres_chargement` |
| R-15 | FS-025 | Publication d'une version de modèle dégradée | 2 | 2 | 3 | Moyen | Porte de qualité contre référence versionnée ; référence promue délibérément | OQ-14 |
| R-16 | FS-013 | **Décision de conception fondée sur une évaluation biaisée** | 3 | 2 | 3 | **Élevé** | Découpage temporel 60/20/20 ; réglages choisis sur la validation, test intact ; balayage **croisé** des réglages | PQ-02 |
| R-17 | FS-027 | Variante de modèle inadéquate livrée par défaut | 1 | 2 | 3 | Faible | Valeurs par défaut alignées sur la variante retenue ; variante rejetée accessible seulement par drapeau explicite | OQ-15, UT `test_variante_etoiles_exige_les_etoiles` |

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

Risque résiduel signalé pour R-12 : la fenêtre de fraîcheur est aujourd'hui
recalculée par le traitement **hors-ligne**, non par un flux continu. Une
interruption du traitement périodique n'est pas détectée par le service lui-même ;
seule la date portée par `recent_window.json` permet de le constater.

## 6. Défaillances observées — justification des risques R-12, R-13 et R-16

Trois des risques ajoutés en version 0.2 ne sont pas hypothétiques : ils ont été
**observés puis corrigés** pendant le développement. Ils sont documentés ici parce
qu'un risque constaté vaut mieux qu'un risque supposé, et que leur détectabilité
mesurée (D = 3, faible) est le point important.

| Risque | Ce qui s'est produit | Comment cela a été détecté |
|--------|----------------------|----------------------------|
| R-12 | Un chargeur d'artefacts suivant une liste figée ne récupérait pas les fichiers de fraîcheur ajoutés après lui. Le service répondait **sans aucune erreur**, en servant la popularité de tout l'historique : HitRate@5 de 0,0010 au lieu de 0,2525. | Comparaison de la réponse du service déployé avec celle du service local (étape imposée avant tout déploiement). |
| R-13 | Un modèle SVD reconstruit avec une autre définition de note occupait **exactement la même taille** ; les instances au cache survivant ne l'ont jamais retéléchargé. Le service a servi deux modèles différents selon l'instance sollicitée — 6 réponses sur 10 avec le nouveau, 4 avec l'ancien. | Répétition du même appel après remplacement de l'artefact. |
| R-16 | Une évaluation *leave-last-out* sur données complètes, le modèle ayant vu le clic à prédire, donnait 0,2415 pour l'ALS contre **0,0415** en découpage temporel — un facteur 5,8 de justesse imaginaire. Deux réglages optimisés séparément, une fois combinés, se sont révélés être la **pire** des configurations. | Mise en place du découpage temporel, puis balayage croisé des réglages. |

Enseignement commun aux trois : **un système qui répond n'est pas un système
correct.** Aucune de ces défaillances ne levait d'erreur. C'est ce qui justifie la
cote de détectabilité D = 3 et le recours à des contrôles comparatifs plutôt qu'à
la seule absence d'exception.
