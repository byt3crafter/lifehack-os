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
    (9, "Add chat_messages table for universal AI chat", '''
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            context_summary TEXT DEFAULT '',
            tokens_used INTEGER DEFAULT 0,
            provider TEXT DEFAULT '',
            model TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_messages(created_at);
    '''),
    (10, "Add deep_work_projects table and extend deep_work_sessions", '''
        CREATE TABLE IF NOT EXISTS deep_work_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            color TEXT DEFAULT '#4f80ff',
            active INTEGER DEFAULT 1,
            total_minutes INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_dw_projects_active ON deep_work_projects(active);
    '''),
    (8, "Add finance tables (rules, log, advice) and discover columns on wishlist", '''
        CREATE TABLE IF NOT EXISTS finance_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            monthly_limit REAL,
            description TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS finance_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT DEFAULT '',
            category TEXT DEFAULT '',
            type TEXT DEFAULT 'withdrawal',
            source TEXT DEFAULT 'firefly',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS finance_advice (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            advice TEXT NOT NULL,
            amount REAL,
            category TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_finance_log_date ON finance_log(date);
        CREATE INDEX IF NOT EXISTS idx_finance_log_category ON finance_log(category);
        CREATE INDEX IF NOT EXISTS idx_finance_advice_created ON finance_advice(created_at);
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

    # Migration 8 (extra): Add Discover columns to wishlist — ALTER TABLE is not
    # idempotent in SQLite so each column is guarded by a presence check.
    # Always check columns — SQL migration may have already incremented the version
    if True:
        wishlist_cols = [r[1] for r in conn.execute("PRAGMA table_info(wishlist)").fetchall()]
        discover_cols = [
            ("status",       "TEXT DEFAULT 'want'"),
            ("rating",       "INTEGER"),
            ("completed_at", "TEXT"),
            ("photos_json",  "TEXT DEFAULT '[]'"),
            ("notes",        "TEXT DEFAULT ''"),
        ]
        for col_name, col_def in discover_cols:
            if col_name not in wishlist_cols:
                conn.execute(f"ALTER TABLE wishlist ADD COLUMN {col_name} {col_def}")
        conn.commit()
        print("  Migration 8 (wishlist discover columns): applied")

    # Migration 10 (extra): Add new columns to deep_work_sessions. SQLite does
    # not support ADD COLUMN IF NOT EXISTS so we guard each with a PRAGMA check.
    # Always check — the SQL migration may have already incremented the version
    if True:
        dw_cols = [r[1] for r in conn.execute("PRAGMA table_info(deep_work_sessions)").fetchall()]
        dw_new_cols = [
            ("local_project_id", "INTEGER"),
            ("vikunja_task_id",  "TEXT"),
            ("description",      "TEXT DEFAULT ''"),
        ]
        for col_name, col_def in dw_new_cols:
            if col_name not in dw_cols:
                conn.execute(f"ALTER TABLE deep_work_sessions ADD COLUMN {col_name} {col_def}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dw_sessions_local_project ON deep_work_sessions(local_project_id)")
        conn.commit()
        print("  Migration 10 (deep_work_sessions new columns): applied")

    # Migration 11: Add rating and mood_after to food_logs
    fl_cols = [r[1] for r in conn.execute("PRAGMA table_info(food_logs)").fetchall()]
    if "rating" not in fl_cols:
        conn.execute("ALTER TABLE food_logs ADD COLUMN rating INTEGER")
    if "mood_after" not in fl_cols:
        conn.execute("ALTER TABLE food_logs ADD COLUMN mood_after INTEGER")
    conn.execute("INSERT OR IGNORE INTO schema_version (version, description) VALUES (11, 'Add rating and mood_after to food_logs')")
    conn.commit()

    # Migration 12: Add savings_goals table for Finance module Stage 1
    current = get_current_version(conn)
    if current < 12:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS savings_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                icon TEXT DEFAULT '🎯',
                target_amount REAL NOT NULL,
                current_amount REAL DEFAULT 0,
                firefly_account_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_savings_goals_created ON savings_goals(created_at);
        """)
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, description) VALUES (12, 'Add savings_goals table')"
        )
        conn.commit()
        print("  Migration 12: Add savings_goals table")

    # Migration 13: Finance Stage 2 tables (recurring, anomalies, digests)
    current = get_current_version(conn)
    if current < 13:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS finance_recurring (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                category TEXT DEFAULT '',
                estimated_amount REAL NOT NULL,
                frequency TEXT DEFAULT 'monthly',
                confidence REAL DEFAULT 0.0,
                last_seen_date TEXT,
                transaction_count INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                dismissed INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_finance_recurring_active ON finance_recurring(active);

            CREATE TABLE IF NOT EXISTS finance_anomalies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id TEXT,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT DEFAULT '',
                category_average REAL,
                deviation_factor REAL,
                alert_type TEXT DEFAULT 'high_spend',
                acknowledged INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_finance_anomalies_ack ON finance_anomalies(acknowledged);

            CREATE TABLE IF NOT EXISTS finance_digests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_start TEXT NOT NULL,
                week_end TEXT NOT NULL,
                total_spent REAL DEFAULT 0,
                top_categories_json TEXT DEFAULT '[]',
                budget_status_json TEXT DEFAULT '[]',
                notable_transactions_json TEXT DEFAULT '[]',
                recurring_total REAL DEFAULT 0,
                anomaly_count INTEGER DEFAULT 0,
                ai_summary TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(week_start)
            );
        """)
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, description) VALUES (13, 'Finance Stage 2: recurring, anomalies, digests')"
        )
        conn.commit()
        print("  Migration 13: Finance Stage 2 tables")

    # Migration 14: Multi-user data isolation
    # Adds user_id column to every user-data table, creates user_settings
    # and user_integrations tables, and assigns all existing data to the
    # first admin user.
    current = get_current_version(conn)
    if current < 14:
        print("  Migration 14: Multi-user data isolation — starting …")

        # Find the first admin user (or first user at all) to own existing data
        admin_row = conn.execute(
            "SELECT id FROM users WHERE is_admin = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        if not admin_row:
            admin_row = conn.execute(
                "SELECT id FROM users ORDER BY id LIMIT 1"
            ).fetchone()
        admin_id = admin_row['id'] if admin_row else 1

        # --- Tables that just need an ALTER TABLE ADD COLUMN + UPDATE --------
        simple_tables = [
            'habits', 'habit_completions', 'habit_phases', 'habit_micro_tasks',
            'micro_task_completions', 'habit_strength', 'habit_miss_log',
            'habit_stacks', 'projects', 'milestones', 'tasks',
            'walk_logs', 'replacement_actions', 'replacement_logs',
            'point_ledger', 'streaks', 'food_logs', 'fasting_logs',
            'wishlist', 'finance_rules', 'finance_log', 'finance_advice',
            'savings_goals', 'finance_recurring', 'finance_anomalies',
            'finance_digests', 'challenges', 'challenge_logs',
            'chat_messages', 'ai_insights', 'deep_work_sessions',
            'deep_work_projects',
        ]

        for table in simple_tables:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if 'user_id' not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id)")
                conn.execute(f"UPDATE {table} SET user_id = ?", (admin_id,))
                conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_user ON {table}(user_id)")
                print(f"    + {table}")
        conn.commit()

        # --- daily_checkins: add user_id, recreate UNIQUE as (user_id, date) -
        dc_cols = [r[1] for r in conn.execute("PRAGMA table_info(daily_checkins)").fetchall()]
        if 'user_id' not in dc_cols:
            conn.execute("ALTER TABLE daily_checkins ADD COLUMN user_id INTEGER REFERENCES users(id)")
            conn.execute(f"UPDATE daily_checkins SET user_id = ?", (admin_id,))
            conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_checkins_user ON daily_checkins(user_id)")
            # The old UNIQUE(date) remains but is harmless — app logic filters by user_id
            print("    + daily_checkins")
        conn.commit()

        # --- user_stats: recreate without CHECK(id=1), use user_id as PK -----
        us_cols = [r[1] for r in conn.execute("PRAGMA table_info(user_stats)").fetchall()]
        if 'user_id' not in us_cols:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_stats_new (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id),
                    total_xp INTEGER NOT NULL DEFAULT 0,
                    level INTEGER NOT NULL DEFAULT 1,
                    sobriety_start_date TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute(f"""
                INSERT OR IGNORE INTO user_stats_new (user_id, total_xp, level, sobriety_start_date, created_at)
                SELECT ?, total_xp, level, sobriety_start_date, created_at FROM user_stats WHERE id = 1
            """, (admin_id,))
            conn.execute("DROP TABLE user_stats")
            conn.execute("ALTER TABLE user_stats_new RENAME TO user_stats")
            print("    + user_stats (recreated)")
        conn.commit()

        # --- New table: user_settings (per-user key-value overrides) ----------
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, key)
            );
        """)
        print("    + user_settings (created)")

        # Migrate existing app_settings that are per-user to user_settings
        per_user_keys = [
            'finance_card_visibility', 'calorie_goal',
        ]
        # Also migrate module toggles
        module_rows = conn.execute(
            "SELECT key, value FROM app_settings WHERE key LIKE 'module_%'"
        ).fetchall()
        for row in module_rows:
            per_user_keys.append(row['key'])

        for key in per_user_keys:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
            if row:
                conn.execute(
                    "INSERT OR IGNORE INTO user_settings (user_id, key, value) VALUES (?, ?, ?)",
                    (admin_id, key, row['value']),
                )

        # --- New table: user_integrations (per-user credentials) --------------
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS user_integrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                integration_name TEXT NOT NULL,
                enabled INTEGER DEFAULT 0,
                config_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, integration_name)
            );
            CREATE INDEX IF NOT EXISTS idx_user_integrations_user ON user_integrations(user_id);
        """)
        print("    + user_integrations (created)")

        # Migrate existing plugin configs from app_settings to user_integrations
        for plugin_name in ('firefly', 'vikunja'):
            setting_key = f'plugin_config_{plugin_name}'
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (setting_key,)
            ).fetchone()
            if row and row['value']:
                import json as _json
                try:
                    cfg = _json.loads(row['value'])
                    conn.execute(
                        """INSERT OR IGNORE INTO user_integrations
                           (user_id, integration_name, enabled, config_json)
                           VALUES (?, ?, ?, ?)""",
                        (admin_id, plugin_name,
                         1 if cfg.get('enabled') else 0,
                         _json.dumps(cfg.get('config', {}))),
                    )
                except (_json.JSONDecodeError, TypeError):
                    pass

        # Migrate AI provider keys to user_integrations
        ai_keys = [
            'ai_openai_key', 'ai_openai_url', 'ai_openai_model',
            'ai_anthropic_key', 'ai_anthropic_model',
            'ai_minimax_key', 'ai_minimax_model',
            'ai_ollama_url', 'ai_ollama_model',
            'ai_chatgpt_model', 'openai_oauth_token',
            'ai_provider_food', 'ai_provider_habits', 'ai_provider_insights',
            'ai_provider_reports', 'ai_provider_default', 'ai_provider',
        ]
        ai_config = {}
        for key in ai_keys:
            r = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
            if r and r['value']:
                ai_config[key] = r['value']

        if ai_config:
            import json as _json
            conn.execute(
                """INSERT OR IGNORE INTO user_integrations
                   (user_id, integration_name, enabled, config_json)
                   VALUES (?, 'ai_providers', 1, ?)""",
                (admin_id, _json.dumps(ai_config)),
            )

        conn.commit()

        # Initialise user_stats for every user that doesn't have a row yet
        all_users = conn.execute("SELECT id FROM users").fetchall()
        for u in all_users:
            conn.execute(
                "INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)",
                (u['id'],),
            )
        conn.commit()

        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, description) VALUES (14, 'Multi-user data isolation')"
        )
        conn.commit()
        print("  Migration 14: Multi-user data isolation — done")

    # Migration 15: User registration, profiles, invite codes, password reset
    current = get_current_version(conn)
    if current < 15:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS invite_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                created_by INTEGER NOT NULL REFERENCES users(id),
                used_by INTEGER,
                max_uses INTEGER DEFAULT 1,
                use_count INTEGER DEFAULT 0,
                expires_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_invite_codes_code ON invite_codes(code);

            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                bio TEXT DEFAULT '',
                age INTEGER,
                timezone TEXT DEFAULT '',
                health_goals TEXT DEFAULT '',
                fitness_level TEXT DEFAULT '',
                dietary_preferences TEXT DEFAULT '',
                work_type TEXT DEFAULT '',
                work_hours TEXT DEFAULT '',
                photo_path TEXT DEFAULT '',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                created_by INTEGER NOT NULL REFERENCES users(id),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_reset_tokens_token ON password_reset_tokens(token);
        """)

        # Initialize profile rows for all existing users
        all_users = conn.execute("SELECT id FROM users").fetchall()
        for u in all_users:
            conn.execute(
                "INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)",
                (u['id'],),
            )

        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, description) VALUES (15, 'User registration, profiles, invite codes')"
        )
        conn.commit()
        print("  Migration 15: User registration, profiles, invite codes")

    # Migration 16: Add body metrics and preferred_name to user_profiles
    current = get_current_version(conn)
    if current < 16:
        profile_cols = [r[1] for r in conn.execute("PRAGMA table_info(user_profiles)").fetchall()]
        new_profile_cols = [
            ("height_cm",        "REAL"),
            ("weight_kg",        "REAL"),
            ("gender",           "TEXT DEFAULT ''"),
            ("target_weight_kg", "REAL"),
            ("preferred_name",   "TEXT DEFAULT ''"),
        ]
        for col_name, col_def in new_profile_cols:
            if col_name not in profile_cols:
                conn.execute(f"ALTER TABLE user_profiles ADD COLUMN {col_name} {col_def}")
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, description) VALUES (16, 'Add body metrics and preferred_name to user_profiles')"
        )
        conn.commit()
        print("  Migration 16: Add body metrics and preferred_name to user_profiles")

    # Migration 17: Add scheduled_time to habits
    current = get_current_version(conn)
    if current < 17:
        habit_cols = [r[1] for r in conn.execute("PRAGMA table_info(habits)").fetchall()]
        if 'scheduled_time' not in habit_cols:
            conn.execute("ALTER TABLE habits ADD COLUMN scheduled_time TEXT DEFAULT ''")
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, description) VALUES (17, 'Add scheduled_time to habits')"
        )
        conn.commit()
        print("  Migration 17: Add scheduled_time to habits")

    # Migration 19: Add email and use_gravatar to user_profiles
    current = get_current_version(conn)
    if current < 19:
        profile_cols = [r[1] for r in conn.execute("PRAGMA table_info(user_profiles)").fetchall()]
        if 'email' not in profile_cols:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN email TEXT DEFAULT ''")
        if 'use_gravatar' not in profile_cols:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN use_gravatar INTEGER DEFAULT 0")
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, description) VALUES (19, 'Add email and use_gravatar to user_profiles')"
        )
        conn.commit()
        print("  Migration 19: Add email and use_gravatar to user_profiles")

    # Migration 20: Wellness — water_logs and sleep_logs
    current = get_current_version(conn)
    if current < 20:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS water_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                glasses INTEGER NOT NULL DEFAULT 1,
                logged_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_water_logs_user ON water_logs(user_id);

            CREATE TABLE IF NOT EXISTS sleep_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                date TEXT NOT NULL,
                bedtime TEXT,
                wake_time TEXT,
                hours REAL,
                quality INTEGER DEFAULT 3,
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_sleep_logs_user ON sleep_logs(user_id);
            CREATE INDEX IF NOT EXISTS idx_sleep_logs_date ON sleep_logs(date);
        """)
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, description) VALUES (20, 'Wellness: water_logs and sleep_logs')"
        )
        conn.commit()
        print("  Migration 20: Wellness — water_logs and sleep_logs")

    # Migration 18: Journal, Books, Notes modules
    current = get_current_version(conn)
    if current < 18:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                date TEXT NOT NULL,
                mood INTEGER DEFAULT 3,
                energy INTEGER DEFAULT 3,
                gratitude_json TEXT DEFAULT '[]',
                wins_json TEXT DEFAULT '[]',
                lessons TEXT DEFAULT '',
                content TEXT DEFAULT '',
                tags_json TEXT DEFAULT '[]',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_journal_entries_user ON journal_entries(user_id);
            CREATE INDEX IF NOT EXISTS idx_journal_entries_date ON journal_entries(date);

            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                title TEXT NOT NULL,
                author TEXT DEFAULT '',
                genre TEXT DEFAULT '',
                page_count INTEGER DEFAULT 0,
                current_page INTEGER DEFAULT 0,
                status TEXT DEFAULT 'to-read',
                rating INTEGER,
                review TEXT DEFAULT '',
                cover_url TEXT DEFAULT '',
                format TEXT DEFAULT 'physical',
                started_at TEXT,
                finished_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_books_user ON books(user_id);
            CREATE INDEX IF NOT EXISTS idx_books_status ON books(status);

            CREATE TABLE IF NOT EXISTS reading_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                pages_read INTEGER NOT NULL DEFAULT 0,
                date TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_reading_sessions_book ON reading_sessions(book_id);

            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                title TEXT NOT NULL,
                body TEXT DEFAULT '',
                tags_json TEXT DEFAULT '[]',
                folder TEXT DEFAULT '',
                pinned INTEGER DEFAULT 0,
                archived INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id);
            CREATE INDEX IF NOT EXISTS idx_notes_pinned ON notes(pinned);
        """)
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, description) VALUES (18, 'Journal, Books, Notes modules')"
        )
        conn.commit()
        print("  Migration 18: Journal, Books, Notes modules")
