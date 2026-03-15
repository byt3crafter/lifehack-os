"""Habits view - manage and track habits."""
import customtkinter as ctk
from datetime import date
from typing import TYPE_CHECKING

from ..theme import COLORS, FONTS, create_card_frame, create_button, create_entry
from ..components import HabitRow

if TYPE_CHECKING:
    from ..app import LifeHackApp


class HabitsView(ctk.CTkFrame):
    """View for managing habits."""
    
    def __init__(self, parent, app: 'LifeHackApp'):
        super().__init__(parent, fg_color=COLORS['bg_primary'])
        self.app = app
        self._build_ui()
        self.refresh()
    
    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color='transparent')
        header.pack(fill='x', padx=24, pady=(24, 16))
        
        ctk.CTkLabel(
            header, text="Habits",
            font=FONTS['h1'], text_color=COLORS['text_primary']
        ).pack(side='left')
        
        create_button(
            header, "+ Add Habit",
            command=self._show_add_dialog
        ).pack(side='right')
        
        # Category filter
        filter_frame = ctk.CTkFrame(self, fg_color='transparent')
        filter_frame.pack(fill='x', padx=24, pady=(0, 16))
        
        self.category_var = ctk.StringVar(value="all")
        
        ctk.CTkRadioButton(
            filter_frame, text="All",
            variable=self.category_var, value="all",
            command=self.refresh,
            fg_color=COLORS['accent']
        ).pack(side='left', padx=(0, 16))
        
        for cat_id, cat_info in self.app.config.categories.items():
            ctk.CTkRadioButton(
                filter_frame, text=cat_info.icon + " " + cat_info.name,
                variable=self.category_var, value=cat_id,
                command=self.refresh,
                fg_color=cat_info.color
            ).pack(side='left', padx=(0, 16))
        
        # Habits list
        self.habits_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS['bg_secondary'],
            corner_radius=8
        )
        self.habits_frame.pack(fill='both', expand=True, padx=24, pady=(0, 24))
    
    def refresh(self):
        """Refresh the habits list."""
        for widget in self.habits_frame.winfo_children():
            widget.destroy()
        
        habits = self.app.habit_repo.get_all()
        completions = self.app.habit_repo.get_completions_for_date(date.today())
        completed_ids = {c.habit_id for c in completions}
        
        selected_cat = self.category_var.get()
        
        for habit in habits:
            if selected_cat != "all" and habit.category != selected_cat:
                continue
            
            is_complete = habit.id in completed_ids
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
    
    def _show_add_dialog(self):
        dialog = AddHabitDialog(self, self.app)
        dialog.grab_set()


class AddHabitDialog(ctk.CTkToplevel):
    """Dialog for adding a new habit."""
    
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.parent_view = parent
        
        self.title("Add Habit")
        self.geometry("450x400")
        self.configure(fg_color=COLORS['bg_primary'])
        self.transient(parent)
        
        self._build_ui()
    
    def _build_ui(self):
        ctk.CTkLabel(
            self, text="New Habit",
            font=FONTS['h2'], text_color=COLORS['text_primary']
        ).pack(pady=(24, 16))
        
        form = ctk.CTkFrame(self, fg_color='transparent')
        form.pack(fill='x', padx=24)
        
        # Name
        ctk.CTkLabel(
            form, text="Name",
            font=FONTS['body'], text_color=COLORS['text_secondary']
        ).pack(anchor='w')
        self.name_entry = create_entry(form, "e.g., Morning workout")
        self.name_entry.pack(fill='x', pady=(4, 12))
        
        # Category
        ctk.CTkLabel(
            form, text="Category",
            font=FONTS['body'], text_color=COLORS['text_secondary']
        ).pack(anchor='w')
        
        categories = list(self.app.config.categories.keys())
        self.category_var = ctk.StringVar(value=categories[0] if categories else "health")
        
        self.category_menu = ctk.CTkOptionMenu(
            form,
            values=categories,
            variable=self.category_var,
            fg_color=COLORS['bg_secondary'],
            button_color=COLORS['accent'],
            button_hover_color=COLORS['accent_hover']
        )
        self.category_menu.pack(fill='x', pady=(4, 12))
        
        # Frequency
        ctk.CTkLabel(
            form, text="Frequency",
            font=FONTS['body'], text_color=COLORS['text_secondary']
        ).pack(anchor='w')
        
        self.frequency_var = ctk.StringVar(value="daily")
        freq_frame = ctk.CTkFrame(form, fg_color='transparent')
        freq_frame.pack(fill='x', pady=(4, 12))
        
        ctk.CTkRadioButton(
            freq_frame, text="Daily",
            variable=self.frequency_var, value="daily",
            fg_color=COLORS['accent']
        ).pack(side='left', padx=(0, 16))
        
        ctk.CTkRadioButton(
            freq_frame, text="Weekly",
            variable=self.frequency_var, value="weekly",
            fg_color=COLORS['accent']
        ).pack(side='left')
        
        # Difficulty
        ctk.CTkLabel(
            form, text="Difficulty (1-5)",
            font=FONTS['body'], text_color=COLORS['text_secondary']
        ).pack(anchor='w')
        
        self.difficulty_var = ctk.IntVar(value=1)
        diff_frame = ctk.CTkFrame(form, fg_color='transparent')
        diff_frame.pack(fill='x', pady=(4, 16))
        
        for i in range(1, 6):
            ctk.CTkRadioButton(
                diff_frame, text=str(i),
                variable=self.difficulty_var, value=i,
                fg_color=COLORS['accent']
            ).pack(side='left', padx=8)
        
        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color='transparent')
        btn_frame.pack(fill='x', padx=24, pady=24)
        
        create_button(
            btn_frame, "Cancel",
            command=self.destroy,
            variant='ghost'
        ).pack(side='left')
        
        create_button(
            btn_frame, "Add Habit",
            command=self._save
        ).pack(side='right')
    
    def _save(self):
        from ...domain.entities import Habit, Frequency
        
        name = self.name_entry.get().strip()
        if not name:
            return
        
        habit = Habit(
            name=name,
            category=self.category_var.get(),
            frequency=Frequency(self.frequency_var.get()),
            difficulty=self.difficulty_var.get(),
            points=self.app.config.scoring.base_habit_points
        )
        
        self.app.habit_repo.create(habit)
        self.destroy()
        self.parent_view.refresh()
