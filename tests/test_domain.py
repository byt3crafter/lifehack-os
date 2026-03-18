"""Tests for domain entities — pure Python, no database or Flask required."""
import sys
from pathlib import Path
from datetime import date, datetime, timedelta

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.entities.habit import Habit, HabitCompletion, CompletionStatus, Frequency
from src.domain.entities.checkin import DailyCheckin
from src.domain.entities.stats import UserStats, Streak, StreakType
from src.domain.entities.walk import WalkLog
from src.domain.entities.deep_work import DeepWorkSession
from src.domain.entities.replacement import ReplacementAction, ReplacementLog
from src.domain.entities.project import Project, Milestone, Task, ProjectStatus


# ---------------------------------------------------------------------------
# Habit
# ---------------------------------------------------------------------------

class TestHabit:
    def test_default_values(self):
        habit = Habit(name="Meditate")
        assert habit.name == "Meditate"
        assert habit.category == "health"
        assert habit.frequency == Frequency.DAILY
        assert habit.difficulty == 1
        assert habit.points == 10
        assert habit.active is True
        assert habit.id is None

    def test_calculate_points_base(self):
        # points=10, difficulty=2 → base = 20, no streak bonus
        habit = Habit(name="Run", points=10, difficulty=2)
        assert habit.calculate_points(streak=0) == 20

    def test_calculate_points_below_streak_threshold(self):
        habit = Habit(name="Run", points=10, difficulty=2)
        # streak=6 is below default threshold of 7
        assert habit.calculate_points(streak=6) == 20

    def test_calculate_points_with_streak_multiplier(self):
        habit = Habit(name="Run", points=10, difficulty=2)
        # streak=7 hits default threshold; base=20, multiplier=1.5 → 30
        assert habit.calculate_points(streak=7) == 30

    def test_calculate_points_high_streak(self):
        habit = Habit(name="Run", points=10, difficulty=2)
        assert habit.calculate_points(streak=30) == 30

    def test_calculate_points_custom_multiplier(self):
        habit = Habit(name="Run", points=10, difficulty=1)
        # base=10, threshold=3, multiplier=2.0
        assert habit.calculate_points(streak=3, multiplier_threshold=3, multiplier=2.0) == 20

    def test_habit_completion_date_property(self):
        dt = datetime(2024, 6, 15, 10, 30)
        completion = HabitCompletion(habit_id=1, completed_at=dt)
        assert completion.date == date(2024, 6, 15)

    def test_habit_completion_defaults(self):
        completion = HabitCompletion(habit_id=5)
        assert completion.status == CompletionStatus.COMPLETE
        assert completion.points_earned == 0
        assert completion.notes == ""


# ---------------------------------------------------------------------------
# DailyCheckin
# ---------------------------------------------------------------------------

class TestDailyCheckin:
    def test_calculate_points_base_only(self):
        checkin = DailyCheckin(avoided_alcohol=False, worked_on_future=False)
        assert checkin.calculate_points(base=15, sobriety_bonus=25, future_bonus=10) == 15

    def test_calculate_points_with_sobriety_bonus(self):
        checkin = DailyCheckin(avoided_alcohol=True, worked_on_future=False)
        assert checkin.calculate_points(base=15, sobriety_bonus=25, future_bonus=10) == 40

    def test_calculate_points_with_future_work_bonus(self):
        checkin = DailyCheckin(avoided_alcohol=False, worked_on_future=True)
        assert checkin.calculate_points(base=15, sobriety_bonus=25, future_bonus=10) == 25

    def test_calculate_points_all_bonuses(self):
        checkin = DailyCheckin(avoided_alcohol=True, worked_on_future=True)
        assert checkin.calculate_points(base=15, sobriety_bonus=25, future_bonus=10) == 50

    def test_default_field_values(self):
        checkin = DailyCheckin()
        assert checkin.mood == 3
        assert checkin.energy == 3
        assert checkin.avoided_alcohol is True
        assert checkin.worked_on_future is False


# ---------------------------------------------------------------------------
# UserStats
# ---------------------------------------------------------------------------

class TestUserStats:
    def test_xp_for_next_level_at_zero_xp(self):
        stats = UserStats(total_xp=0, level=1)
        # level 1 → next threshold = 1*500 = 500; needs 500 more XP
        assert stats.xp_for_next_level(xp_per_level=500) == 500

    def test_xp_for_next_level_mid_level(self):
        stats = UserStats(total_xp=300, level=1)
        # next threshold = 500; needs 200 more
        assert stats.xp_for_next_level(xp_per_level=500) == 200

    def test_xp_for_next_level_at_level_boundary(self):
        stats = UserStats(total_xp=500, level=2)
        # next threshold = 2*500 = 1000; needs 500 more
        assert stats.xp_for_next_level(xp_per_level=500) == 500

    def test_calculate_level_from_xp(self):
        stats = UserStats(total_xp=0)
        assert stats.calculate_level(xp_per_level=500) == 1

    def test_calculate_level_at_threshold(self):
        stats = UserStats(total_xp=500)
        assert stats.calculate_level(xp_per_level=500) == 2

    def test_calculate_level_high_xp(self):
        stats = UserStats(total_xp=2499)
        assert stats.calculate_level(xp_per_level=500) == 5

    def test_add_xp_updates_level(self):
        stats = UserStats(total_xp=490, level=1)
        stats.add_xp(20)
        assert stats.total_xp == 510
        assert stats.level == 2

    def test_sobriety_days_no_start_date(self):
        stats = UserStats()
        assert stats.sobriety_days == 0

    def test_sobriety_days_with_start_date(self):
        start = date.today() - timedelta(days=10)
        stats = UserStats(sobriety_start_date=start)
        assert stats.sobriety_days == 10


# ---------------------------------------------------------------------------
# Streak
# ---------------------------------------------------------------------------

class TestStreak:
    def test_increment_from_none(self):
        streak = Streak(type=StreakType.HABIT)
        today = date.today()
        streak.increment(for_date=today)
        assert streak.current_count == 1
        assert streak.best_count == 1
        assert streak.last_date == today

    def test_increment_consecutive_days(self):
        streak = Streak(type=StreakType.HABIT)
        d0 = date(2024, 1, 1)
        streak.increment(for_date=d0)
        streak.increment(for_date=d0 + timedelta(days=1))
        assert streak.current_count == 2
        assert streak.best_count == 2

    def test_increment_gap_resets_streak(self):
        streak = Streak(type=StreakType.HABIT)
        d0 = date(2024, 1, 1)
        streak.increment(for_date=d0)
        streak.increment(for_date=d0 + timedelta(days=3))
        assert streak.current_count == 1
        assert streak.best_count == 1

    def test_increment_same_day_no_change(self):
        streak = Streak(type=StreakType.HABIT)
        today = date.today()
        streak.increment(for_date=today)
        streak.increment(for_date=today)
        assert streak.current_count == 1

    def test_best_count_preserved_after_reset(self):
        streak = Streak(type=StreakType.HABIT)
        for i in range(5):
            streak.increment(for_date=date(2024, 1, 1) + timedelta(days=i))
        # Gap — resets current
        streak.increment(for_date=date(2024, 2, 1))
        assert streak.current_count == 1
        assert streak.best_count == 5

    def test_reset(self):
        streak = Streak(type=StreakType.HABIT, current_count=10, best_count=10)
        streak.reset()
        assert streak.current_count == 0
        assert streak.best_count == 10


# ---------------------------------------------------------------------------
# WalkLog
# ---------------------------------------------------------------------------

class TestWalkLog:
    def test_mood_improvement_positive(self):
        walk = WalkLog(mood_before=2, mood_after=4)
        assert walk.mood_improvement == 2

    def test_mood_improvement_negative(self):
        walk = WalkLog(mood_before=4, mood_after=3)
        assert walk.mood_improvement == -1

    def test_calculate_points_base(self):
        walk = WalkLog(distance_km=0.0, mood_before=3, mood_after=3)
        assert walk.calculate_points(base=20, km_bonus=5, mood_bonus=10) == 20

    def test_calculate_points_with_distance(self):
        walk = WalkLog(distance_km=3.0, mood_before=3, mood_after=3)
        # base=20 + 3*5=15 = 35; no mood bonus (no improvement)
        assert walk.calculate_points(base=20, km_bonus=5, mood_bonus=10) == 35

    def test_calculate_points_with_mood_improvement(self):
        walk = WalkLog(distance_km=0.0, mood_before=2, mood_after=4)
        assert walk.calculate_points(base=20, km_bonus=5, mood_bonus=10) == 30

    def test_calculate_points_full(self):
        walk = WalkLog(distance_km=2.0, mood_before=2, mood_after=5)
        # base=20 + 2*5=10 + 10 = 40
        assert walk.calculate_points(base=20, km_bonus=5, mood_bonus=10) == 40


# ---------------------------------------------------------------------------
# DeepWorkSession
# ---------------------------------------------------------------------------

class TestDeepWorkSession:
    def test_is_active_when_no_end(self):
        session = DeepWorkSession()
        assert session.is_active is True

    def test_is_not_active_after_end(self):
        session = DeepWorkSession(ended_at=datetime.now())
        assert session.is_active is False

    def test_calculate_points_below_minimum(self):
        session = DeepWorkSession(duration_minutes=20)
        assert session.calculate_points(points_per_30min=15, minimum_minutes=25) == 0

    def test_calculate_points_one_block(self):
        session = DeepWorkSession(duration_minutes=30)
        assert session.calculate_points(points_per_30min=15, minimum_minutes=25) == 15

    def test_calculate_points_partial_block_not_counted(self):
        session = DeepWorkSession(duration_minutes=45)
        # Only 1 complete 30-min block
        assert session.calculate_points(points_per_30min=15, minimum_minutes=25) == 15

    def test_calculate_points_two_blocks(self):
        session = DeepWorkSession(duration_minutes=60)
        assert session.calculate_points(points_per_30min=15, minimum_minutes=25) == 30

    def test_end_sets_ended_at_and_duration(self):
        start = datetime.now() - timedelta(minutes=45)
        session = DeepWorkSession(started_at=start)
        session.end()
        assert session.ended_at is not None
        assert session.duration_minutes >= 44  # allow slight timing variance


# ---------------------------------------------------------------------------
# ReplacementLog
# ---------------------------------------------------------------------------

class TestReplacementLog:
    def test_calculate_points_base_urge(self):
        log = ReplacementLog(action_id=1, urge_level=3)
        assert log.calculate_points(base=30, high_urge_bonus=20) == 30

    def test_calculate_points_high_urge(self):
        log = ReplacementLog(action_id=1, urge_level=4)
        assert log.calculate_points(base=30, high_urge_bonus=20) == 50

    def test_calculate_points_max_urge(self):
        log = ReplacementLog(action_id=1, urge_level=5)
        assert log.calculate_points(base=30, high_urge_bonus=20) == 50

    def test_replacement_action_defaults(self):
        action = ReplacementAction(name="Go for a walk")
        assert action.category == "general"
        assert action.points == 30
        assert action.active is True


# ---------------------------------------------------------------------------
# Project / Milestone / Task
# ---------------------------------------------------------------------------

class TestProject:
    def test_project_is_complete_when_status_complete(self):
        project = Project(name="MyProject", status=ProjectStatus.COMPLETE)
        assert project.is_complete is True

    def test_project_not_complete_when_active(self):
        project = Project(name="MyProject", status=ProjectStatus.ACTIVE)
        assert project.is_complete is False

    def test_project_progress_no_milestones_active(self):
        project = Project(name="MyProject", status=ProjectStatus.ACTIVE)
        assert project.progress == 0.0

    def test_project_progress_no_milestones_complete(self):
        project = Project(name="MyProject", status=ProjectStatus.COMPLETE)
        assert project.progress == 1.0

    def test_project_progress_with_milestones(self):
        m1 = Milestone(id=1, project_id=1, name="M1", completed_at=datetime.now())
        m2 = Milestone(id=2, project_id=1, name="M2", completed_at=None)
        project = Project(name="MyProject", milestones=[m1, m2])
        assert project.progress == 0.5


class TestMilestone:
    def test_milestone_progress_no_tasks_incomplete(self):
        m = Milestone(id=1, project_id=1, name="M1")
        assert m.progress == 0.0

    def test_milestone_progress_no_tasks_complete(self):
        m = Milestone(id=1, project_id=1, name="M1", completed_at=datetime.now())
        assert m.progress == 1.0

    def test_milestone_progress_with_tasks(self):
        t1 = Task(id=1, milestone_id=1, name="T1", completed_at=datetime.now())
        t2 = Task(id=2, milestone_id=1, name="T2", completed_at=None)
        t3 = Task(id=3, milestone_id=1, name="T3", completed_at=None)
        m = Milestone(id=1, project_id=1, name="M1", tasks=[t1, t2, t3])
        assert abs(m.progress - (1 / 3)) < 0.001


class TestTask:
    def test_task_is_complete_when_completed_at_set(self):
        t = Task(id=1, milestone_id=1, name="T1", completed_at=datetime.now())
        assert t.is_complete is True

    def test_task_is_not_complete_when_no_completed_at(self):
        t = Task(id=1, milestone_id=1, name="T1")
        assert t.is_complete is False
