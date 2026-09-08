# Dossier de Validation CSV — My Content (système de recommandation)

> **Statut : DRAFT — supports en cours de rédaction.**
> Ces documents sont des **supports assistifs** destinés à être revus, complétés
> et **approuvés par une personne qualifiée (AQ / CSV)** avant tout usage.
> Ils ne constituent pas une décision de conformité réglementaire.

## Objet

Documentation de validation des systèmes informatisés (*Computerized System
Validation*, CSV) du logiciel de recommandation d'articles **My Content**,
selon une approche **GAMP 5 (2e édition)** basée sur le risque.

## Note de proportionnalité (à statuer par l'AQ)

En l'état, My Content est une application grand public de recommandation de
lecture : **aucune donnée GxP** (patient, clinique, qualité produit) n'est
traitée, et le système n'a pas d'impact direct sur la sécurité patient ni sur
l'intégrité de données réglementées. L'**impact GxP est donc évalué comme faible**
(cf. analyse de risque). Le présent dossier est fourni :
- soit comme **démonstration de méthodologie / gabarit** réutilisable,
- soit pour répondre à une **exigence interne** d'encadrement qualité du SDLC.

L'effort de validation réel doit être ajusté au risque par l'AQ.

## Classification GAMP

| Composant | Catégorie GAMP | Justification |
|-----------|----------------|---------------|
| Système d'exploitation, runtime Python, Azure Functions, Blob Storage, Table Storage, Hugging Face Spaces (SDK Docker) | 1 — Infrastructure | Plateformes/services standards |
| Bibliothèques (numpy, scikit-learn, implicit, surprise, streamlit, huggingface_hub, azure-data-tables) | 3 — Produit non configuré | Utilisées telles quelles, sans modification |
| Moteur de recommandation (`src/`), Azure Function, Space HF, application locale, pipeline d'artefacts | 5 — Application sur mesure | Code développé spécifiquement |

## Liste des documents

| ID | Document | Version | Fichier |
|----|----------|---------|---------|
| MC-VAL-001 | Plan de Validation (VP) | 0.2 | [01_Validation_Plan.md](01_Validation_Plan.md) |
| MC-URS-001 | Spécification des Exigences Utilisateur (URS) | 0.2 | [02_URS.md](02_URS.md) |
| MC-FS-001 | Spécification Fonctionnelle (FS) | 0.2 | [03_Functional_Specification.md](03_Functional_Specification.md) |
| MC-RA-001 | Analyse de Risque (RA) | 0.2 | [04_Risk_Assessment.md](04_Risk_Assessment.md) |
| MC-RTM-001 | Matrice de Traçabilité (RTM) | 0.2 | [05_Traceability_Matrix.md](05_Traceability_Matrix.md) |
| MC-IQ-001 | Protocole de Qualification d'Installation (IQ) | 0.2 | [06_IQ_Protocol.md](06_IQ_Protocol.md) |
| MC-OQ-001 | Protocole de Qualification Opérationnelle (OQ) | 0.2 | [07_OQ_Protocol.md](07_OQ_Protocol.md) |
| MC-PQ-001 | Protocole de Qualification de Performance (PQ) | 0.2 | [08_PQ_Protocol.md](08_PQ_Protocol.md) |
| MC-VSR-001 | Rapport de Synthèse de Validation (VSR) | 0.1 | [09_Validation_Summary_Report.md](09_Validation_Summary_Report.md) |

Périmètre couvert par la révision 0.2 (2026-09-08) : 22 exigences (URS), 28
spécifications fonctionnelles (FS), 17 risques (RA), 17 cas OQ, 7 cas PQ, 9 cas
IQ, et 59 tests unitaires servant de preuves de vérification.

**Reste en 0.1** : le VSR, à rédiger à l'issue de l'exécution des protocoles.

## Cycle de vie (V-model) et traçabilité

```
   URS ───────────────────────────────▶ PQ
     │                                   ▲
     └── FS ───────────────────────▶ OQ ─┘
           │                         ▲
           └── Design/Code ──▶ IQ ───┘
                    │
              Analyse de risque (transverse) + RTM (transverse)
```

## Références normatives (indicatives)

- ISPE GAMP 5: A Risk-Based Approach to Compliant GxP Computerized Systems (2e éd.).
- EU GMP Annexe 11 — Systèmes informatisés.
- FDA 21 CFR Part 11 — Enregistrements et signatures électroniques.
- Principes d'intégrité des données **ALCOA+**.
