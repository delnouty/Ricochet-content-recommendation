# Protocole de Qualification Opérationnelle (OQ)

| Champ | Valeur |
|-------|--------|
| ID document | MC-OQ-001 |
| Version | 0.2 |
| Statut | DRAFT — pour exécution après approbation |
| Système | My Content — système de recommandation d'articles |
| Date d'émission | 2026-09-08 |
| Remplace | Version 0.1 du 2026-07-20 |

> **Support assistif — à réviser et approuver par l'AQ/CSV avant exécution.**

## 1. Objet

Démontrer que le système fonctionne conformément à la FS sur l'ensemble des
fonctions, dans l'environnement qualifié (IQ prononcée conforme).

## 2. Stratégie de test

Les fonctions du cœur de reco sont vérifiées par une **suite de tests unitaires
automatisée** (`tests/`, sur artefacts synthétiques maîtrisés), exécutée comme
preuve OQ, complétée par des tests d'interface / de bout en bout.

Exécution de référence : `python -m pytest tests/ -q` → **résultat attendu :
59 tests, tous PASS**.

Les cas OQ-11 à OQ-16 portent sur des fonctions absentes de la version 0.1 de la
FS. Trois d'entre eux (OQ-11, OQ-12, OQ-14) vérifient des mécanismes dont la
défaillance **ne lève aucune erreur** : leur critère d'acceptation est donc une
**comparaison**, et non l'absence d'exception (cf. RA § 6).

## 3. Cas de qualification

| ID | Réf. FS/URS | Cas de test | Étapes | Critère d'acceptation | P/F | Preuve |
|----|-------------|-------------|--------|-----------------------|-----|--------|
| OQ-01 | FS-001 / URS-001,002 | Cardinalité du résultat | Appeler `recommend(user, n)` | Exactement `n` id (ou moins si catalogue épuisé), jamais plus | | `test_recommend_returns_exactly_n`, `test_n_larger_than_catalog_is_capped` |
| OQ-02 | FS-002 / URS-003 | Pertinence content-based | Utilisateur ayant lu un article | Le plus similaire arrive en tête | | `test_content_ranks_most_similar_first` |
| OQ-03 | FS-004 / URS-005 | Stratégie hybride | Appeler `method="hybrid"` avec/sans CF | Résultat cohérent, articles vus exclus | | `test_hybrid_without_cf_behaves_like_content`, `test_hybrid_with_cf_excludes_seen` |
| OQ-04 | FS-006 / URS-007 | Exclusion des articles lus | Utilisateur avec historique | Aucun article déjà lu dans le résultat | | `test_content_excludes_already_seen`, `test_popularity_fallback_excludes_seen` |
| OQ-05 | FS-005 / URS-006 | Cold start et cascade de repli | `user_id` inconnu, avec et sans région ; lecteur ayant lu tout le vivier | Liste non vide dans tous les cas ; ordre = popularité de la région croisée avec la fraîcheur si disponible, sinon niveau suivant de la cascade | | `test_unknown_user_falls_back_to_popularity`, `test_new_user_gets_regional_popularity`, `test_region_croisee_avec_la_fraicheur`, `test_jamais_de_liste_vide` |
| OQ-06 | FS-003 / URS-004 | Classement collaboratif | Utilisateur connu du modèle CF | Article de meilleur score latent en tête | | `test_collaborative_ranks_by_factor_score` |
| OQ-07 | FS-015 / URS-001 | Robustesse entrée | `method` invalide | Erreur explicite (`ValueError` / HTTP 400), pas de crash | | `test_invalid_method_raises` |
| OQ-08 | FS-016 / URS-017 | Absence de données sensibles | Revue des entrées/sorties | Seuls des identifiants numériques anonymes sont manipulés | | revue documentée |
| OQ-09 | FS-008 / URS-009 | Interface de démonstration | Lancer l'app, choisir un `user_id`, cliquer « Recommander » | 5 articles affichés sans erreur | | capture d'écran |
| OQ-10 | FS-009 / URS-010 | Endpoint serverless (Azure) | `GET /api/recommend` avec `user_id` et `n=5`, sans préciser `method` | HTTP 200 ; JSON contenant `"method": "mix"` et `recommendations` de taille 5 | | capture réponse |
| OQ-11 | FS-018, FS-019 / URS-019 | Fenêtre de fraîcheur appliquée | Écrire un vivier connu, appeler les cinq stratégies ; décocher `fresh_only` | Aucune stratégie ne sort du vivier ; la désactivation élargit visiblement le classement ; une fenêtre trop courte est élargie et la durée effective reportée dans `recent_window.json` | | `test_toutes_les_strategies_respectent_le_vivier`, `test_fresh_only_desactivable`, `test_elargissement_automatique`, `test_ancre_ignore_les_horodatages_aberrants` |
| OQ-12 | FS-023, FS-024 / URS-020 | Prise en compte d'un artefact remplacé | Remplacer un artefact de fraîcheur dans Blob **sans redémarrer** ; puis remplacer un artefact lourd **de taille identique** et redéployer ; répéter 15 fois le même appel | Fraîcheur : la réponse suit le nouveau fichier sans redémarrage. Artefact lourd : une **seule** réponse distincte sur 15 appels (aucune instance ne sert l'ancien modèle) | | `test_meme_taille_mais_blob_plus_recent`, `test_meme_taille_et_cache_a_jour`, captures des 15 appels |
| OQ-13 | FS-020, FS-021 / URS-018 | Inscription d'un lecteur | Inscrire un lecteur (nom, région optionnelle), demander des recommandations, marquer un article comme lu, redemander | Recommandations obtenues immédiatement ; identifiant ≥ 1 000 000 ; la liste change après la lecture enregistrée ; nom vide ou déjà pris refusé avec message | | `test_identifiant_hors_catalogue_injecte_apres_chargement`, `test_historique_hors_catalogue_filtre_au_chargement`, capture d'écran |
| OQ-14 | FS-025 / URS-021 | Garde-fou de non-régression | Soumettre à `check_metrics.py` un fichier de métriques dégradé au-delà de la tolérance, puis un fichier conforme | Sortie **non nulle** (publication bloquée) dans le premier cas, nulle dans le second ; rapport nommant la métrique en cause | | journal d'exécution des deux appels |
| OQ-15 | FS-027 / URS-004 | Variante de note du SVD | Construire les deux variantes dans la même mesure ; demander la variante « étoiles » sans artefact d'étoiles | Les deux variantes donnent des classements distincts (aucun écrasement mutuel) ; l'absence d'artefact d'étoiles produit une erreur explicite | | `test_deux_variantes_ne_s_ecrasent_pas`, `test_variante_etoiles_exige_les_etoiles`, `test_le_recommender_d_origine_reste_intact` |
| OQ-16 | FS-017 / URS-019 | Composition de la stratégie de production | Appeler `method="mix"`, `n=5`, sur un vivier connu | Quatre premières places = popularité récente dans l'ordre ; cinquième place issue du contenu, absente des quatre premières | | `test_mix_reserve_une_place_au_contenu` |
| OQ-17 | FS-007 / URS-008 | Publication d'un nouvel article | Ajouter des articles depuis leurs embeddings, sans ré-ajuster l'ACP | Identifiants attribués à la suite du catalogue ; vecteurs existants inchangés ; article recommandable immédiatement par la voie contenu | | `test_new_article_is_recommendable_immediately`, `test_existing_vectors_are_untouched`, `test_new_article_projects_without_refitting` |

## 4. Écarts

| ID écart | Cas | Description | Criticité | Résolution | Statut |
|----------|-----|-------------|-----------|------------|--------|
| | | | | | |

## 5. Conclusion OQ

| Rôle | Nom | Signature | Date |
|------|-----|-----------|------|
| Exécutant | | | |
| Revue AQ | | | |
