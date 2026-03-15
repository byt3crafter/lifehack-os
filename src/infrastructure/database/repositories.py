"""Repository implementations for database access."""
from datetime import datetime, date
from typing import List, Optional
import sqlite3

from .connection import get_connection
from ...domain.entities import (
    Habit, HabitCompletion, CompletionStatus, Frequency,
    Project, Milestone, Task, ProjectStatus,
    DailyCheckin, WalkLog,
    ReplacementAction, ReplacementLog,
    UserStats, Streak, StreakType, PointLedgerEntry,
    DeepWorkSession,
)


class HabitRepository:
    """Repository for habit operations."""
    
    def __init__(self):
        self.conn = get_connection()
    
    def get_all(self, active_only: bool = True) -> List[Habit]:
        query = "SELECT * FROM habits"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY category, name"
        
        rows = self.conn.execute(query).fetchall()
        return [self._row_to_habit(row) for row in rows]
    
    def get_by_id(self, habit_id: int) -> Optional[Habit]:
        row = self.conn.execute(
            "SELECT * FROM habits WHERE id = ?", (habit_id,)
        ).fetchone()
        return self._row_to_habit(row) if row else None
    
    def create(self, habit: Habit) -> Habit:
        cursor = self.conn.execute(
            """INSERT INTO habits (name, category, frequency, difficulty, points, active)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (habit.name, habit.category, habit.frequency.value, 
             habit.difficulty, habit.points, habit.active)
        )
        self.conn.commit()
        habit.id = cursor.lastrowid
        return habit
    
    def update(self, habit: Habit) -> None:
        self.conn.execute(
            """UPDATE habits SET name=?, category=?, frequency=?, 
               difficulty=?, points=?, active=? WHERE id=?""",
            (habit.name, habit.category, habit.frequency.value,
             habit.difficulty, habit.points, habit.active, habit.id)
        )
        self.conn.commit()
    
    def delete(self, habit_id: int) -> None:
        self.conn.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
        self.conn.commit()
    
    def log_completion(self, completion: HabitCompletion) -> HabitCompletion:
        cursor = self.conn.execute(
            """INSERT INTO habit_completions (habit_id, completed_at, status, points_earned, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (completion.habit_id, completion.completed_at.isoformat(),
             completion.status.value, completion.points_earned, completion.notes)
        )
        self.conn.commit()
        completion.id = cursor.lastrowid
        return completion
    
    def get_completions_for_date(self, target_date: date) -> List[HabitCompletion]:
        date_str = target_date.isoformat()
        rows = self.conn.execute(
            """SELECT * FROM habit_completions 
               WHERE date(completed_at) = ? ORDER BY completed_at""",
            (date_str,)
        ).fetchall()
        return [self._row_to_completion(row) for row in rows]
    
    def get_streak(self, habit_id: int) -> int:
        """Calculate current streak for a habit."""
        rows = self.conn.execute(
            """SELECT DISTINCT date(completed_at) as d FROM habit_completions
               WHERE habit_id = ? AND status = 'complete'
               ORDER BY d DESC LIMIT 365""",
            (habit_id,)
        ).fetchall()
        
        if not rows:
            return 0
        
        streak = 0
        expected = date.today()
        
        for row in rows:
            completion_date = date.fromisoformat(row['d'])
            if completion_date == expected:
                streak += 1
                expected = date.fromordinal(expected.toordinal() - 1)
            elif completion_date < expected:
                break
        
        return streak
    
    def _row_to_habit(self, row: sqlite3.Row) -> Habit:
        return Habit(
            id=row['id'],
            name=row['name'],
            category=row['category'],
            frequency=Frequency(row['frequency']),
            difficulty=row['difficulty'],
            points=row['points'],
            active=bool(row['active']),
            created_at=datetime.fromisoformat(row['created_at'])
        )
    
    def _row_to_completion(self, row: sqlite3.Row) -> HabitCompletion:
        return HabitCompletion(
            id=row['id'],
            habit_id=row['habit_id'],
            completed_at=datetime.fromisoformat(row['completed_at']),
            status=CompletionStatus(row['status']),
            points_earned=row['points_earned'],
            notes=row['notes'] or ""
        )


class ProjectRepository:
    """Repository for project operations."""
    
    def __init__(self):
        self.conn = get_connection()
    
    def get_all(self, include_completed: bool = False) -> List[Project]:
        query = "SELECT * FROM projects"
        if not include_completed:
            query += " WHERE status != 'complete' AND status != 'archived'"
        query += " ORDER BY created_at DESC"
        
        rows = self.conn.execute(query).fetchall()
        projects = []
        for row in rows:
            project = self._row_to_project(row)
            project.milestones = self._get_milestones(project.id)
            projects.append(project)
        return projects
    
    def get_by_id(self, project_id: int) -> Optional[Project]:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if not row:
            return None
        project = self._row_to_project(row)
        project.milestones = self._get_milestones(project.id)
        return project
    
    def create(self, project: Project) -> Project:
        cursor = self.conn.execute(
            """INSERT INTO projects (name, description, status, points_start, points_complete)
               VALUES (?, ?, ?, ?, ?)""",
            (project.name, project.description, project.status.value,
             project.points_start, project.points_complete)
        )
        self.conn.commit()
        project.id = cursor.lastrowid
        return project
    
    def update(self, project: Project) -> None:
        completed_at = project.completed_at.isoformat() if project.completed_at else None
        self.conn.execute(
            """UPDATE projects SET name=?, description=?, status=?, 
               points_start=?, points_complete=?, completed_at=? WHERE id=?""",
            (project.name, project.description, project.status.value,
             project.points_start, project.points_complete, completed_at, project.id)
        )
        self.conn.commit()
    
    def add_milestone(self, milestone: Milestone) -> Milestone:
        cursor = self.conn.execute(
            """INSERT INTO milestones (project_id, name, points, sort_order)
               VALUES (?, ?, ?, ?)""",
            (milestone.project_id, milestone.name, milestone.points, milestone.order)
        )
        self.conn.commit()
        milestone.id = cursor.lastrowid
        return milestone
    
    def complete_milestone(self, milestone_id: int) -> None:
        self.conn.execute(
            "UPDATE milestones SET completed_at = ? WHERE id = ?",
            (datetime.now().isoformat(), milestone_id)
        )
        self.conn.commit()
    
    def _get_milestones(self, project_id: int) -> List[Milestone]:
        rows = self.conn.execute(
            "SELECT * FROM milestones WHERE project_id = ? ORDER BY sort_order",
            (project_id,)
        ).fetchall()
        milestones = []
        for row in rows:
            milestone = Milestone(
                id=row['id'],
                project_id=row['project_id'],
                name=row['name'],
                points=row['points'],
                order=row['sort_order'],
                completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None
            )
            milestone.tasks = self._get_tasks(milestone.id)
            milestones.append(milestone)
        return milestones
    
    def _get_tasks(self, milestone_id: int) -> List[Task]:
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE milestone_id = ? ORDER BY sort_order",
            (milestone_id,)
        ).fetchall()
        return [
            Task(
                id=row['id'],
                milestone_id=row['milestone_id'],
                name=row['name'],
                points=row['points'],
                order=row['sort_order'],
                completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None
            )
            for row in rows
        ]
    
    def _row_to_project(self, row: sqlite3.Row) -> Project:
        return Project(
            id=row['id'],
            name=row['name'],
            description=row['description'] or "",
            status=ProjectStatus(row['status']),
            points_start=row['points_start'],
            points_complete=row['points_complete'],
            created_at=datetime.fromisoformat(row['created_at']),
            completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None
        )


class CheckinRepository:
    """Repository for daily check-in operations."""
    
    def __init__(self):
        self.conn = get_connection()
    
    def get_for_date(self, target_date: date) -> Optional[DailyCheckin]:
        row = self.conn.execute(
            "SELECT * FROM daily_checkins WHERE date = ?",
            (target_date.isoformat(),)
        ).fetchone()
        return self._row_to_checkin(row) if row else None
    
    def get_recent(self, days: int = 7) -> List[DailyCheckin]:
        rows = self.conn.execute(
            """SELECT * FROM daily_checkins 
               ORDER BY date DESC LIMIT ?""",
            (days,)
        ).fetchall()
        return [self._row_to_checkin(row) for row in rows]
    
    def save(self, checkin: DailyCheckin) -> DailyCheckin:
        existing = self.get_for_date(checkin.date)
        if existing:
            self.conn.execute(
                """UPDATE daily_checkins SET completed_today=?, avoided_alcohol=?,
                   worked_on_future=?, mood=?, energy=?, improvement_note=?, points_earned=?
                   WHERE date=?""",
                (checkin.completed_today, checkin.avoided_alcohol, checkin.worked_on_future,
                 checkin.mood, checkin.energy, checkin.improvement_note, 
                 checkin.points_earned, checkin.date.isoformat())
            )
            checkin.id = existing.id
        else:
            cursor = self.conn.execute(
                """INSERT INTO daily_checkins 
                   (date, completed_today, avoided_alcohol, worked_on_future, mood, energy, improvement_note, points_earned)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (checkin.date.isoformat(), checkin.completed_today, checkin.avoided_alcohol,
                 checkin.worked_on_future, checkin.mood, checkin.energy,
                 checkin.improvement_note, checkin.points_earned)
            )
            checkin.id = cursor.lastrowid
        self.conn.commit()
        return checkin
    
    def get_sobriety_streak(self) -> int:
        """Calculate current sobriety streak from check-ins."""
        rows = self.conn.execute(
            """SELECT date, avoided_alcohol FROM daily_checkins
               ORDER BY date DESC LIMIT 365"""
        ).fetchall()
        
        streak = 0
        for row in rows:
            if row['avoided_alcohol']:
                streak += 1
            else:
                break
        return streak
    
    def _row_to_checkin(self, row: sqlite3.Row) -> DailyCheckin:
        return DailyCheckin(
            id=row['id'],
            date=date.fromisoformat(row['date']),
            completed_today=row['completed_today'] or "",
            avoided_alcohol=bool(row['avoided_alcohol']),
            worked_on_future=bool(row['worked_on_future']),
            mood=row['mood'],
            energy=row['energy'],
            improvement_note=row['improvement_note'] or "",
            points_earned=row['points_earned'],
            created_at=datetime.fromisoformat(row['created_at'])
        )


class WalkRepository:
    """Repository for walk log operations."""
    
    def __init__(self):
        self.conn = get_connection()
    
    def get_recent(self, limit: int = 10) -> List[WalkLog]:
        rows = self.conn.execute(
            "SELECT * FROM walk_logs ORDER BY logged_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [self._row_to_walk(row) for row in rows]
    
    def log(self, walk: WalkLog) -> WalkLog:
        cursor = self.conn.execute(
            """INSERT INTO walk_logs 
               (logged_at, distance_km, duration_minutes, mood_before, mood_after, points_earned, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (walk.logged_at.isoformat(), walk.distance_km, walk.duration_minutes,
             walk.mood_before, walk.mood_after, walk.points_earned, walk.notes)
        )
        self.conn.commit()
        walk.id = cursor.lastrowid
        return walk
    
    def get_weekly_stats(self) -> dict:
        row = self.conn.execute(
            """SELECT COUNT(*) as count, SUM(distance_km) as total_km, 
                      SUM(duration_minutes) as total_minutes, SUM(points_earned) as points
               FROM walk_logs WHERE logged_at >= date('now', '-7 days')"""
        ).fetchone()
        return {
            'count': row['count'] or 0,
            'total_km': row['total_km'] or 0,
            'total_minutes': row['total_minutes'] or 0,
            'points': row['points'] or 0
        }
    
    def _row_to_walk(self, row: sqlite3.Row) -> WalkLog:
        return WalkLog(
            id=row['id'],
            logged_at=datetime.fromisoformat(row['logged_at']),
            distance_km=row['distance_km'],
            duration_minutes=row['duration_minutes'],
            mood_before=row['mood_before'],
            mood_after=row['mood_after'],
            points_earned=row['points_earned'],
            notes=row['notes'] or ""
        )


class ReplacementRepository:
    """Repository for replacement action operations."""
    
    def __init__(self):
        self.conn = get_connection()
    
    def get_all_actions(self, active_only: bool = True) -> List[ReplacementAction]:
        query = "SELECT * FROM replacement_actions"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY category, name"
        
        rows = self.conn.execute(query).fetchall()
        return [
            ReplacementAction(
                id=row['id'], name=row['name'],
                category=row['category'], points=row['points'],
                active=bool(row['active'])
            )
            for row in rows
        ]
    
    def create_action(self, action: ReplacementAction) -> ReplacementAction:
        cursor = self.conn.execute(
            "INSERT INTO replacement_actions (name, category, points) VALUES (?, ?, ?)",
            (action.name, action.category, action.points)
        )
        self.conn.commit()
        action.id = cursor.lastrowid
        return action
    
    def log_replacement(self, log: ReplacementLog) -> ReplacementLog:
        cursor = self.conn.execute(
            """INSERT INTO replacement_logs (action_id, logged_at, urge_level, points_earned, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (log.action_id, log.logged_at.isoformat(), log.urge_level,
             log.points_earned, log.notes)
        )
        self.conn.commit()
        log.id = cursor.lastrowid
        return log
    
    def get_recent_logs(self, limit: int = 10) -> List[ReplacementLog]:
        rows = self.conn.execute(
            """SELECT rl.*, ra.name as action_name FROM replacement_logs rl
               JOIN replacement_actions ra ON rl.action_id = ra.id
               ORDER BY rl.logged_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        return [
            ReplacementLog(
                id=row['id'], action_id=row['action_id'],
                action_name=row['action_name'],
                logged_at=datetime.fromisoformat(row['logged_at']),
                urge_level=row['urge_level'],
                points_earned=row['points_earned'],
                notes=row['notes'] or ""
            )
            for row in rows
        ]


class StatsRepository:
    """Repository for user stats and point ledger."""
    
    def __init__(self):
        self.conn = get_connection()
    
    def get_stats(self) -> UserStats:
        row = self.conn.execute("SELECT * FROM user_stats WHERE id = 1").fetchone()
        return UserStats(
            id=1,
            total_xp=row['total_xp'],
            level=row['level'],
            sobriety_start_date=date.fromisoformat(row['sobriety_start_date']) if row['sobriety_start_date'] else None,
            created_at=datetime.fromisoformat(row['created_at'])
        )
    
    def update_stats(self, stats: UserStats) -> None:
        sobriety = stats.sobriety_start_date.isoformat() if stats.sobriety_start_date else None
        self.conn.execute(
            "UPDATE user_stats SET total_xp=?, level=?, sobriety_start_date=? WHERE id=1",
            (stats.total_xp, stats.level, sobriety)
        )
        self.conn.commit()
    
    def add_points(self, source_type: str, points: int, reason: str, source_id: int = None) -> None:
        """Add points and log to ledger."""
        # Update total XP
        self.conn.execute(
            "UPDATE user_stats SET total_xp = total_xp + ? WHERE id = 1",
            (points,)
        )
        # Recalculate level
        stats = self.get_stats()
        new_level = stats.calculate_level()
        if new_level != stats.level:
            self.conn.execute(
                "UPDATE user_stats SET level = ? WHERE id = 1",
                (new_level,)
            )
        # Log to ledger
        self.conn.execute(
            """INSERT INTO point_ledger (source_type, source_id, points, reason)
               VALUES (?, ?, ?, ?)""",
            (source_type, source_id, points, reason)
        )
        self.conn.commit()
    
    def get_ledger(self, limit: int = 50) -> List[PointLedgerEntry]:
        rows = self.conn.execute(
            "SELECT * FROM point_ledger ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [
            PointLedgerEntry(
                id=row['id'],
                timestamp=datetime.fromisoformat(row['timestamp']),
                source_type=row['source_type'],
                source_id=row['source_id'],
                points=row['points'],
                reason=row['reason'] or ""
            )
            for row in rows
        ]
    
    def get_weekly_summary(self) -> dict:
        """Get points earned this week by category."""
        rows = self.conn.execute(
            """SELECT source_type, SUM(points) as total
               FROM point_ledger 
               WHERE timestamp >= date('now', '-7 days')
               GROUP BY source_type"""
        ).fetchall()
        return {row['source_type']: row['total'] for row in rows}


class DeepWorkRepository:
    """Repository for deep work session operations."""
    
    def __init__(self):
        self.conn = get_connection()
    
    def get_active(self) -> Optional[DeepWorkSession]:
        row = self.conn.execute(
            """SELECT dw.*, p.name as project_name FROM deep_work_sessions dw
               LEFT JOIN projects p ON dw.project_id = p.id
               WHERE dw.ended_at IS NULL
               ORDER BY dw.started_at DESC LIMIT 1"""
        ).fetchone()
        return self._row_to_session(row) if row else None
    
    def start(self, session: DeepWorkSession) -> DeepWorkSession:
        cursor = self.conn.execute(
            "INSERT INTO deep_work_sessions (project_id, notes) VALUES (?, ?)",
            (session.project_id, session.notes)
        )
        self.conn.commit()
        session.id = cursor.lastrowid
        return session
    
    def end(self, session: DeepWorkSession) -> None:
        self.conn.execute(
            """UPDATE deep_work_sessions 
               SET ended_at=?, duration_minutes=?, points_earned=?
               WHERE id=?""",
            (session.ended_at.isoformat(), session.duration_minutes,
             session.points_earned, session.id)
        )
        self.conn.commit()
    
    def get_recent(self, limit: int = 10) -> List[DeepWorkSession]:
        rows = self.conn.execute(
            """SELECT dw.*, p.name as project_name FROM deep_work_sessions dw
               LEFT JOIN projects p ON dw.project_id = p.id
               WHERE dw.ended_at IS NOT NULL
               ORDER BY dw.started_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        return [self._row_to_session(row) for row in rows]
    
    def get_today_count(self) -> int:
        row = self.conn.execute(
            """SELECT COUNT(*) as count FROM deep_work_sessions
               WHERE date(started_at) = date('now') AND ended_at IS NOT NULL"""
        ).fetchone()
        return row['count']
    
    def _row_to_session(self, row: sqlite3.Row) -> DeepWorkSession:
        return DeepWorkSession(
            id=row['id'],
            project_id=row['project_id'],
            project_name=row['project_name'] or "General",
            started_at=datetime.fromisoformat(row['started_at']),
            ended_at=datetime.fromisoformat(row['ended_at']) if row['ended_at'] else None,
            duration_minutes=row['duration_minutes'] or 0,
            points_earned=row['points_earned'] or 0,
            notes=row['notes'] or ""
        )
