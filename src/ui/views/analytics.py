"""Analytics view - reports and trends."""
import customtkinter as ctk
from datetime import date, timedelta
from typing import TYPE_CHECKING

from ..theme import COLORS, FONTS, create_card_frame
from ..components import ProgressBar

if TYPE_CHECKING:
    from ..app import LifeHackApp


class AnalyticsView(ctk.CTkFrame):
    """View for analytics and reports."""
    
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
            header, text="Analytics",
            font=FONTS['h1'], text_color=COLORS['text_primary']
        ).pack(side='left')
        
        # Main content
        content = ctk.CTkScrollableFrame(self, fg_color='transparent')
        content.pack(fill='both', expand=True, padx=24, pady=(0, 24))
        
        # Weekly summary
        self.weekly_card = create_card_frame(content)
        self.weekly_card.pack(fill='x', pady=8)
        
        ctk.CTkLabel(
            self.weekly_card, text="📊 This Week",
            font=FONTS['h2'], text_color=COLORS['text_primary']
        ).pack(anchor='w', padx=16, pady=(16, 12))
        
        self.weekly_content = ctk.CTkFrame(self.weekly_card, fg_color='transparent')
        self.weekly_content.pack(fill='x', padx=16, pady=(0, 16))
        
        # Point sources breakdown
        self.sources_card = create_card_frame(content)
        self.sources_card.pack(fill='x', pady=8)
        
        ctk.CTkLabel(
            self.sources_card, text="💰 XP Sources (7 days)",
            font=FONTS['h2'], text_color=COLORS['text_primary']
        ).pack(anchor='w', padx=16, pady=(16, 12))
        
        self.sources_content = ctk.CTkFrame(self.sources_card, fg_color='transparent')
        self.sources_content.pack(fill='x', padx=16, pady=(0, 16))
        
        # Recent activity
        self.activity_card = create_card_frame(content)
        self.activity_card.pack(fill='x', pady=8)
        
        ctk.CTkLabel(
            self.activity_card, text="📜 Recent Point Ledger",
            font=FONTS['h2'], text_color=COLORS['text_primary']
        ).pack(anchor='w', padx=16, pady=(16, 12))
        
        self.activity_content = ctk.CTkFrame(self.activity_card, fg_color='transparent')
        self.activity_content.pack(fill='x', padx=16, pady=(0, 16))
    
    def refresh(self):
        """Refresh analytics data."""
        self._refresh_weekly()
        self._refresh_sources()
        self._refresh_activity()
    
    def _refresh_weekly(self):
        """Refresh weekly summary."""
        for widget in self.weekly_content.winfo_children():
            widget.destroy()
        
        # Get stats
        stats = self.app.stats_repo.get_stats()
        config = self.app.config
        
        # Stats grid
        grid = ctk.CTkFrame(self.weekly_content, fg_color='transparent')
        grid.pack(fill='x')
        
        # Row 1
        self._add_stat(grid, "Total XP", f"{stats.total_xp:,}", COLORS['xp_gold'], 0, 0)
        self._add_stat(grid, "Level", f"{stats.level} - {config.get_level_name(stats.level)}", 
                      COLORS['accent'], 0, 1)
        
        # Row 2  
        sobriety = self.app.checkin_repo.get_sobriety_streak()
        self._add_stat(grid, "Sobriety Streak", f"{sobriety} days", COLORS['sobriety'], 1, 0)
        
        walk_stats = self.app.walk_repo.get_weekly_stats()
        self._add_stat(grid, "Walks This Week", f"{walk_stats['count']} ({walk_stats['total_km']:.1f}km)", 
                      COLORS['success'], 1, 1)
        
        # XP to next level
        xp_needed = stats.xp_for_next_level(config.levels.xp_per_level)
        xp_in_level = config.levels.xp_per_level - xp_needed
        progress = xp_in_level / config.levels.xp_per_level
        
        prog_frame = ctk.CTkFrame(self.weekly_content, fg_color='transparent')
        prog_frame.pack(fill='x', pady=(12, 0))
        
        ProgressBar(
            prog_frame,
            value=progress,
            label=f"Level {stats.level + 1} Progress",
            color=COLORS['accent']
        ).pack(fill='x')
        
        ctk.CTkLabel(
            prog_frame,
            text=f"{xp_needed} XP to next level",
            font=FONTS['small'],
            text_color=COLORS['text_muted']
        ).pack(anchor='e', pady=(4, 0))
    
    def _add_stat(self, parent, label, value, color, row, col):
        frame = ctk.CTkFrame(parent, fg_color=COLORS['bg_secondary'], corner_radius=6)
        frame.grid(row=row, column=col, padx=4, pady=4, sticky='nsew')
        parent.grid_columnconfigure(col, weight=1)
        
        ctk.CTkLabel(
            frame, text=label,
            font=FONTS['small'], text_color=COLORS['text_secondary']
        ).pack(anchor='w', padx=12, pady=(8, 2))
        
        ctk.CTkLabel(
            frame, text=value,
            font=FONTS['body_bold'], text_color=color
        ).pack(anchor='w', padx=12, pady=(0, 8))
    
    def _refresh_sources(self):
        """Refresh point sources breakdown."""
        for widget in self.sources_content.winfo_children():
            widget.destroy()
        
        summary = self.app.stats_repo.get_weekly_summary()
        
        if not summary:
            ctk.CTkLabel(
                self.sources_content,
                text="No points earned this week yet",
                font=FONTS['body'],
                text_color=COLORS['text_muted']
            ).pack(anchor='w')
            return
        
        total = sum(summary.values())
        
        source_colors = {
            'habit': COLORS['success'],
            'project': COLORS['accent'],
            'milestone': COLORS['accent'],
            'checkin': COLORS['warning'],
            'walk': COLORS['success'],
            'replacement': COLORS['sobriety'],
            'penalty': COLORS['danger'],
        }
        
        for source, points in sorted(summary.items(), key=lambda x: -x[1]):
            pct = (points / total * 100) if total > 0 else 0
            
            row = ctk.CTkFrame(self.sources_content, fg_color='transparent')
            row.pack(fill='x', pady=2)
            
            ctk.CTkLabel(
                row, text=source.title(),
                font=FONTS['body'], text_color=COLORS['text_primary']
            ).pack(side='left')
            
            color = source_colors.get(source, COLORS['text_secondary'])
            sign = "+" if points >= 0 else ""
            
            ctk.CTkLabel(
                row, text=f"{sign}{points} ({pct:.0f}%)",
                font=FONTS['body_bold'], text_color=color
            ).pack(side='right')
    
    def _refresh_activity(self):
        """Refresh recent activity ledger."""
        for widget in self.activity_content.winfo_children():
            widget.destroy()
        
        ledger = self.app.stats_repo.get_ledger(20)
        
        if not ledger:
            ctk.CTkLabel(
                self.activity_content,
                text="No activity yet",
                font=FONTS['body'],
                text_color=COLORS['text_muted']
            ).pack(anchor='w')
            return
        
        for entry in ledger:
            row = ctk.CTkFrame(
                self.activity_content,
                fg_color=COLORS['bg_secondary'],
                corner_radius=4
            )
            row.pack(fill='x', pady=2)
            
            # Time
            time_str = entry.timestamp.strftime("%b %d %H:%M")
            ctk.CTkLabel(
                row, text=time_str,
                font=FONTS['mono_small'], text_color=COLORS['text_muted'],
                width=100
            ).pack(side='left', padx=8, pady=4)
            
            # Reason
            ctk.CTkLabel(
                row, text=entry.reason or entry.source_type,
                font=FONTS['small'], text_color=COLORS['text_primary']
            ).pack(side='left', padx=4, pady=4, fill='x', expand=True)
            
            # Points
            sign = "+" if entry.points >= 0 else ""
            color = COLORS['success'] if entry.points >= 0 else COLORS['danger']
            
            ctk.CTkLabel(
                row, text=f"{sign}{entry.points}",
                font=FONTS['body_bold'], text_color=color
            ).pack(side='right', padx=8, pady=4)
