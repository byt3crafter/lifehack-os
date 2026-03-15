"""Habit row component for habit list display."""
import customtkinter as ctk
from typing import Callable, Optional
from ..theme import COLORS, FONTS


class HabitRow(ctk.CTkFrame):
    """A row displaying a habit with completion toggle."""
    
    def __init__(self, parent, habit_id: int, name: str, category: str,
                 streak: int = 0, completed: bool = False,
                 on_toggle: Callable[[int, bool], None] = None,
                 category_color: str = None, **kwargs):
        super().__init__(
            parent,
            fg_color=COLORS['bg_secondary'],
            corner_radius=6,
            height=56,
            **kwargs
        )
        
        self.habit_id = habit_id
        self.completed = completed
        self.on_toggle = on_toggle
        self.category_color = category_color or COLORS['accent']
        
        self.pack_propagate(False)
        
        # Main container
        container = ctk.CTkFrame(self, fg_color='transparent')
        container.pack(fill='both', expand=True, padx=12, pady=8)
        
        # Left side: checkbox + name
        left = ctk.CTkFrame(container, fg_color='transparent')
        left.pack(side='left', fill='y')
        
        self.checkbox = ctk.CTkCheckBox(
            left,
            text="",
            width=24,
            checkbox_height=24,
            checkbox_width=24,
            corner_radius=4,
            fg_color=COLORS['success'] if completed else COLORS['bg_card'],
            hover_color=COLORS['success'],
            border_color=COLORS['border_light'],
            command=self._on_check
        )
        self.checkbox.pack(side='left', padx=(0, 12))
        if completed:
            self.checkbox.select()
        
        # Name and category
        name_frame = ctk.CTkFrame(left, fg_color='transparent')
        name_frame.pack(side='left', fill='y')
        
        self.name_label = ctk.CTkLabel(
            name_frame,
            text=name,
            font=FONTS['body_bold'],
            text_color=COLORS['text_muted'] if completed else COLORS['text_primary']
        )
        self.name_label.pack(anchor='w')
        
        self.category_label = ctk.CTkLabel(
            name_frame,
            text=category,
            font=FONTS['small'],
            text_color=self.category_color
        )
        self.category_label.pack(anchor='w')
        
        # Right side: streak
        right = ctk.CTkFrame(container, fg_color='transparent')
        right.pack(side='right', fill='y')
        
        if streak > 0:
            streak_frame = ctk.CTkFrame(
                right,
                fg_color=COLORS['bg_card'],
                corner_radius=4
            )
            streak_frame.pack(side='right', padx=4)
            
            streak_label = ctk.CTkLabel(
                streak_frame,
                text=f"🔥 {streak}",
                font=FONTS['small'],
                text_color=COLORS['streak_fire']
            )
            streak_label.pack(padx=8, pady=4)
    
    def _on_check(self):
        """Handle checkbox toggle."""
        self.completed = self.checkbox.get()
        self._update_style()
        if self.on_toggle:
            self.on_toggle(self.habit_id, self.completed)
    
    def _update_style(self):
        """Update visual style based on completion state."""
        if self.completed:
            self.name_label.configure(text_color=COLORS['text_muted'])
            self.checkbox.configure(fg_color=COLORS['success'])
        else:
            self.name_label.configure(text_color=COLORS['text_primary'])
            self.checkbox.configure(fg_color=COLORS['bg_card'])
