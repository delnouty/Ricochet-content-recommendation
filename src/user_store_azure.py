"""Enregistrement des clients dans **Azure Table Storage**.

Même interface que `user_store.UserStore` (SQLite), à choisir selon l'hébergement :

  - SQLite convient à la solution **locale**, qui doit fonctionner sans réseau ;
  - Table Storage est nécessaire dès qu'un déploiement est **partagé ou éphémère** :
    un Space Hugging Face perd son disque à chaque redémarrage, et deux visiteurs
    d'un même service ne verraient pas les mêmes clients.

Pourquoi Table Storage plutôt que Cosmos DB ou Azure SQL : le compte de stockage
existe déjà (il héberge les artefacts) et sa chaîne de connexion est déjà
configurée. Aucune ressource, aucune dépendance d'infrastructure supplémentaire —
seul le paquet `azure-data-tables`.

Modèle de données — deux tables, dessinées pour les seules lectures dont
l'application a besoin :

| Table | PartitionKey | RowKey | Colonnes |
|---|---|---|---|
| `ricochetclients` | `"client"` | `user_id` | `name`, `created_at`, `region` |
| `ricochetreads` | `user_id` | `article_id` | `read_at` |

L'historique d'un client est donc **une seule partition** : le lire est une requête
de partition, l'opération la plus efficace du service. `all_histories()` balaie en
revanche toute la table — acceptable pour une démonstration (quelques dizaines de
clients), à revoir au-delà (voir `docs/architecture.md` §4.c, store de profils).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

FIRST_LOCAL_USER_ID = 1_000_000

TABLE_CLIENTS = "ricochetclients"
TABLE_READS = "ricochetreads"
PARTITION_CLIENTS = "client"


def _now() -> str:
    """Horodatage à la **microseconde**, et non à la seconde.

    L'ordre de lecture porte du sens : le profil de contenu peut être restreint aux
    k derniers articles, et l'interface affiche les dernières lectures. Or une table
    n'a pas d'équivalent du `rowid` de SQLite pour départager deux lignes de même
    horodatage : avec une précision à la seconde, trois lectures faites dans la même
    seconde ressortaient triées par identifiant d'article au lieu de l'ordre réel.
    """
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


class AzureUserStore:
    """Clients inscrits et articles lus, stockés dans Azure Table Storage."""

    def __init__(self, connection_string: str | None = None,
                 prefix: str = "ricochet"):
        from azure.data.tables import TableServiceClient

        conn = connection_string or os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        if not conn:
            raise ValueError(
                "Chaîne de connexion absente. Fournir `connection_string` ou définir "
                "AZURE_STORAGE_CONNECTION_STRING."
            )

        self.nom_clients = f"{prefix}clients"
        self.nom_reads = f"{prefix}reads"

        service = TableServiceClient.from_connection_string(conn)
        # `create_table_if_not_exists` est idempotent : appelable à chaque démarrage.
        self._clients = service.create_table_if_not_exists(self.nom_clients)
        self._reads = service.create_table_if_not_exists(self.nom_reads)

    # ----------------------------------------------------------------- clients
    def create_client(self, name: str, region: int | None = None) -> int:
        """Inscrit un client et renvoie son `user_id`.

        Lève `ValueError` si le nom est vide ou déjà utilisé. L'unicité du nom n'est
        pas garantie par le service (une table n'a pas d'index secondaire) : elle est
        vérifiée par lecture préalable, ce qui laisse une fenêtre de concurrence
        acceptable pour une démonstration mais qu'il faudrait fermer en production
        (par exemple en faisant du nom la clé de ligne).
        """
        name = (name or "").strip()
        if not name:
            raise ValueError("Le nom du client ne peut pas être vide.")

        existants = list(self._clients.list_entities())
        if any(e.get("name") == name for e in existants):
            raise ValueError(f"Un client nommé « {name} » existe déjà.")

        prochain = max([int(e["RowKey"]) for e in existants] + [FIRST_LOCAL_USER_ID - 1]) + 1
        self._clients.create_entity({
            "PartitionKey": PARTITION_CLIENTS,
            "RowKey": str(prochain),
            "name": name,
            "created_at": _now(),
            "region": None if region is None else int(region),
        })
        return prochain

    def list_clients(self) -> list[dict]:
        """Clients inscrits, du plus récent au plus ancien, avec leur nombre de lectures."""
        lectures = self._compter_lectures()
        clients = [{
            "user_id": int(e["RowKey"]),
            "name": e.get("name", ""),
            "created_at": e.get("created_at", ""),
            "region": e.get("region"),
            "reads": lectures.get(int(e["RowKey"]), 0),
        } for e in self._clients.list_entities()]
        return sorted(clients, key=lambda c: -c["user_id"])

    def name_of(self, user_id: int) -> str | None:
        entite = self._client_ou_none(user_id)
        return entite.get("name") if entite else None

    def region_of(self, user_id: int) -> int | None:
        entite = self._client_ou_none(user_id)
        if not entite or entite.get("region") is None:
            return None
        return int(entite["region"])

    def delete_client(self, user_id: int) -> None:
        """Supprime le client et tout son historique."""
        from azure.core.exceptions import ResourceNotFoundError

        for article_id in self.history(user_id):
            try:
                self._reads.delete_entity(partition_key=str(int(user_id)),
                                          row_key=str(int(article_id)))
            except ResourceNotFoundError:
                pass
        try:
            self._clients.delete_entity(partition_key=PARTITION_CLIENTS,
                                        row_key=str(int(user_id)))
        except ResourceNotFoundError:
            pass

    # ---------------------------------------------------------------- lectures
    def add_read(self, user_id: int, article_id: int) -> None:
        """Enregistre une lecture. Idempotent : `upsert` écrase la même clé."""
        if int(article_id) < 0:
            raise ValueError("article_id doit être positif.")
        self._reads.upsert_entity({
            "PartitionKey": str(int(user_id)),
            "RowKey": str(int(article_id)),
            "read_at": _now(),
        })

    def add_reads(self, user_id: int, article_ids) -> int:
        """Enregistre plusieurs lectures ; renvoie le nombre de nouvelles lignes."""
        avant = set(self.history(user_id))
        for article_id in article_ids:
            self.add_read(user_id, article_id)
        return len(set(self.history(user_id)) - avant)

    def history(self, user_id: int) -> list[int]:
        """Articles lus, dans l'ordre chronologique.

        Requête de partition : la partition **est** l'utilisateur, donc c'est la
        lecture la plus directe que le service sait faire.
        """
        entites = self._reads.query_entities(
            "PartitionKey eq @pk", parameters={"pk": str(int(user_id))})
        lignes = [(e.get("read_at", ""), int(e["RowKey"])) for e in entites]
        return [article_id for _, article_id in sorted(lignes)]

    def all_histories(self) -> dict[int, list[int]]:
        """Historique de tous les clients : user_id -> [article_id].

        Balayage complet de la table : acceptable pour une démonstration, à
        remplacer par une lecture par utilisateur au-delà de quelques centaines.
        """
        par_client: dict[int, list[tuple[str, int]]] = {}
        for e in self._reads.list_entities():
            par_client.setdefault(int(e["PartitionKey"]), []).append(
                (e.get("read_at", ""), int(e["RowKey"])))
        return {user_id: [a for _, a in sorted(lignes)]
                for user_id, lignes in par_client.items()}

    # ------------------------------------------------------------------ privé
    def _client_ou_none(self, user_id: int):
        from azure.core.exceptions import ResourceNotFoundError
        try:
            return self._clients.get_entity(partition_key=PARTITION_CLIENTS,
                                            row_key=str(int(user_id)))
        except ResourceNotFoundError:
            return None

    def _compter_lectures(self) -> dict[int, int]:
        compte: dict[int, int] = {}
        for e in self._reads.list_entities():
            cle = int(e["PartitionKey"])
            compte[cle] = compte.get(cle, 0) + 1
        return compte


def open_store(clients_db=None, connection_string: str | None = None):
    """Ouvre le magasin adapté à l'hébergement.

    Règle : Table Storage si une chaîne de connexion est disponible, SQLite sinon.
    Ainsi la solution locale reste sans réseau, tandis que les déploiements Azure et
    Hugging Face conservent leurs clients d'un redémarrage à l'autre.

    `RICOCHET_STORE=sqlite` force le stockage local même en présence d'une chaîne de
    connexion — utile pour tester l'interface sans écrire dans le cloud.
    """
    conn = connection_string or os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    force = os.environ.get("RICOCHET_STORE", "").lower()

    if conn and force != "sqlite":
        try:
            return AzureUserStore(conn)
        except Exception as exc:  # noqa: BLE001
            # Un stockage distant indisponible ne doit pas empêcher l'application
            # de démarrer : on se replie sur le local en le disant.
            print(f"[store] Table Storage indisponible ({type(exc).__name__}) — "
                  "repli sur SQLite local")

    from src.user_store import UserStore
    return UserStore(clients_db or "clients.db")
