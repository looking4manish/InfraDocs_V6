"""MongoDB manager — single-database build for V6."""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import ConnectionFailure

logger = logging.getLogger(__name__)


class DBManager:
    """Single-database MongoDB manager for InfraDocs V6.

    V5 used a database-per-server pattern (infradocs_oci, infradocs_n150, ...).
    V6 is OCI-only, so we use one database and tag each document with
    server_id='oci' for forward-compatibility when distribution returns.
    """

    def __init__(self, uri: str, database: str):
        self.uri = uri
        self.database = database
        self.client: Optional[MongoClient] = None
        self._connect()

    def _connect(self):
        try:
            self.client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            self.client.admin.command("ping")
            logger.info(f"Connected to MongoDB database '{self.database}'")
        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    @property
    def db(self):
        return self.client[self.database]

    # ---------- assets ----------

    def insert_assets(self, assets: List[Dict]) -> int:
        if not assets:
            return 0
        now = datetime.now(timezone.utc)
        for a in assets:
            a.setdefault("created_at", now)
            a["updated_at"] = now
        result = self.db.assets.insert_many(assets)
        logger.info(f"Inserted {len(result.inserted_ids)} assets")
        return len(result.inserted_ids)

    def upsert_asset(self, asset: Dict) -> bool:
        query = {
            "category": asset["category"],
            "asset_id": asset["asset_id"],
        }
        now = datetime.now(timezone.utc)
        asset.setdefault("created_at", now)
        asset["updated_at"] = now
        result = self.db.assets.update_one(query, {"$set": asset}, upsert=True)
        return result.acknowledged

    def get_assets(
        self,
        category: Optional[str] = None,
        project: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict]:
        query: Dict = {}
        if category:
            query["category"] = category
        if project:
            query["project"] = project
        if status:
            query["status"] = status

        assets = list(self.db.assets.find(query))
        for a in assets:
            a["_id"] = str(a["_id"])
        return assets

    def delete_all_assets(self) -> int:
        result = self.db.assets.delete_many({})
        logger.info(f"Deleted {result.deleted_count} assets")
        return result.deleted_count

    # ---------- projects ----------

    def upsert_project(self, project: Dict) -> bool:
        query = {"project_name": project["project_name"]}
        now = datetime.now(timezone.utc)
        project.setdefault("created_at", now)
        project["updated_at"] = now
        result = self.db.projects.update_one(query, {"$set": project}, upsert=True)
        return result.acknowledged

    def get_projects(self) -> List[Dict]:
        projects = list(self.db.projects.find({}))
        for p in projects:
            p["_id"] = str(p["_id"])
        return projects

    # ---------- scan logs ----------

    def insert_scan_log(self, scan_log: Dict) -> str:
        scan_log["created_at"] = datetime.now(timezone.utc)
        result = self.db.scan_logs.insert_one(scan_log)
        return str(result.inserted_id)

    def get_scan_logs(self, limit: int = 50) -> List[Dict]:
        logs = list(
            self.db.scan_logs.find({})
            .sort("created_at", DESCENDING)
            .limit(limit)
        )
        for log in logs:
            log["_id"] = str(log["_id"])
        return logs

    # ---------- utilities ----------

    def create_indexes(self):
        self.db.assets.create_index([("category", ASCENDING)])
        self.db.assets.create_index("asset_id")
        self.db.assets.create_index("project")
        self.db.assets.create_index("status")
        self.db.assets.create_index([("updated_at", DESCENDING)])

        self.db.projects.create_index("project_name", unique=True)

        self.db.scan_logs.create_index([("created_at", DESCENDING)])

        logger.info(f"Created indexes for {self.database}")

    def get_stats(self) -> Dict:
        return {
            "database": self.database,
            "assets_count": self.db.assets.count_documents({}),
            "projects_count": self.db.projects.count_documents({}),
            "scan_logs_count": self.db.scan_logs.count_documents({}),
            "collections": self.db.list_collection_names(),
        }

    def close(self):
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")
