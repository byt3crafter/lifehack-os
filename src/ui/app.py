"""Main application window."""
import customtkinter as ctk
from typing import Dict, Type

from .theme import COLORS, FONTS, configure_theme, create_button
from .views import (
    DashboardView, HabitsView, ProjectsView,
    CheckinView, WalksView, AnalyticsView
)
from ..infrastructure.database import (
    init_database,
    HabitRepository, ProjectRepository, CheckinRepository,
    WalkRepository, ReplacementRepository, StatsRepository,
    DeepWorkRepository
)
from ..infrastructure.config import load_config


class LifeHackApp(ctk.CTk):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        
        # Configure window
        self.title("Life Hack OS")
        self.geometry("1200x800")
        self.minsize(1000, 600)
        self.configure(fg_color=COLORS['bg_primary'])
        
        # Initialize
        configure_theme()
        init_database()
        self.config = load_config()
        self._init_repositories()
        self._seed_defaults()
        
        # Build UI
        self._build_ui()
        
        # Show dashboard
        self.show_view('dashboard')
    
    def _init_repositories(self):
        """Initialize all repositories."""
        self.habit_repo = HabitRepository()
        self.project_repo = ProjectRepository()
        self.checkin_repo = CheckinRepository()
        self.walk_repo = WalkRepository()
        self.replacement_repo = ReplacementRepository()
        self.stats_repo = StatsRepository()
        self.deep_work_repo = DeepWorkRepository()
    
    def _seed_defaults(self):
        """Seed default data if empty."""
        # Seed replacement actions from config
        actions = self.replacement_repo.get_all_actions()
        if not actions:
            from ..domain.entities import ReplacementAction
            
            for cat_id, cat_info in self.config.replacement_categories.items():
                action = ReplacementAction(
                    name=cat_info['name'],
                    category=cat_id,
                    points=cat_info['points']
                )
                self.replacement_repo.create_action(action)
    
    def _build_ui(self):
        """Build the main UI layout."""
        # Main container
        self.main = ctk.CTkFrame(self, fg_color='transparent')
        self.main.pack(fill='both', expand=True)
        
        # Sidebar navigation
        self.sidebar = ctk.CTkFrame(
            self.main,
            fg_color=COLORS['bg_secondary'],
            width=220,
            corner_radius=0
        )
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)
        
        # Logo
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color='transparent')
        logo_frame.pack(fill='x', padx=16, pady=(24, 32))
        
        ctk.CTkLabel(
            logo_frame,
            text="⚡ LIFE HACK OS",
            font=('Inter', 16, 'bold'),
            text_color=COLORS['text_primary']
        ).pack(anchor='w')
        
        # Nav buttons
        self.nav_buttons: Dict[str, ctk.CTkButton] = {}
        
        nav_items = [
            ('dashboard', '📊', 'Dashboard'),
            ('habits', '✓', 'Habits'),
            ('projects', '📁', 'Projects'),
            ('checkin', '📝', 'Check-in'),
            ('walks', '🚶', 'Movement'),
            ('analytics', '📈', 'Analytics'),
        ]
        
        for view_id, icon, label in nav_items:
            btn = ctk.CTkButton(
                self.sidebar,
                text=f"  {icon}  {label}",
                font=FONTS['body'],
                fg_color='transparent',
                hover_color=COLORS['bg_hover'],
                anchor='w',
                height=44,
                corner_radius=8,
                command=lambda v=view_id: self.show_view(v)
            )
            btn.pack(fill='x', padx=12, pady=2)
            self.nav_buttons[view_id] = btn
        
        # Spacer
        ctk.CTkFrame(self.sidebar, fg_color='transparent').pack(fill='both', expand=True)
        
        # Bottom stats
        stats_frame = ctk.CTkFrame(self.sidebar, fg_color=COLORS['bg_card'], corner_radius=8)
        stats_frame.pack(fill='x', padx=12, pady=(0, 16))
        
        self.sidebar_xp = ctk.CTkLabel(
            stats_frame,
            text="0 XP",
            font=FONTS['body_bold'],
            text_color=COLORS['xp_gold']
        )
        self.sidebar_xp.pack(anchor='w', padx=12, pady=(12, 4))
        
        self.sidebar_level = ctk.CTkLabel(
            stats_frame,
            text="Level 1 • Initiate",
            font=FONTS['small'],
            text_color=COLORS['text_secondary']
        )
        self.sidebar_level.pack(anchor='w', padx=12, pady=(0, 12))
        
        # Content area
        self.content = ctk.CTkFrame(self.main, fg_color=COLORS['bg_primary'])
        self.content.pack(side='right', fill='both', expand=True)
        
        # Initialize views
        self.views: Dict[str, ctk.CTkFrame] = {}
        self.current_view = None
    
    def show_view(self, view_id: str):
        """Switch to a view."""
        # Update nav button styles
        for vid, btn in self.nav_buttons.items():
            if vid == view_id:
                btn.configure(fg_color=COLORS['accent'])
            else:
                btn.configure(fg_color='transparent')
        
        # Hide current view
        if self.current_view and self.current_view in self.views:
            self.views[self.current_view].pack_forget()
        
        # Create or show view
        if view_id not in self.views:
            view_classes = {
                'dashboard': DashboardView,
                'habits': HabitsView,
                'projects': ProjectsView,
                'checkin': CheckinView,
                'walks': WalksView,
                'analytics': AnalyticsView,
            }
            
            if view_id in view_classes:
                self.views[view_id] = view_classes[view_id](self.content, self)
        
        if view_id in self.views:
            self.views[view_id].pack(fill='both', expand=True)
            if hasattr(self.views[view_id], 'refresh'):
                self.views[view_id].refresh()
        
        self.current_view = view_id
        self._update_sidebar_stats()
    
    def _update_sidebar_stats(self):
        """Update sidebar stats display."""
        stats = self.stats_repo.get_stats()
        self.sidebar_xp.configure(text=f"{stats.total_xp:,} XP")
        level_name = self.config.get_level_name(stats.level)
        self.sidebar_level.configure(text=f"Level {stats.level} • {level_name}")


def run():
    """Run the application."""
    app = LifeHackApp()
    app.mainloop()
