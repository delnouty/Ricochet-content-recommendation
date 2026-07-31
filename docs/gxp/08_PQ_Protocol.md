# Protocole de Qualification de Performance (PQ)

| Champ | Valeur |
|-------|--------|
| ID document | MC-PQ-001 |
| Version | 0.1 |
| Statut | DRAFT — pour exécution après approbation |
| Système | My Content — système de recommandation d'articles |
| Date d'émission | 2026-07-20 |

> **Support assistif — à réviser et approuver par l'AQ/CSV avant exécution.**

## 1. Objet

Démontrer que le système, dans des conditions représentatives de l'usage réel
(données réelles Globo.com, environnement de production), répond aux exigences
de performance et de qualité dans la durée.

## 2. Cas de qualification

| ID | Réf. URS | Cas | Méthode | Critère d'acceptation | P/F | Preuve |
|----|----------|-----|---------|-----------------------|-----|--------|
| PQ-01 | URS-011 | Temps de réponse | Mesurer la latence sur N requêtes représentatives (hors démarrage à froid) | Latence médiane < 2 s ; démarrage à froid documenté | | relevés |
| PQ-02 | URS-015, URS-016 | Qualité du modèle | Calculer HitRate@5 (leave-last-out) sur données réelles | Métrique ≥ seuil défini par le métier ; valeur enregistrée comme référence (*baseline*) | | notebook / rapport |
| PQ-03 | URS-012, URS-013 | Reproductibilité | Régénérer les artefacts (`prepare_model.py`) avec mêmes données/paramètres | Artefacts identiques / métriques stables (`random_state` fixés) | | logs comparés |
| PQ-04 | URS-010 | Équivalence des deux solutions | Même `user_id` sur solution Azure et solution HF | Recommandations identiques (mêmes artefacts, même cœur) | | captures comparées |
| PQ-05 | URS-016 | Surveillance de dérive (mise en place) | Vérifier le dispositif de suivi (métriques, journaux) prévu par l'architecture cible | Dispositif de monitoring et seuils d'alerte définis | | doc / capture |

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
