from .mongo import (
    COLLECTIONS,
    INDEX_SPECS,
    SENSITIVE_COLLECTIONS,
    db,
    ensure_indexes,
    get_client,
)

__all__ = [
    "COLLECTIONS",
    "INDEX_SPECS",
    "SENSITIVE_COLLECTIONS",
    "db",
    "ensure_indexes",
    "get_client",
]
