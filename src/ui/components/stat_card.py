"""Stat card component for displaying metrics."""
import customtkinter as ctk
from ..theme import COLORS, FONTS, create_card_frame


class StatCard(ctk.CTkFrame):
    """A card displaying a single statistic."""
    
    def __init__(self, parent, title: str, value: str, subtitle: str = "", 
                 accent_color: str = None, **kwargs):
        super().__init__(
            parent,
            fg_color=COLORS['bg_card'],
            corner_radius=8,
            border_width=1,
            border_color=COLORS['border'],
            **kwargs
        )
        
        self.accent = accent_color or COLORS['accent']
        
        # Title
        self.title_label = ctk.CTkLabel(
            self,
            text=title,
            font=FONTS['small'],
            text_color=COLORS['text_secondary']
        )
        self.title_label.pack(anchor='w', padx=16, pady=(12, 4))
        
        # Value
        self.value_label = ctk.CTkLabel(
            self,
            text=value,
            font=FONTS['h2'],
            text_color=self.accent
        )
        self.value_label.pack(anchor='w', padx=16, pady=(0, 4))
        
        # Subtitle
        if subtitle:
            self.subtitle_label = ctk.CTkLabel(
                self,
                text=subtitle,
                font=FONTS['small'],
                text_color=COLORS['text_muted']
            )
            self.subtitle_label.pack(anchor='w', padx=16, pady=(0, 12))
    
    def update_value(self, value: str, subtitle: str = None):
        """Update the displayed value."""
        self.value_label.configure(text=value)
        if subtitle is not None and hasattr(self, 'subtitle_label'):
            self.subtitle_label.configure(text=subtitle)
