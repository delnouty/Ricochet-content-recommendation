"""COPIE DÉPLOYÉE (solution Hugging Face) — générée depuis src/user_store.py.

⚠️  NE PAS ÉDITER ICI : toute modification serait écrasée.
    Source unique de vérité : src/user_store.py
    Régénérer : python scripts/sync_recommender.py
    Vérifier  : python scripts/sync_recommender.py --check   (utilisé en CI)
"""


from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

FIRST_LOCAL_USER_ID = 1_000_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    user_id    INTEGER PRIMARY KEY,
    name       TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL,
    region     INTEGER
);
CREATE TABLE IF NOT EXISTS reads (
    user_id    INTEGER NOT NULL,
    article_id INTEGER NOT NULL,
    read_at    TEXT    NOT NULL,
    PRIMARY KEY (user_id, article_id)
);
"""


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


class UserStore:
    """Clients inscrits localement et articles qu'ils ont lus."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            # Base créée avant l'ajout du cold start régional : on complète.
            columns = {row[1] for row in conn.execute("PRAGMA table_info(clients)")}
            if "region" not in columns:
                conn.execute("ALTER TABLE clients ADD COLUMN region INTEGER")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # ----------------------------------------------------------------- clients
    def create_client(self, name: str, region: int | None = None) -> int:
        """Inscrit un client et renvoie son `user_id`.

        `region` (code anonymisé, optionnel) sert au cold start : avant tout clic,
        le client reçoit la popularité de sa région plutôt que la popularité globale.

        Lève `ValueError` si le nom est vide ou déjà utilisé.
        """
        name = (name or "").strip()
        if not name:
            raise ValueError("Le nom du client ne peut pas être vide.")

        with self._connect() as conn:
            row = conn.execute("SELECT MAX(user_id) FROM clients").fetchone()
            user_id = max(FIRST_LOCAL_USER_ID, (row[0] or 0) + 1)
            try:
                conn.execute(
                    "INSERT INTO clients (user_id, name, created_at, region) "
                    "VALUES (?, ?, ?, ?)",
                    (user_id, name, _now(), None if region is None else int(region)))
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Un client nommé « {name} » existe déjà.") from exc
        return user_id

    def list_clients(self) -> list[dict]:
        """Clients inscrits (du plus récent au plus ancien) avec leur nombre de lectures."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT c.user_id, c.name, c.created_at, COUNT(r.article_id), c.region
                   FROM clients c LEFT JOIN reads r ON r.user_id = c.user_id
                   GROUP BY c.user_id ORDER BY c.user_id DESC"""
            ).fetchall()
        return [{"user_id": r[0], "name": r[1], "created_at": r[2], "reads": r[3],
                 "region": r[4]} for r in rows]

    def name_of(self, user_id: int) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT name FROM clients WHERE user_id = ?",
                               (int(user_id),)).fetchone()
        return row[0] if row else None

    def region_of(self, user_id: int) -> int | None:
        with self._connect() as conn:
            row = conn.execute("SELECT region FROM clients WHERE user_id = ?",
                               (int(user_id),)).fetchone()
        return row[0] if row and row[0] is not None else None

    def delete_client(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM reads WHERE user_id = ?", (int(user_id),))
            conn.execute("DELETE FROM clients WHERE user_id = ?", (int(user_id),))

    # ---------------------------------------------------------------- lectures
    def add_read(self, user_id: int, article_id: int) -> None:
        """Enregistre une lecture (idempotent : un article n'est stocké qu'une fois)."""
        if int(article_id) < 0:
            raise ValueError("article_id doit être positif.")
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO reads VALUES (?, ?, ?)",
                         (int(user_id), int(article_id), _now()))

    def add_reads(self, user_id: int, article_ids) -> int:
        """Enregistre plusieurs lectures ; renvoie le nombre de nouvelles lignes."""
        before = len(self.history(user_id))
        for article_id in article_ids:
            self.add_read(user_id, article_id)
        return len(self.history(user_id)) - before

    def history(self, user_id: int) -> list[int]:
        """Articles lus, dans l'ordre chronologique (comme `user_clicks.pkl`)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT article_id FROM reads WHERE user_id = ? ORDER BY read_at, rowid",
                (int(user_id),)).fetchall()
        return [r[0] for r in rows]

    def all_histories(self) -> dict[int, list[int]]:
        """Historique de tous les clients inscrits : user_id -> [article_id]."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_id, article_id FROM reads ORDER BY user_id, read_at, rowid"
            ).fetchall()
        out: dict[int, list[int]] = {}
        for user_id, article_id in rows:
            out.setdefault(user_id, []).append(article_id)
        return out
