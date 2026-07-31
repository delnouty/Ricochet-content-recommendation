# Protocole de Qualification d'Installation (IQ)

| Champ | Valeur |
|-------|--------|
| ID document | MC-IQ-001 |
| Version | 0.1 |
| Statut | DRAFT — pour exécution après approbation |
| Système | My Content — système de recommandation d'articles |
| Date d'émission | 2026-07-20 |

> **Support assistif — à réviser et approuver par l'AQ/CSV avant exécution.**

## 1. Objet et pré-requis

Vérifier que l'environnement et les composants sont correctement installés et
configurés. Pré-requis : VP, URS, FS, RA approuvés ; environnement cible
disponible ; artefacts de modèle générés.

## 2. Cas de qualification

| ID | Vérification | Méthode | Critère d'acceptation | Résultat (P/F) | Preuve | Exécutant/Date |
|----|--------------|---------|-----------------------|----------------|--------|----------------|
| IQ-01 | Version de Python | `python --version` | Version conforme à FS (≥ 3.11) | | capture | |
| IQ-02 | Dépôt de code cloné et versionné | `git log -1` | Commit identifiable (hash, auteur, date) | | capture | |
| IQ-03 | Artefacts de modèle présents et nommés | Lister `models/` (ou conteneur Blob / dépôt HF Hub) | `articles_embeddings_pca.npy`, `user_clicks.pkl`, `popular_articles.npy` (+ `cf_*` si collaboratif) présents | | listing | |
| IQ-04 | Dépendances installées (env de proto) | `pip install -r requirements.txt` | Installation sans erreur | | log | |
| IQ-05 | Solution Azure — dépendances Function | Vérifier `azure_function/requirements.txt` déployé | `azure-functions`, `numpy`, `azure-storage-blob` présents | | log | |
| IQ-06 | Solution Azure — configuration | Vérifier variables (`MODELS_DIR` ou `AZURE_STORAGE_CONNECTION_STRING`, `MODELS_CONTAINER`) | Variables renseignées, secret non exposé au dépôt | | capture | |
| IQ-07 | Solution HF — configuration du Space | Vérifier en-tête `spaces/README.md` (sdk streamlit) et secret `HF_MODEL_REPO` | Space configuré, secret présent | | capture | |
| IQ-08 | Intégrité des copies du cœur de reco | `python scripts/sync_recommender.py --check` | Code de sortie 0 (copies synchronisées) | | log | |
| IQ-09 | Exclusion des éléments sensibles | Vérifier `.gitignore` | `data/`, artefacts, `local.settings.json`, `.env` exclus | | capture | |

## 3. Écarts

| ID écart | Cas concerné | Description | Criticité | Résolution | Statut |
|----------|--------------|-------------|-----------|------------|--------|
| | | | | | |

## 4. Conclusion IQ

IQ prononcée **conforme / non conforme** (à statuer). Signatures :

| Rôle | Nom | Signature | Date |
|------|-----|-----------|------|
| Exécutant | | | |
| Revue AQ | | | |
