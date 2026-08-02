from neo4j import AsyncDriver, AsyncGraphDatabase

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
