"""Dashboard view - main overview screen."""
import customtkinter as ctk
from datetime import date, datetime
from typing import TYPE_CHECKING

from ..theme import COLORS, FONTS, create_card_frame, create_button
from ..components import StatCard, HabitRow, ProgressBar, StreakBadge

if TYPE_CHECKING:
    from ..app import LifeHackApp


class DashboardView(ctk.CTkFrame):
    """Main dashboard showing today's overview."""
    
    def __init__(self, parent, app: 'LifeHackApp'):
        super().__init__(parent, fg_color=COLORS['bg_primary'])
        self.app = app
        self._build_ui()
        self.refresh()
    
    def _build_ui(self):
        """Build the dashboard UI."""
        # Header
        header = ctk.CTkFrame(self, fg_color='transparent')
        header.pack(fill='x', padx=24, pady=(24, 16))
        
        today = date.today().strftime("%A, %B %d")
        ctk.CTkLabel(
            header, text="Dashboard",
            font=FONTS['h1'], text_color=COLORS['text_primary']
        ).pack(side='left')
        
        ctk.CTkLabel(
            header, text=today,
            font=FONTS['body'], text_color=COLORS['text_secondary']
        ).pack(side='right')
        
        # Main content area
        content = ctk.CTkFrame(self, fg_color='transparent')
        content.pack(fill='both', expand=True, padx=24, pady=(0, 24))
        
        # Left column (stats + habits)
        left = ctk.CTkFrame(content, fg_color='transparent')
        left.pack(side='left', fill='both', expand=True, padx=(0, 12))
        
        # Stats row
        stats_frame = ctk.CTkFrame(left, fg_color='transparent')
        stats_frame.pack(fill='x', pady=(0, 16))
        
        self.xp_card = StatCard(
            stats_frame, "Total XP", "0",
            accent_color=COLORS['xp_gold']
        )
        self.xp_card.pack(side='left', fill='x', expand=True, padx=(0, 8))
        
        self.level_card = StatCard(
            stats_frame, "Level", "1",
            subtitle="Initiate",
            accent_color=COLORS['accent']
        )
        self.level_card.pack(side='left', fill='x', expand=True, padx=(0, 8))
        
        self.streak_card = StatCard(
            stats_frame, "Best Streak", "0",
            subtitle="days",
            accent_color=COLORS['streak_fire']
        )
        self.streak_card.pack(side='left', fill='x', expand=True)
        
        # Today's habits
        habits_header = ctk.CTkFrame(left, fg_color='transparent')
        habits_header.pack(fill='x', pady=(8, 8))
        
        ctk.CTkLabel(
            habits_header, text="Today's Habits",
            font=FONTS['h3'], text_color=COLORS['text_primary']
        ).pack(side='left')
        
        self.habits_progress = ctk.CTkLabel(
            habits_header, text="0/0",
            font=FONTS['body'], text_color=COLORS['text_secondary']
        )
        self.habits_progress.pack(side='right')
        
        # Habits list
        self.habits_frame = ctk.CTkScrollableFrame(
            left,
            fg_color=COLORS['bg_secondary'],
            corner_radius=8
        )
        self.habits_frame.pack(fill='both', expand=True)
        
        # Right column (sobriety + projects + quick actions)
        right = ctk.CTkFrame(content, fg_color='transparent', width=320)
        right.pack(side='right', fill='y', padx=(12, 0))
        right.pack_propagate(False)
        
        # Sobriety card
        sobriety_card = create_card_frame(right)
        sobriety_card.pack(fill='x', pady=(0, 16))
        
        ctk.CTkLabel(
            sobriety_card, text="🛡️ Sobriety",
            font=FONTS['h3'], text_color=COLORS['sobriety']
        ).pack(anchor='w', padx=16, pady=(16, 8))
        
        self.sobriety_label = ctk.CTkLabel(
            sobriety_card, text="0 days",
            font=FONTS['h1'], text_color=COLORS['text_primary']
        )
        self.sobriety_label.pack(anchor='w', padx=16, pady=(0, 16))
        
        # Active projects
        projects_card = create_card_frame(right)
        projects_card.pack(fill='x', pady=(0, 16))
        
        ctk.CTkLabel(
            projects_card, text="📁 Active Projects",
            font=FONTS['h3'], text_color=COLORS['text_primary']
        ).pack(anchor='w', padx=16, pady=(16, 8))
        
        self.projects_list = ctk.CTkFrame(projects_card, fg_color='transparent')
        self.projects_list.pack(fill='x', padx=16, pady=(0, 16))
        
        # Quick actions
        actions_card = create_card_frame(right)
        actions_card.pack(fill='x')
        
        ctk.CTkLabel(
            actions_card, text="Quick Actions",
            font=FONTS['h3'], text_color=COLORS['text_primary']
        ).pack(anchor='w', padx=16, pady=(16, 12))
        
        actions = ctk.CTkFrame(actions_card, fg_color='transparent')
        actions.pack(fill='x', padx=16, pady=(0, 16))
        
        create_button(
            actions, "📝 Check-in",
            command=lambda: self.app.show_view('checkin'),
            variant='ghost'
        ).pack(fill='x', pady=(0, 8))
        
        create_button(
            actions, "🚶 Log Walk",
            command=lambda: self.app.show_view('walks'),
            variant='ghost'
        ).pack(fill='x', pady=(0, 8))
        
        create_button(
            actions, "🔄 Urge Redirect",
            command=self._show_replacement_dialog,
            variant='success'
        ).pack(fill='x')
    
    def refresh(self):
        """Refresh dashboard data."""
        # Get stats
        stats = self.app.stats_repo.get_stats()
        config = self.app.config
        
        self.xp_card.update_value(
            f"{stats.total_xp:,}",
            f"{stats.xp_for_next_level(config.levels.xp_per_level)} to next level"
        )
        self.level_card.update_value(
            str(stats.level),
            config.get_level_name(stats.level)
        )
        
        # Sobriety
        sobriety_days = self.app.checkin_repo.get_sobriety_streak()
        self.sobriety_label.configure(text=f"{sobriety_days} days")
        
        # Today's habits
        self._refresh_habits()
        
        # Active projects
        self._refresh_projects()
    
    def _refresh_habits(self):
        """Refresh the habits list."""
        # Clear existing
        for widget in self.habits_frame.winfo_children():
            widget.destroy()
        
        habits = self.app.habit_repo.get_all()
        completions = self.app.habit_repo.get_completions_for_date(date.today())
        completed_ids = {c.habit_id for c in completions}
        
        completed_count = 0
        for habit in habits:
            is_complete = habit.id in completed_ids
            if is_complete:
                completed_count += 1
            
            streak = self.app.habit_repo.get_streak(habit.id)
            cat_info = self.app.config.categories.get(habit.category)
            
            row = HabitRow(
                self.habits_frame,
                habit_id=habit.id,
                name=habit.name,
                category=cat_info.name if cat_info else habit.category,
                streak=streak,
                completed=is_complete,
                on_toggle=self._on_habit_toggle,
                category_color=cat_info.color if cat_info else None
            )
            row.pack(fill='x', padx=8, pady=4)
        
        self.habits_progress.configure(text=f"{completed_count}/{len(habits)}")
        
        # Update best streak
        best_streak = max((self.app.habit_repo.get_streak(h.id) for h in habits), default=0)
        self.streak_card.update_value(str(best_streak))
    
    def _refresh_projects(self):
        """Refresh the projects list."""
        for widget in self.projects_list.winfo_children():
            widget.destroy()
        
        projects = self.app.project_repo.get_all()[:5]  # Top 5
        
        if not projects:
            ctk.CTkLabel(
                self.projects_list,
                text="No active projects",
                font=FONTS['small'],
                text_color=COLORS['text_muted']
            ).pack(anchor='w')
            return
        
        for project in projects:
            proj_frame = ctk.CTkFrame(self.projects_list, fg_color='transparent')
            proj_frame.pack(fill='x', pady=4)
            
            ctk.CTkLabel(
                proj_frame,
                text=project.name,
                font=FONTS['body'],
                text_color=COLORS['text_primary']
            ).pack(anchor='w')
            
            ProgressBar(
                proj_frame,
                value=project.progress,
                show_percentage=True,
                height=6
            ).pack(fill='x', pady=(4, 0))
    
    def _on_habit_toggle(self, habit_id: int, completed: bool):
        """Handle habit completion toggle."""
        from ...domain.entities import HabitCompletion, CompletionStatus
        
        if completed:
            habit = self.app.habit_repo.get_by_id(habit_id)
            if habit:
                streak = self.app.habit_repo.get_streak(habit_id)
                points = habit.calculate_points(
                    streak,
                    self.app.config.scoring.streak_multiplier_threshold,
                    self.app.config.scoring.streak_multiplier
                )
                
                completion = HabitCompletion(
                    habit_id=habit_id,
                    status=CompletionStatus.COMPLETE,
                    points_earned=points
                )
                self.app.habit_repo.log_completion(completion)
                self.app.stats_repo.add_points(
                    'habit', points,
                    f"Completed: {habit.name}",
                    habit_id
                )
        
        self.refresh()
    
    def _show_replacement_dialog(self):
        """Show the urge replacement dialog."""
        # For MVP, just switch to a simple flow
        dialog = ReplacementDialog(self, self.app)
        dialog.grab_set()


class ReplacementDialog(ctk.CTkToplevel):
    """Dialog for logging an urge replacement."""
    
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        
        self.title("Redirect Urge")
        self.geometry("400x500")
        self.configure(fg_color=COLORS['bg_primary'])
        
        # Center on parent
        self.transient(parent)
        
        self._build_ui()
    
    def _build_ui(self):
        ctk.CTkLabel(
            self, text="🔄 Redirect the Urge",
            font=FONTS['h2'], text_color=COLORS['text_primary']
        ).pack(pady=(24, 8))
        
        ctk.CTkLabel(
            self, text="What will you do instead?",
            font=FONTS['body'], text_color=COLORS['text_secondary']
        ).pack(pady=(0, 16))
        
        # Urge level
        urge_frame = ctk.CTkFrame(self, fg_color='transparent')
        urge_frame.pack(fill='x', padx=24, pady=(0, 16))
        
        ctk.CTkLabel(
            urge_frame, text="Urge Level:",
            font=FONTS['body'], text_color=COLORS['text_secondary']
        ).pack(side='left')
        
        self.urge_var = ctk.IntVar(value=3)
        for i in range(1, 6):
            ctk.CTkRadioButton(
                urge_frame, text=str(i),
                variable=self.urge_var, value=i,
                fg_color=COLORS['accent']
            ).pack(side='left', padx=8)
        
        # Actions list
        actions_frame = ctk.CTkScrollableFrame(
            self, fg_color=COLORS['bg_secondary'],
            height=250
        )
        actions_frame.pack(fill='x', padx=24, pady=(0, 16))
        
        self.selected_action = ctk.IntVar(value=0)
        actions = self.app.replacement_repo.get_all_actions()
        
        for action in actions:
            ctk.CTkRadioButton(
                actions_frame,
                text=f"{action.name} (+{action.points} pts)",
                variable=self.selected_action,
                value=action.id,
                fg_color=COLORS['success']
            ).pack(anchor='w', pady=4)
        
        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color='transparent')
        btn_frame.pack(fill='x', padx=24, pady=(0, 24))
        
        create_button(
            btn_frame, "Cancel",
            command=self.destroy,
            variant='ghost'
        ).pack(side='left')
        
        create_button(
            btn_frame, "Log Redirect ✓",
            command=self._save,
            variant='success'
        ).pack(side='right')
    
    def _save(self):
        from ...domain.entities import ReplacementLog
        
        action_id = self.selected_action.get()
        if not action_id:
            return
        
        urge_level = self.urge_var.get()
        config = self.app.config.replacements
        
        points = config.urge_redirect_base
        if urge_level >= 4:
            points += config.high_urge_bonus
        
        log = ReplacementLog(
            action_id=action_id,
            urge_level=urge_level,
            points_earned=points
        )
        self.app.replacement_repo.log_replacement(log)
        self.app.stats_repo.add_points(
            'replacement', points,
            f"Redirected urge (level {urge_level})",
            action_id
        )
        
        self.destroy()
        self.master.refresh()
