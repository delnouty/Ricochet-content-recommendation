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
| Système d'exploitation, runtime Python, Azure Functions, Hugging Face Spaces | 1 — Infrastructure | Plateformes/services standards |
| Bibliothèques (numpy, scikit-learn, implicit, streamlit) | 3 — Produit non configuré | Utilisées telles quelles |
| Moteur de recommandation (`src/`), Azure Function, Space HF, pipeline | 5 — Application sur mesure | Code développé spécifiquement |

## Liste des documents

| ID | Document | Fichier |
|----|----------|---------|
| MC-VAL-001 | Plan de Validation (VP) | [01_Validation_Plan.md](01_Validation_Plan.md) |
| MC-URS-001 | Spécification des Exigences Utilisateur (URS) | [02_URS.md](02_URS.md) |
| MC-FS-001 | Spécification Fonctionnelle (FS) | [03_Functional_Specification.md](03_Functional_Specification.md) |
| MC-RA-001 | Analyse de Risque (RA) | [04_Risk_Assessment.md](04_Risk_Assessment.md) |
| MC-RTM-001 | Matrice de Traçabilité (RTM) | [05_Traceability_Matrix.md](05_Traceability_Matrix.md) |
| MC-IQ-001 | Protocole de Qualification d'Installation (IQ) | [06_IQ_Protocol.md](06_IQ_Protocol.md) |
| MC-OQ-001 | Protocole de Qualification Opérationnelle (OQ) | [07_OQ_Protocol.md](07_OQ_Protocol.md) |
| MC-PQ-001 | Protocole de Qualification de Performance (PQ) | [08_PQ_Protocol.md](08_PQ_Protocol.md) |
| MC-VSR-001 | Rapport de Synthèse de Validation (VSR) | [09_Validation_Summary_Report.md](09_Validation_Summary_Report.md) |

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
