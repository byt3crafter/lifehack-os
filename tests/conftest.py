"""Pytest fixtures for LifeHack OS test suite."""
import os
import sqlite3
import sys
from pathlib import Path

import pytest

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))

# Env vars before any imports
os.environ["LIFEHACK_SECRET_KEY"] = "test-secret"
os.environ["LIFEHACK_USERNAME"] = "test"
os.environ["LIFEHACK_PASSWORD"] = "test"
os.environ["LIFEHACK_API_KEY"] = "test-key"
os.environ["LIFEHACK_AI_PROVIDER"] = "none"

# Import and patch BEFORE any app code
import src.infrastructure.database.connection as db_mod
import src.infrastructure.database as db_pkg

# Override get_db_path to use in-memory
_test_db_path = None


def _patched_get_db_path():
    """Return a temp file path for the test DB."""
    return Path(_test_db_path) if _test_db_path else Path(":memory:")


# Store original
_orig_get_db_path = db_mod.get_db_path


@pytest.fixture()
def test_conn(tmp_path):
    """Fresh SQLite DB for each test."""
    global _test_db_path

    db_file = tmp_path / "test.db"
    _test_db_path = str(db_file)

    # Reset the global connection so get_connection() creates a fresh one
    db_mod._connection = None
    db_mod.get_db_path = lambda: db_file

    # Now init will create tables on the fresh DB
    db_mod.init_database()
    conn = db_mod.get_connection()

    yield conn

    # Cleanup
    db_mod._connection = None
    db_mod.get_db_path = _orig_get_db_path
    _test_db_path = None


@pytest.fixture()
def app(test_conn):
    """Flask app wired to test DB."""
    from web.app import create_app
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    yield flask_app


@pytest.fixture()
def client(app):
    """Unauthenticated test client."""
    return app.test_client()


@pytest.fixture()
def auth_client(app):
    """Logged-in test client."""
    with app.test_client() as c:
        c.post("/login", data={"username": "test", "password": "test"}, follow_redirects=True)
        yield c


@pytest.fixture()
def api_headers():
    """API key headers for testing."""
    return {"X-API-Key": "test-key", "Content-Type": "application/json"}
