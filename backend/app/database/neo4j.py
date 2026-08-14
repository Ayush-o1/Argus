from neo4j import AsyncDriver, AsyncGraphDatabase, NotificationDisabledClassification

from app.config import get_settings

_driver: AsyncDriver | None = None


async def connect_neo4j() -> AsyncDriver:
    """Create the process-wide Neo4j async driver. Called once at app startup."""
    global _driver
    settings = get_settings()
    _driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        max_connection_pool_size=50,
        # A query that times out is a bounded failure the caller can report; one
        # that hangs holds a pool connection until the client disconnects, and
        # fifty of those take the service down. Applies to every query unless a
        # call site overrides it.
        max_transaction_retry_time=settings.neo4j_transaction_retry_seconds,
        # UNRECOGNIZED fires for "label does not exist" / "property does not
        # exist", which is the normal state on a fresh graph and during
        # migrations — several lines of warning per startup query, all benign.
        # Every other classification (PERFORMANCE, DEPRECATION, SECURITY) still
        # surfaces, which is where the real signal is.
        notifications_disabled_classifications=[NotificationDisabledClassification.UNRECOGNIZED],
    )
    await _driver.verify_connectivity()
    return _driver


async def close_neo4j() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


def get_driver() -> AsyncDriver:
    if _driver is None:
        raise RuntimeError("Neo4j driver not initialized — app startup did not run.")
    return _driver
