"""Tests must never touch the developer's database (backend/data/sentinel-<mode>.db).

`sentinel.main` builds a module-level app for uvicorn; importing it in a test would open,
and migrate, the default database file. conftest.py points it at an in-memory database.
"""

import sentinel.main


def test_the_module_level_app_uses_an_in_memory_database():
    assert sentinel.main.app.state.container.settings.resolved_db_path() == ":memory:"
