# Spécification des Exigences Utilisateur (URS)

| Champ | Valeur |
|-------|--------|
| ID document | MC-URS-001 |
| Version | 0.1 |
| Statut | DRAFT — pour revue AQ |
| Système | My Content — système de recommandation d'articles |
| Date d'émission | 2026-07-20 |

> **Support assistif — à réviser et approuver par l'AQ/CSV et le métier avant usage.**

## Tableau d'approbation

| Rôle | Nom | Signature | Date |
|------|-----|-----------|------|
| Propriétaire métier (CEO) | | | |
| Propriétaire système (CTO) | | | |
| Revue Qualité / AQ | | | |

## Conventions

- Criticité : **H** (haute), **M** (moyenne), **B** (basse).
- Type : F (fonctionnelle), P (performance), D (données/intégrité), R (réglementaire/qualité).

## Exigences

| ID | Type | Crit. | Exigence |
|----|------|-------|----------|
| URS-001 | F | H | Pour un identifiant utilisateur fourni, le système restitue une sélection d'articles recommandés. |
| URS-002 | F | H | Le nombre d'articles restitués est paramétrable, avec une valeur par défaut de **5**. |
| URS-003 | F | H | Le système recommande sur la base du contenu déjà lu (approche *content-based*). |
| URS-004 | F | M | Le système exploite les comportements collectifs (*collaborative filtering*). |
| URS-005 | F | M | Le système combine les approches (stratégie *hybride*) et permet de choisir la stratégie. |
| URS-006 | F | H | Un utilisateur sans historique exploitable reçoit une recommandation de repli (articles populaires — *cold start*). |
| URS-007 | F | H | Les articles déjà lus par l'utilisateur ne sont pas re-recommandés. |
| URS-008 | F | M | L'ajout d'un nouvel article est pris en charge sans ré-entraînement (via son embedding). |
| URS-009 | F | M | Le système est accessible via une interface applicative (démonstration). |
| URS-010 | F | M | Le système est déployable en **deux solutions indépendantes** : serverless Azure et Space Hugging Face. |
| URS-011 | P | M | Le temps de réponse d'une recommandation est compatible avec un usage interactif (cible : < 2 s hors démarrage à froid). |
| URS-012 | D | H | Les artefacts de modèle sont **versionnés et traçables** (intégrité, reproductibilité). |
| URS-013 | D | M | Le pipeline de préparation des modèles est **reproductible** à partir des données et de paramètres documentés. |
| URS-014 | R | M | Le code source est géré en contrôle de version (Git/GitHub). |
| URS-015 | F | B | La qualité des recommandations est **évaluable** par une métrique documentée (ex. HitRate@5). |
| URS-016 | R | M | Le comportement du modèle IA/ML est ré-évaluable dans le temps (suivi de dérive, ré-entraînement contrôlé). |
| URS-017 | D | M | Le système ne traite aucune donnée à caractère sensible/réglementé (pas de donnée patient/clinique). |

## Hypothèses et contraintes

- Données d'entrée : jeu Globo.com (interactions users↔articles), traité comme
  donnée de développement.
- Hébergement : services gérés Azure Functions et Hugging Face Spaces (free tier).
