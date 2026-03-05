import os
from dataclasses import dataclass


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class KGConfig:
    enabled: bool
    uri: str
    user: str
    password: str
    database: str
    bootstrap_on_start: bool

    @classmethod
    def from_env(cls) -> "KGConfig":
        return cls(
            enabled=_as_bool(os.getenv("KG_ENABLED"), default=False),
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            user=os.getenv("NEO4J_USER", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", "neo4j_password"),
            database=os.getenv("NEO4J_DB", "neo4j"),
            bootstrap_on_start=_as_bool(os.getenv("KG_BOOTSTRAP_ON_START"), default=False),
        )
