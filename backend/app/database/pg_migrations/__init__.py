"""Forward-only PostgreSQL migrations.

Mirrors the Neo4j runner in app/database/migrations, with two differences that
follow from what this database holds:

  - Migrations connect as the **admin** role, while the application connects as
    the weaker `argus_app`. Schema changes and privilege grants must not be
    performable by the process serving requests.
  - `.sql` files rather than inline statements, because the security properties
    here (GRANTs, triggers) are worth reading as SQL rather than as generated
    strings.

Add a migration by dropping a `NNN_name.sql` file in this directory. Never edit
a released one — write the next number.
"""

from app.database.pg_migrations.runner import (
    applied_versions,
    current_version,
    run_pg_migrations,
)

__all__ = ["applied_versions", "current_version", "run_pg_migrations"]
