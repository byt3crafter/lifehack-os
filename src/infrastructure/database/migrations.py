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
    (5, "Add app_log table for application-wide error and event logging", '''
        CREATE TABLE IF NOT EXISTS app_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            level TEXT NOT NULL DEFAULT 'error',
            source TEXT NOT NULL DEFAULT 'app',
            message TEXT NOT NULL,
            detail TEXT DEFAULT '',
            request_path TEXT DEFAULT '',
            request_method TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_app_log_timestamp ON app_log(timestamp);
    '''),
    (6, "Add habit phases, micro-tasks, strength, miss log, stacks, and templates", '''
        CREATE TABLE IF NOT EXISTS habit_phases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            phase_number INTEGER NOT NULL DEFAULT 1,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            unlock_after_days INTEGER DEFAULT 14,
            is_current INTEGER DEFAULT 0,
            completed_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS habit_micro_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phase_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (phase_id) REFERENCES habit_phases(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS habit_strength (
            habit_id INTEGER PRIMARY KEY,
            strength REAL DEFAULT 0,
            peak_strength REAL DEFAULT 0,
            last_completed TEXT,
            last_missed TEXT,
            total_completions INTEGER DEFAULT 0,
            total_misses INTEGER DEFAULT 0,
            FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS habit_miss_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            reason TEXT DEFAULT '',
            blocker TEXT DEFAULT '',
            logged_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS habit_stacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_text TEXT NOT NULL,
            habit_id INTEGER NOT NULL,
            FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS habit_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            category TEXT DEFAULT 'health',
            difficulty TEXT DEFAULT 'beginner',
            duration_weeks INTEGER DEFAULT 8,
            icon TEXT DEFAULT '',
            phases_json TEXT NOT NULL DEFAULT '[]',
            created_by TEXT DEFAULT 'system',
            is_featured INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_habit_phases_habit ON habit_phases(habit_id);
        CREATE INDEX IF NOT EXISTS idx_habit_micro_tasks_phase ON habit_micro_tasks(phase_id);
        CREATE INDEX IF NOT EXISTS idx_habit_miss_log_habit ON habit_miss_log(habit_id);
        CREATE INDEX IF NOT EXISTS idx_habit_stacks_habit ON habit_stacks(habit_id);
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

    # Migration 7: Add verification_rule to habit_micro_tasks + micro_task_completions table
    current = get_current_version(conn)
    if current < 7:
        # ALTER TABLE is not idempotent in SQLite so check column existence first
        micro_task_cols = [r[1] for r in conn.execute("PRAGMA table_info(habit_micro_tasks)").fetchall()]
        if "verification_rule" not in micro_task_cols:
            conn.execute(
                "ALTER TABLE habit_micro_tasks ADD COLUMN verification_rule TEXT DEFAULT '{\"type\": \"manual\"}'"
            )
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS micro_task_completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                micro_task_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                verified_by TEXT NOT NULL DEFAULT 'manual',
                verified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                current_value REAL,
                FOREIGN KEY (micro_task_id) REFERENCES habit_micro_tasks(id) ON DELETE CASCADE,
                UNIQUE(micro_task_id, date)
            );
            CREATE INDEX IF NOT EXISTS idx_micro_task_completions_task ON micro_task_completions(micro_task_id);
            CREATE INDEX IF NOT EXISTS idx_micro_task_completions_date ON micro_task_completions(date);
        """)
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, description) VALUES (7, 'Add verification_rule + micro_task_completions')"
        )
        conn.commit()
        print("  Migration 7: Add verification_rule + micro_task_completions")
