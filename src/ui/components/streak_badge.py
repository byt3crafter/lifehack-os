"""Streak badge component."""
import customtkinter as ctk
from ..theme import COLORS, FONTS


class StreakBadge(ctk.CTkFrame):
    """A badge displaying streak information."""
    
    def __init__(self, parent, count: int, label: str = "day streak",
                 icon: str = "🔥", color: str = None, **kwargs):
        super().__init__(
            parent,
            fg_color=COLORS['bg_card'],
            corner_radius=8,
            **kwargs
        )
        
        self.color = color or COLORS['streak_fire']
        
        # Icon and count
        top = ctk.CTkFrame(self, fg_color='transparent')
        top.pack(pady=(12, 4))
        
        self.icon_label = ctk.CTkLabel(
            top,
            text=icon,
            font=('Inter', 24)
        )
        self.icon_label.pack(side='left', padx=(0, 8))
        
        self.count_label = ctk.CTkLabel(
            top,
            text=str(count),
            font=FONTS['h2'],
            text_color=self.color
        )
        self.count_label.pack(side='left')
        
        # Label
        self.label = ctk.CTkLabel(
            self,
            text=label,
            font=FONTS['small'],
            text_color=COLORS['text_secondary']
        )
        self.label.pack(pady=(0, 12))
    
    def update(self, count: int):
        """Update the streak count."""
        self.count_label.configure(text=str(count))
