"""Database connection and initialization."""
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
    """Initialize the database schema."""
    conn = get_connection()
    
    conn.executescript("""
        -- Habits
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            points INTEGER NOT NULL DEFAULT 50,
            sort_order INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            date TEXT NOT NULL UNIQUE,
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
            logged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            distance_km REAL NOT NULL DEFAULT 0,
            duration_minutes INTEGER NOT NULL DEFAULT 0,
            mood_before INTEGER NOT NULL DEFAULT 3,
            mood_after INTEGER NOT NULL DEFAULT 3,
            points_earned INTEGER NOT NULL DEFAULT 0,
            notes TEXT DEFAULT ''
        );
        
        -- Replacement Actions
        CREATE TABLE IF NOT EXISTS replacement_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            points INTEGER NOT NULL DEFAULT 30,
            active INTEGER NOT NULL DEFAULT 1
        );
        
        CREATE TABLE IF NOT EXISTS replacement_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_id INTEGER NOT NULL,
            logged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            urge_level INTEGER NOT NULL DEFAULT 3,
            points_earned INTEGER NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '',
            FOREIGN KEY (action_id) REFERENCES replacement_actions(id) ON DELETE CASCADE
        );
        
        -- Stats & Streaks
        CREATE TABLE IF NOT EXISTS user_stats (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            total_xp INTEGER NOT NULL DEFAULT 0,
            level INTEGER NOT NULL DEFAULT 1,
            sobriety_start_date TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS streaks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            reference_id INTEGER,
            current_count INTEGER NOT NULL DEFAULT 0,
            best_count INTEGER NOT NULL DEFAULT 0,
            last_date TEXT
        );
        
        CREATE TABLE IF NOT EXISTS point_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source_type TEXT NOT NULL,
            source_id INTEGER,
            points INTEGER NOT NULL,
            reason TEXT DEFAULT ''
        );
        
        -- Initialize user stats if not exists
        INSERT OR IGNORE INTO user_stats (id, total_xp, level) VALUES (1, 0, 1);
        
        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_habit_completions_date ON habit_completions(completed_at);
        CREATE INDEX IF NOT EXISTS idx_checkins_date ON daily_checkins(date);
        CREATE INDEX IF NOT EXISTS idx_walks_date ON walk_logs(logged_at);
        CREATE INDEX IF NOT EXISTS idx_ledger_timestamp ON point_ledger(timestamp);
    """)
    
    conn.commit()
