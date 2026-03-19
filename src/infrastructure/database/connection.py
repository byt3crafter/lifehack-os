"""Database connection and initialization.

MULTI-USER CONVENTION: Every table that stores user-specific data MUST include
a ``user_id INTEGER REFERENCES users(id)`` column.  System/global tables
(users, schema_version, app_settings, habit_templates, app_log, openclaw_log,
ai_usage_log) are exempt.
"""
import sqlite3
from pathlib import Path
from typing import Optional

_connection: Optional[sqlite3.Connection] = None

def get_db_path() -> Path:
    """Get the database file path."""
    db_dir = Path(__file__).parent.parent.parent.parent / "data"
    db_dir.mkdir(exist_ok=True)
    return db_dir / "lifehack.db"


def get_connection() -> sqlite3.Connection:
    """Get or create the database connection."""
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(get_db_path(), check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA foreign_keys = ON")
    return _connection


def init_database() -> None:
    """Initialize the database schema.

    All user-data tables include ``user_id`` for multi-user isolation.
    """
    conn = get_connection()

    conn.executescript("""
        -- Habits
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'health',
            frequency TEXT NOT NULL DEFAULT 'daily',
            difficulty INTEGER NOT NULL DEFAULT 1,
            points INTEGER NOT NULL DEFAULT 10,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS habit_completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            habit_id INTEGER NOT NULL,
            completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'complete',
            points_earned INTEGER NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '',
            FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE
        );

        -- Projects
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            points_start INTEGER NOT NULL DEFAULT 25,
            points_complete INTEGER NOT NULL DEFAULT 100,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            points INTEGER NOT NULL DEFAULT 50,
            sort_order INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            milestone_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            points INTEGER NOT NULL DEFAULT 5,
            sort_order INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT,
            FOREIGN KEY (milestone_id) REFERENCES milestones(id) ON DELETE CASCADE
        );

        -- Deep Work
        CREATE TABLE IF NOT EXISTS deep_work_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            project_id INTEGER,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ended_at TEXT,
            duration_minutes INTEGER DEFAULT 0,
            points_earned INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
        );

        -- Check-ins
        CREATE TABLE IF NOT EXISTS daily_checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            date TEXT NOT NULL,
            completed_today TEXT DEFAULT '',
            avoided_alcohol INTEGER NOT NULL DEFAULT 1,
            worked_on_future INTEGER NOT NULL DEFAULT 0,
            mood INTEGER NOT NULL DEFAULT 3,
            energy INTEGER NOT NULL DEFAULT 3,
            improvement_note TEXT DEFAULT '',
            points_earned INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        -- Walks
        CREATE TABLE IF NOT EXISTS walk_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            logged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            distance_km REAL NOT NULL DEFAULT 0,
            duration_minutes INTEGER NOT NULL DEFAULT 0,
            mood_before INTEGER NOT NULL DEFAULT 3,
            mood_after INTEGER NOT NULL DEFAULT 3,
            points_earned INTEGER NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '',
            location TEXT DEFAULT '',
            movement_type TEXT DEFAULT 'exercise'
        );

        -- Replacement Actions
        CREATE TABLE IF NOT EXISTS replacement_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            points INTEGER NOT NULL DEFAULT 30,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS replacement_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            action_id INTEGER NOT NULL,
            logged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            urge_level INTEGER NOT NULL DEFAULT 3,
            points_earned INTEGER NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '',
            FOREIGN KEY (action_id) REFERENCES replacement_actions(id) ON DELETE CASCADE
        );

        -- Stats & Streaks (user_stats keyed by user_id)
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY REFERENCES users(id),
            total_xp INTEGER NOT NULL DEFAULT 0,
            level INTEGER NOT NULL DEFAULT 1,
            sobriety_start_date TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS streaks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            type TEXT NOT NULL,
            reference_id INTEGER,
            current_count INTEGER NOT NULL DEFAULT 0,
            best_count INTEGER NOT NULL DEFAULT 0,
            last_date TEXT
        );

        CREATE TABLE IF NOT EXISTS point_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source_type TEXT NOT NULL,
            source_id INTEGER,
            points INTEGER NOT NULL,
            reason TEXT DEFAULT ''
        );

        -- Food Logs
        CREATE TABLE IF NOT EXISTS food_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            logged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            meal_type TEXT NOT NULL DEFAULT 'meal',
            description TEXT DEFAULT '',
            calories REAL,
            protein_g REAL,
            carbs_g REAL,
            fat_g REAL,
            image_path TEXT,
            ai_analysis TEXT,
            notes TEXT DEFAULT '',
            rating INTEGER,
            mood_after INTEGER
        );

        -- Fasting Logs
        CREATE TABLE IF NOT EXISTS fasting_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            start_at TEXT NOT NULL,
            end_at TEXT,
            target_hours INTEGER DEFAULT 16,
            status TEXT DEFAULT 'active',
            mood_start INTEGER DEFAULT 3,
            mood_end INTEGER,
            notes TEXT DEFAULT ''
        );

        -- Wishlist / Discover
        CREATE TABLE IF NOT EXISTS wishlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            title TEXT NOT NULL,
            location TEXT DEFAULT '',
            description TEXT DEFAULT '',
            category TEXT DEFAULT 'place',
            completed INTEGER DEFAULT 0,
            status TEXT DEFAULT 'want',
            rating INTEGER,
            completed_at TEXT,
            photos_json TEXT DEFAULT '[]',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- Finance
        CREATE TABLE IF NOT EXISTS finance_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            category TEXT NOT NULL,
            monthly_limit REAL,
            description TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS finance_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
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
            user_id INTEGER REFERENCES users(id),
            question TEXT NOT NULL,
            advice TEXT NOT NULL,
            amount REAL,
            category TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS savings_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            name TEXT NOT NULL,
            icon TEXT DEFAULT '🎯',
            target_amount REAL NOT NULL,
            current_amount REAL DEFAULT 0,
            firefly_account_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- Challenges
        CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            name TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            target_days INTEGER,
            start_date TEXT NOT NULL,
            end_date TEXT,
            status TEXT DEFAULT 'active',
            check_in_frequency TEXT DEFAULT 'daily',
            last_check_in TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS challenge_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            challenge_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            note TEXT,
            logged_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (challenge_id) REFERENCES challenges(id)
        );

        -- App Settings (GLOBAL — not user-scoped)
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- Per-user settings (overrides app_settings per user)
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, key)
        );

        -- Per-user integration credentials
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

        -- OpenClaw Connection Log (GLOBAL)
        CREATE TABLE IF NOT EXISTS openclaw_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            detail TEXT DEFAULT '',
            ip_address TEXT DEFAULT '',
            logged_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- AI Insights
        CREATE TABLE IF NOT EXISTS ai_insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            insight_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            priority INTEGER DEFAULT 0,
            dismissed INTEGER DEFAULT 0
        );

        -- AI Usage Log (GLOBAL — tracks costs system-wide)
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

        -- Chat Messages
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            context_summary TEXT DEFAULT '',
            tokens_used INTEGER DEFAULT 0,
            provider TEXT DEFAULT '',
            model TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_messages(created_at);

        -- App Log (GLOBAL)
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

        -- Habit phases
        CREATE TABLE IF NOT EXISTS habit_phases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
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

        -- Micro tasks
        CREATE TABLE IF NOT EXISTS habit_micro_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            phase_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            verification_rule TEXT DEFAULT '{"type": "manual"}',
            FOREIGN KEY (phase_id) REFERENCES habit_phases(id) ON DELETE CASCADE
        );

        -- Micro task completions
        CREATE TABLE IF NOT EXISTS micro_task_completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            micro_task_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            verified_by TEXT NOT NULL DEFAULT 'manual',
            verified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            current_value REAL,
            FOREIGN KEY (micro_task_id) REFERENCES habit_micro_tasks(id) ON DELETE CASCADE,
            UNIQUE(micro_task_id, date)
        );

        -- Habit strength
        CREATE TABLE IF NOT EXISTS habit_strength (
            habit_id INTEGER PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            strength REAL DEFAULT 0,
            peak_strength REAL DEFAULT 0,
            last_completed TEXT,
            last_missed TEXT,
            total_completions INTEGER DEFAULT 0,
            total_misses INTEGER DEFAULT 0,
            FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE
        );

        -- Habit miss log
        CREATE TABLE IF NOT EXISTS habit_miss_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            habit_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            reason TEXT DEFAULT '',
            blocker TEXT DEFAULT '',
            logged_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE
        );

        -- Habit stacks
        CREATE TABLE IF NOT EXISTS habit_stacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            trigger_text TEXT NOT NULL,
            habit_id INTEGER NOT NULL,
            FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE
        );

        -- Habit templates (GLOBAL — system templates)
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

        -- Deep Work Projects
        CREATE TABLE IF NOT EXISTS deep_work_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            color TEXT DEFAULT '#4f80ff',
            active INTEGER DEFAULT 1,
            total_minutes INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- Finance Stage 2
        CREATE TABLE IF NOT EXISTS finance_recurring (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
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

        CREATE TABLE IF NOT EXISTS finance_anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
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

        CREATE TABLE IF NOT EXISTS finance_digests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
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
            UNIQUE(user_id, week_start)
        );

        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_habit_completions_date ON habit_completions(completed_at);
        CREATE INDEX IF NOT EXISTS idx_checkins_date ON daily_checkins(date);
        CREATE INDEX IF NOT EXISTS idx_walks_date ON walk_logs(logged_at);
        CREATE INDEX IF NOT EXISTS idx_ledger_timestamp ON point_ledger(timestamp);
        CREATE INDEX IF NOT EXISTS idx_food_date ON food_logs(logged_at);
        CREATE INDEX IF NOT EXISTS idx_challenges_status ON challenges(status);
        CREATE INDEX IF NOT EXISTS idx_ai_usage_timestamp ON ai_usage_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_app_log_timestamp ON app_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_habit_phases_habit ON habit_phases(habit_id);
        CREATE INDEX IF NOT EXISTS idx_habit_micro_tasks_phase ON habit_micro_tasks(phase_id);
        CREATE INDEX IF NOT EXISTS idx_habit_miss_log_habit ON habit_miss_log(habit_id);
        CREATE INDEX IF NOT EXISTS idx_habit_stacks_habit ON habit_stacks(habit_id);
        CREATE INDEX IF NOT EXISTS idx_micro_task_completions_task ON micro_task_completions(micro_task_id);
        CREATE INDEX IF NOT EXISTS idx_micro_task_completions_date ON micro_task_completions(date);
        CREATE INDEX IF NOT EXISTS idx_finance_log_date ON finance_log(date);
        CREATE INDEX IF NOT EXISTS idx_finance_log_category ON finance_log(category);
        CREATE INDEX IF NOT EXISTS idx_finance_advice_created ON finance_advice(created_at);
        CREATE INDEX IF NOT EXISTS idx_savings_goals_created ON savings_goals(created_at);
        CREATE INDEX IF NOT EXISTS idx_user_integrations_user ON user_integrations(user_id);
    """)

    conn.commit()

    # Run pending migrations (adds users table, schema_version table, etc.)
    from .migrations import run_migrations
    run_migrations(conn)
