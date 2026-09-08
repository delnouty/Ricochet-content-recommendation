# Protocole de Qualification de Performance (PQ)

| Champ | Valeur |
|-------|--------|
| ID document | MC-PQ-001 |
| Version | 0.2 |
| Statut | DRAFT — pour exécution après approbation |
| Système | My Content — système de recommandation d'articles |
| Date d'émission | 2026-09-08 |
| Remplace | Version 0.1 du 2026-07-20 |

> **Support assistif — à réviser et approuver par l'AQ/CSV avant exécution.**

## 1. Objet

Démontrer que le système, dans des conditions représentatives de l'usage réel
(données réelles Globo.com, environnement de production), répond aux exigences
de performance et de qualité dans la durée.

## 2. Cas de qualification

| ID | Réf. URS | Cas | Méthode | Critère d'acceptation | P/F | Preuve |
|----|----------|-----|---------|-----------------------|-----|--------|
| PQ-01 | URS-011 | Temps de réponse | Mesurer la latence sur N requêtes représentatives (hors démarrage à froid) | Latence médiane < 2 s ; démarrage à froid mesuré et documenté séparément | | relevés |
| PQ-02 | URS-015, URS-016 | Qualité du modèle | `python -m src.evaluate --split test` : découpage **temporel 60/20/20**, réglages figés sur la validation, mesure unique sur le test. Quatre métriques : HitRate@5, Recall@5, couverture, personnalisation | Les quatre métriques sont produites et enregistrées dans `models/baseline_metrics.json` ; la stratégie retenue est celle du meilleur compromis justesse/couverture, pas de la seule justesse | | `models/baseline_metrics.json`, journal d'exécution, notebook 07 |
| PQ-03 | URS-012, URS-013 | Reproductibilité | Régénérer les artefacts (`prepare_model.py`, `collaborative_surprise.py`) avec mêmes données/paramètres | Artefacts identiques / métriques stables (`random_state` fixés) | | logs comparés |
| PQ-04 | URS-010 | Équivalence des trois solutions | Même `user_id`, même `method`, même `n` sur les solutions Azure, Hugging Face et locale | Recommandations **identiques** (mêmes artefacts, même cœur généré depuis `src/`) | | captures comparées des trois |
| PQ-05 | URS-016 | Surveillance de dérive (mise en place) | Vérifier le dispositif de suivi (métriques, journaux) prévu par l'architecture cible | Dispositif de monitoring et seuils d'alerte définis | | doc / capture |
| **PQ-06** | URS-015 | **Absence de biais d'évaluation** | Comparer la mesure en découpage temporel à une mesure *leave-last-out* sur données complètes (`python scripts/mesure_fuite.py`) | L'écart est mesuré et documenté ; seule la valeur en découpage temporel est retenue comme résultat | | journal d'exécution |
| **PQ-07** | URS-019, URS-020 | **Effet et actualité de la fenêtre de fraîcheur** | `python scripts/sweep_fraicheur.py` ; puis relever la date portée par `recent_window.json` en production | L'écart de justesse entre la fenêtre de production et l'historique complet est mesuré et documenté ; la fenêtre servie n'est pas plus ancienne que la cadence de republication prévue | | `models/freshness_sweep.json`, capture de la bannière système |

## 3. Suivi en exploitation (maintien de l'état validé)

- Surveillance : disponibilité, latence, taux d'erreur (Application Insights /
  logs HF).
- Indicateur métier : taux de clic (CTR) sur les articles recommandés.
- Réévaluation périodique de la qualité du modèle ; **ré-entraînement contrôlé**
  en cas de dérive (déclenche une re-validation ciblée — cf. VP §10).

## 4. Écarts

| ID écart | Cas | Description | Criticité | Résolution | Statut |
|----------|-----|-------------|-----------|------------|--------|
| | | | | | |

## 5. Conclusion PQ

| Rôle | Nom | Signature | Date |
|------|-----|-----------|------|
| Exécutant | | | |
| Revue AQ | | | |
