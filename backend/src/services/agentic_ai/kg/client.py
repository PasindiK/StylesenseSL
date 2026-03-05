import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Optional

from .config import KGConfig

logger = logging.getLogger(__name__)

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except Exception:
    GraphDatabase = None
    NEO4J_AVAILABLE = False


class Neo4jKGClient:
    def __init__(self, config: Optional[KGConfig] = None):
        self.config = config or KGConfig.from_env()
        self.driver = None
        self.enabled = bool(self.config.enabled and NEO4J_AVAILABLE)

        if not self.config.enabled:
            logger.info("[KG] Disabled via KG_ENABLED flag")
            return
        if not NEO4J_AVAILABLE:
            logger.warning("[KG] neo4j driver not installed. Install neo4j package to enable KG")
            return

        try:
            self.driver = GraphDatabase.driver(
                self.config.uri,
                auth=(self.config.user, self.config.password),
            )
            self.driver.verify_connectivity()
            logger.info("[KG] Connected to Neo4j at %s", self.config.uri)
        except Exception as exc:
            self.enabled = False
            self.driver = None
            logger.warning("[KG] Connection failed. Running without KG. reason=%s", exc)

    @contextmanager
    def session(self):
        if not self.enabled or not self.driver:
            yield None
            return
        s = self.driver.session(database=self.config.database)
        try:
            yield s
        finally:
            s.close()

    def run_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> Iterable[Any]:
        if not self.enabled:
            return []
        for attempt in range(3):
            try:
                with self.session() as s:
                    if s is None:
                        return []
                    result = s.run(query, params or {})
                    return list(result)
            except Exception as exc:
                logger.warning("[KG] Query failed (attempt %s): %s", attempt + 1, exc)
                if attempt < 2:
                    time.sleep(0.4 * (attempt + 1))
                    continue
                return []

    def execute_write(self, query: str, params: Optional[Dict[str, Any]] = None) -> None:
        if not self.enabled:
            return
        for attempt in range(3):
            try:
                with self.session() as s:
                    if s is None:
                        return
                    s.run(query, params or {})
                    return
            except Exception as exc:
                logger.warning("[KG] Write failed (attempt %s): %s", attempt + 1, exc)
                if attempt < 2:
                    time.sleep(0.4 * (attempt + 1))
                    continue
                return

    def close(self) -> None:
        if self.driver:
            self.driver.close()
