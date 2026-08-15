"""Ingestion: connectors, record mapping, and the pipeline that joins them.

Importing this package registers the built-in connector types, so
`build_connector` can resolve them by name from a database row.
"""

from app.ingestion import connectors as _connectors  # noqa: F401  (registration side effect)
from app.ingestion.base import (
    Connector,
    ConnectorConfigError,
    ConnectorError,
    FetchResult,
    RawRecord,
    build_connector,
    register_connector,
    registered_types,
)

__all__ = [
    "Connector",
    "ConnectorConfigError",
    "ConnectorError",
    "FetchResult",
    "RawRecord",
    "build_connector",
    "register_connector",
    "registered_types",
]
