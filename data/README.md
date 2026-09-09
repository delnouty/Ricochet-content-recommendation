# Data

The data is **not versioned** (see `.gitignore`). Download it and place it here
before running anything.

## Source

*News Portal User Interactions by Globo.com* (Kaggle):
https://www.kaggle.com/datasets/gspmoreira/news-portal-user-interactions-by-globocom

## Expected layout

```
data/
├── raw/
│   ├── clicks/                     # directory of clicks_hour_XXX.csv files
│   │   ├── clicks_hour_000.csv
│   │   └── ...
│   ├── clicks_sample.csv           # sample (optional, handy to get started)
│   ├── articles_metadata.csv       # article_id, category_id, created_at_ts, publisher_id, words_count
│   └── articles_embeddings.pickle  # numpy matrix (n_articles x 250)
```

## Formats

**clicks_hour_XXX.csv** (one row = one click within a session):
`user_id, session_id, session_start, session_size, click_article_id,
click_timestamp, click_environment, click_deviceGroup, click_os,
click_country, click_region, click_referrer_type`

**articles_metadata.csv**:
`article_id, category_id, created_at_ts, publisher_id, words_count`

**articles_embeddings.pickle**: a `numpy.ndarray` of shape `(n_articles, 250)`,
indexed by `article_id`.
