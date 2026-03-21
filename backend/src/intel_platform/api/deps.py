from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException
from neo4j import Driver, GraphDatabase

from intel_platform.config import settings
from intel_platform.graph.store import GraphStore

_driver: Driver | None = None


def get_neo4j_driver() -> Driver:
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _driver


def get_graph_store(driver: Driver = Depends(get_neo4j_driver)) -> GraphStore:
    return GraphStore(driver)


def verify_api_key(authorization: Optional[str] = Header(None)) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    if authorization != f"Bearer {settings.api_key}":
        raise HTTPException(status_code=401, detail="Invalid API key")
    return authorization
