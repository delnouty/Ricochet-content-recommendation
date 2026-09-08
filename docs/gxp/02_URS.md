# Spécification des Exigences Utilisateur (URS)

| Champ | Valeur |
|-------|--------|
| ID document | MC-URS-001 |
| Version | 0.2 |
| Statut | DRAFT — pour revue AQ |
| Système | My Content — système de recommandation d'articles |
| Date d'émission | 2026-09-08 |
| Remplace | Version 0.1 du 2026-07-20 |

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
| URS-010 | F | M | Le système est déployable en **trois solutions indépendantes** : serverless Azure, Space Hugging Face, et exécution locale sans réseau. |
| URS-011 | P | M | Le temps de réponse d'une recommandation est compatible avec un usage interactif (cible : < 2 s hors démarrage à froid). |
| URS-012 | D | H | Les artefacts de modèle sont **versionnés et traçables** (intégrité, reproductibilité). |
| URS-013 | D | M | Le pipeline de préparation des modèles est **reproductible** à partir des données et de paramètres documentés. |
| URS-014 | R | M | Le code source est géré en contrôle de version (Git/GitHub). |
| URS-015 | F | M | La qualité des recommandations est **évaluable** par des métriques documentées couvrant à la fois la justesse et la variété de l'offre (la justesse seule désigne toujours la stratégie la moins personnalisée). |
| URS-016 | R | M | Le comportement du modèle IA/ML est ré-évaluable dans le temps (suivi de dérive, ré-entraînement contrôlé). |
| URS-017 | D | M | Le système ne traite aucune donnée à caractère sensible/réglementé (pas de donnée patient/clinique). |
| URS-018 | F | H | Un **nouveau lecteur** peut être inscrit dans l'application et reçoit des recommandations immédiatement, sans ré-entraînement du modèle. |
| URS-019 | F | H | Les recommandations privilégient les articles **récents**. La durée de la fenêtre de récence est un paramètre produit documenté et modifiable. |
| URS-020 | P | M | Une nouvelle fenêtre de récence devient effective **sans interruption de service**. |
| URS-021 | D | H | Une version de modèle dont la performance se dégrade au-delà d'un seuil défini **ne peut pas être publiée** (garde-fou de non-régression contre une référence versionnée). |
| URS-022 | F | M | Les lectures d'un lecteur inscrit sont **conservées** d'une session à l'autre lorsque l'hébergement le permet ; dans le cas contraire, l'application l'annonce explicitement au visiteur. |

## Hypothèses et contraintes

- Données d'entrée : jeu Globo.com (interactions users↔articles), traité comme
  donnée de développement.
- Hébergement : services gérés Azure Functions et Hugging Face Spaces (free tier),
  plus une exécution locale sans réseau.

## Historique des révisions

| Version | Date | Modifications | Motif |
|---------|------|---------------|-------|
| 0.1 | 2026-07-20 | Émission initiale. | — |
| 0.2 | 2026-09-08 | URS-010 : deux solutions → **trois** (l'exécution locale est une solution à part entière). URS-015 reformulée : la qualité ne s'évalue pas sur la seule justesse. Ajout de **URS-018 à URS-022** : inscription d'un nouveau lecteur, fenêtre de récence, mise à jour sans interruption, garde-fou de non-régression, persistance des lectures. | Les mesures conduites entre juillet et septembre ont fait de la **récence** un besoin produit et non un détail d'implémentation ; l'inscription d'un nouveau lecteur, absente de la v0.1, est une attente explicite du cahier des charges. |
