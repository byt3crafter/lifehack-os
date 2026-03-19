"""Simple migration system for SQLite schema changes."""

MIGRATIONS = [
    # Each migration is (version, description, sql)
    (1, "Add users table", '''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_login TEXT
        );
    '''),
    (2, "Add schema_version tracking", '''
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
            description TEXT
        );
    '''),
    # Note: migration 3 uses Python logic, not raw SQL (see run_migrations)
    (4, "Add AI usage log table", '''
        CREATE TABLE IF NOT EXISTS ai_usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            action TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0,
            success INTEGER DEFAULT 1,
            error_message TEXT DEFAULT '',
            duration_ms INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_ai_usage_timestamp ON ai_usage_log(timestamp);
    '''),
]


def get_current_version(conn) -> int:
    """Get current schema version."""
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        return row[0] or 0
    except Exception:
        return 0


def run_migrations(conn) -> None:
    """Run any pending migrations."""
    # First ensure schema_version table exists
    conn.execute('''CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
        description TEXT
    )''')

    current = get_current_version(conn)
    for version, description, sql in MIGRATIONS:
        if version > current:
            conn.executescript(sql)
            conn.execute(
                "INSERT OR IGNORE INTO schema_version (version, description) VALUES (?, ?)",
                (version, description),
            )
            conn.commit()
            print(f"  Migration {version}: {description}")

    # Migration 3: Add location/movement_type to walk_logs (safe for new DBs too)
    if current < 3:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(walk_logs)").fetchall()]
        if "location" not in cols:
            conn.execute("ALTER TABLE walk_logs ADD COLUMN location TEXT DEFAULT ''")
        if "movement_type" not in cols:
            conn.execute("ALTER TABLE walk_logs ADD COLUMN movement_type TEXT DEFAULT 'exercise'")
        conn.execute("INSERT OR IGNORE INTO schema_version (version, description) VALUES (3, 'Add location/movement_type to walk_logs')")
        conn.commit()
