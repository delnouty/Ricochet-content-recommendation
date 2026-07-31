# Données

Les données **ne sont pas versionnées** (voir `.gitignore`). Il faut les télécharger et
les placer ici avant de lancer le prototypage.

## Source

Jeu de données *News Portal User Interactions by Globo.com* (Kaggle) :
https://www.kaggle.com/datasets/gspmoreira/news-portal-user-interactions-by-globocom

## Arborescence attendue

```
data/
├── raw/
│   ├── clicks/                     # dossier de fichiers clicks_hour_XXX.csv
│   │   ├── clicks_hour_000.csv
│   │   └── ...
│   ├── clicks_sample.csv           # échantillon (optionnel, pratique pour débuter)
│   ├── articles_metadata.csv       # article_id, category_id, created_at_ts, publisher_id, words_count
│   └── articles_embeddings.pickle  # matrice numpy (n_articles x 250)
```

## Formats

**clicks_hour_XXX.csv** (une ligne = un clic dans une session) :
`user_id, session_id, session_start, session_size, click_article_id,
click_timestamp, click_environment, click_deviceGroup, click_os,
click_country, click_region, click_referrer_type`

**articles_metadata.csv** :
`article_id, category_id, created_at_ts, publisher_id, words_count`

**articles_embeddings.pickle** : `numpy.ndarray` de forme `(n_articles, 250)`,
indexée par `article_id`.
