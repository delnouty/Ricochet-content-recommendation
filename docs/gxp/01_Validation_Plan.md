# Plan de Validation (VP)

| Champ | Valeur |
|-------|--------|
| ID document | MC-VAL-001 |
| Version | 0.1 |
| Statut | DRAFT — pour revue AQ |
| Système | My Content — système de recommandation d'articles |
| Date d'émission | 2026-07-20 |
| Auteur | Équipe technique (CTO) |

> **Support assistif — à réviser et approuver par l'AQ/CSV avant usage.**

## Tableau d'approbation

| Rôle | Nom | Signature | Date |
|------|-----|-----------|------|
| Auteur (Propriétaire système) | | | |
| Revue technique | | | |
| Revue Qualité / AQ | | | |
| Approbation | | | |

## 1. Objet

Définir la stratégie, le périmètre, les responsabilités et les livrables de la
validation du logiciel My Content, selon une approche GAMP 5 basée sur le risque.

## 2. Périmètre

**Inclus** : moteur de recommandation (`src/recommender.py`), pipeline de
préparation des artefacts (`src/prepare_model.py`), solution Azure
(`azure_function/`, `app/`), solution Hugging Face (`spaces/`), artefacts de
modèle et leur gestion.

**Exclu** : infrastructures gérées (services Azure, Hugging Face, dépôts Git),
couvertes par les accords de service des fournisseurs (catégorie GAMP 1) ;
constitution du jeu de données source (Globo.com), traité comme donnée d'entrée.

## 3. Description du système

Système de recommandation restituant une sélection d'articles (par défaut 5)
pour un identifiant utilisateur, à partir de trois stratégies (content-based,
collaboratif ALS, hybride) avec repli sur la popularité (cold start). Déployé
selon **deux solutions indépendantes** : serverless Azure Functions et Space
Hugging Face. Voir `docs/architecture.md`.

## 4. Approche de validation (basée sur le risque)

- Classification GAMP (cf. index) : cœur applicatif en catégorie 5.
- Effort de validation modulé par l'**analyse de risque** (MC-RA-001).
- Cycle en V : URS → FS → conception/code → IQ → OQ → PQ.
- Réutilisation des **tests unitaires automatisés** (`tests/`) comme preuves de
  vérification (leveraging supplier/developer testing).

## 5. Livrables de validation

VP, URS, FS, RA, RTM, protocoles IQ/OQ/PQ, VSR (cf. index MC-VAL).

## 6. Rôles et responsabilités

| Rôle | Responsabilité |
|------|----------------|
| Propriétaire système / CTO | Pilotage, exactitude technique, exécution des tests |
| Développement | Réalisation, tests unitaires, gestion de configuration |
| AQ / CSV | Revue, approbation, conformité méthodologique |
| Propriétaire métier (CEO) | Validation des exigences utilisateur |

## 7. Gestion de configuration et du changement

- Code versionné (Git + GitHub) ; artefacts de modèle versionnés (Blob / HF Hub).
- Cœur de reco maintenu en source unique (`src/`) et synchronisé vers les copies
  déployées via `scripts/sync_recommender.py` (contrôle `--check`).
- Tout changement significatif → évaluation d'impact et re-validation ciblée.

## 8. Critères d'acceptation

La validation est prononcée si : tous les cas OQ/PQ critiques sont **PASS**,
les écarts sont documentés et clôturés (ou justifiés), la RTM démontre une
couverture complète URS → tests. Formalisé dans le VSR (MC-VSR-001).

## 9. Gestion des écarts

Tout résultat non conforme est enregistré comme écart (description, criticité,
analyse de cause, action corrective, statut) et statué avant émission du VSR.

## 10. Maintien de l'état validé

Revue périodique, gestion des incidents, réévaluation lors des changements
(nouveau modèle, nouvelle version de dépendance), et pour l'IA/ML : suivi de la
**dérive du modèle** et re-entraînement contrôlé (cf. MC-RA-001).
