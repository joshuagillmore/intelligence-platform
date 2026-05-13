# Legacy in-memory CollectionManager replaced by Neo4j-backed collections.
# TaskStatus enum preserved for backwards compatibility with collection status values.
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    STARTED = "STARTED"
    PROGRESS = "PROGRESS"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    REVOKED = "REVOKED"
