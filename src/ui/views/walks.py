"""Walks view - log and track movement."""
import customtkinter as ctk
from datetime import datetime
from typing import TYPE_CHECKING

from ..theme import COLORS, FONTS, create_card_frame, create_button, create_entry

if TYPE_CHECKING:
    from ..app import LifeHackApp


class WalksView(ctk.CTkFrame):
    """View for logging walks and movement."""
    
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
            header, text="Movement Tracker",
            font=FONTS['h1'], text_color=COLORS['text_primary']
        ).pack(side='left')
        
        create_button(
            header, "+ Log Walk",
            command=self._show_log_dialog
        ).pack(side='right')
        
        # Stats row
        stats_frame = ctk.CTkFrame(self, fg_color='transparent')
        stats_frame.pack(fill='x', padx=24, pady=(0, 16))
        
        self.week_card = create_card_frame(stats_frame)
        self.week_card.pack(side='left', fill='x', expand=True, padx=(0, 8))
        
        ctk.CTkLabel(
            self.week_card, text="This Week",
            font=FONTS['small'], text_color=COLORS['text_secondary']
        ).pack(anchor='w', padx=16, pady=(12, 4))
        
        self.week_stats = ctk.CTkLabel(
            self.week_card, text="0 walks • 0 km",
            font=FONTS['h3'], text_color=COLORS['success']
        )
        self.week_stats.pack(anchor='w', padx=16, pady=(0, 12))
        
        self.points_card = create_card_frame(stats_frame)
        self.points_card.pack(side='left', fill='x', expand=True)
        
        ctk.CTkLabel(
            self.points_card, text="XP Earned",
            font=FONTS['small'], text_color=COLORS['text_secondary']
        ).pack(anchor='w', padx=16, pady=(12, 4))
        
        self.week_points = ctk.CTkLabel(
            self.points_card, text="0",
            font=FONTS['h3'], text_color=COLORS['xp_gold']
        )
        self.week_points.pack(anchor='w', padx=16, pady=(0, 12))
        
        # Recent walks
        ctk.CTkLabel(
            self, text="Recent Walks",
            font=FONTS['h3'], text_color=COLORS['text_primary']
        ).pack(anchor='w', padx=24, pady=(0, 8))
        
        self.walks_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS['bg_secondary'],
            corner_radius=8
        )
        self.walks_frame.pack(fill='both', expand=True, padx=24, pady=(0, 24))
    
    def refresh(self):
        """Refresh walks data."""
        # Weekly stats
        stats = self.app.walk_repo.get_weekly_stats()
        self.week_stats.configure(
            text=f"{stats['count']} walks • {stats['total_km']:.1f} km"
        )
        self.week_points.configure(text=str(stats['points']))
        
        # Recent walks
        for widget in self.walks_frame.winfo_children():
            widget.destroy()
        
        walks = self.app.walk_repo.get_recent(20)
        
        if not walks:
            ctk.CTkLabel(
                self.walks_frame,
                text="No walks logged yet. Get moving!",
                font=FONTS['body'],
                text_color=COLORS['text_muted']
            ).pack(pady=20)
            return
        
        for walk in walks:
            self._add_walk_row(walk)
    
    def _add_walk_row(self, walk):
        row = ctk.CTkFrame(
            self.walks_frame,
            fg_color=COLORS['bg_card'],
            corner_radius=6
        )
        row.pack(fill='x', padx=8, pady=4)
        
        # Left: date and stats
        left = ctk.CTkFrame(row, fg_color='transparent')
        left.pack(side='left', fill='y', padx=12, pady=8)
        
        date_str = walk.logged_at.strftime("%b %d, %H:%M")
        ctk.CTkLabel(
            left, text=date_str,
            font=FONTS['body_bold'], text_color=COLORS['text_primary']
        ).pack(anchor='w')
        
        stats = f"{walk.distance_km:.1f} km • {walk.duration_minutes} min"
        ctk.CTkLabel(
            left, text=stats,
            font=FONTS['small'], text_color=COLORS['text_secondary']
        ).pack(anchor='w')
        
        # Right: mood and points
        right = ctk.CTkFrame(row, fg_color='transparent')
        right.pack(side='right', fill='y', padx=12, pady=8)
        
        mood_diff = walk.mood_after - walk.mood_before
        mood_str = f"Mood: {walk.mood_before}→{walk.mood_after}"
        if mood_diff > 0:
            mood_str += f" (+{mood_diff})"
        
        ctk.CTkLabel(
            right, text=mood_str,
            font=FONTS['small'],
            text_color=COLORS['success'] if mood_diff > 0 else COLORS['text_secondary']
        ).pack(anchor='e')
        
        ctk.CTkLabel(
            right, text=f"+{walk.points_earned} XP",
            font=FONTS['body_bold'], text_color=COLORS['xp_gold']
        ).pack(anchor='e')
    
    def _show_log_dialog(self):
        dialog = LogWalkDialog(self, self.app)
        dialog.grab_set()


class LogWalkDialog(ctk.CTkToplevel):
    """Dialog for logging a walk."""
    
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.parent_view = parent
        
        self.title("Log Walk")
        self.geometry("400x450")
        self.configure(fg_color=COLORS['bg_primary'])
        self.transient(parent)
        
        self._build_ui()
    
    def _build_ui(self):
        ctk.CTkLabel(
            self, text="🚶 Log Walk",
            font=FONTS['h2'], text_color=COLORS['text_primary']
        ).pack(pady=(24, 16))
        
        form = ctk.CTkFrame(self, fg_color='transparent')
        form.pack(fill='x', padx=24)
        
        # Distance
        ctk.CTkLabel(
            form, text="Distance (km)",
            font=FONTS['body'], text_color=COLORS['text_secondary']
        ).pack(anchor='w')
        self.distance_entry = create_entry(form, "e.g., 3.5")
        self.distance_entry.pack(fill='x', pady=(4, 12))
        
        # Duration
        ctk.CTkLabel(
            form, text="Duration (minutes)",
            font=FONTS['body'], text_color=COLORS['text_secondary']
        ).pack(anchor='w')
        self.duration_entry = create_entry(form, "e.g., 45")
        self.duration_entry.pack(fill='x', pady=(4, 12))
        
        # Mood before
        ctk.CTkLabel(
            form, text="Mood Before (1-5)",
            font=FONTS['body'], text_color=COLORS['text_secondary']
        ).pack(anchor='w')
        
        self.mood_before_var = ctk.IntVar(value=3)
        mb_frame = ctk.CTkFrame(form, fg_color='transparent')
        mb_frame.pack(fill='x', pady=(4, 12))
        
        for i in range(1, 6):
            ctk.CTkRadioButton(
                mb_frame, text=str(i), width=40,
                variable=self.mood_before_var, value=i,
                fg_color=COLORS['accent']
            ).pack(side='left')
        
        # Mood after
        ctk.CTkLabel(
            form, text="Mood After (1-5)",
            font=FONTS['body'], text_color=COLORS['text_secondary']
        ).pack(anchor='w')
        
        self.mood_after_var = ctk.IntVar(value=4)
        ma_frame = ctk.CTkFrame(form, fg_color='transparent')
        ma_frame.pack(fill='x', pady=(4, 12))
        
        for i in range(1, 6):
            ctk.CTkRadioButton(
                ma_frame, text=str(i), width=40,
                variable=self.mood_after_var, value=i,
                fg_color=COLORS['success']
            ).pack(side='left')
        
        # Notes
        ctk.CTkLabel(
            form, text="Notes (optional)",
            font=FONTS['body'], text_color=COLORS['text_secondary']
        ).pack(anchor='w')
        self.notes_entry = create_entry(form, "")
        self.notes_entry.pack(fill='x', pady=(4, 16))
        
        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color='transparent')
        btn_frame.pack(fill='x', padx=24, pady=24)
        
        create_button(
            btn_frame, "Cancel",
            command=self.destroy,
            variant='ghost'
        ).pack(side='left')
        
        create_button(
            btn_frame, "Log Walk ✓",
            command=self._save,
            variant='success'
        ).pack(side='right')
    
    def _save(self):
        from ...domain.entities import WalkLog
        
        try:
            distance = float(self.distance_entry.get() or 0)
            duration = int(self.duration_entry.get() or 0)
        except ValueError:
            return
        
        config = self.app.config.walks
        
        walk = WalkLog(
            distance_km=distance,
            duration_minutes=duration,
            mood_before=self.mood_before_var.get(),
            mood_after=self.mood_after_var.get(),
            notes=self.notes_entry.get().strip()
        )
        
        points = walk.calculate_points(
            config.base_points,
            config.km_bonus,
            config.mood_improvement_bonus
        )
        walk.points_earned = points
        
        self.app.walk_repo.log(walk)
        self.app.stats_repo.add_points(
            'walk', points,
            f"Walk: {distance}km in {duration}min",
            walk.id
        )
        
        self.destroy()
        self.parent_view.refresh()
