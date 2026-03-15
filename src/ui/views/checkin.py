"""Check-in view - daily reflection."""
import customtkinter as ctk
from datetime import date
from typing import TYPE_CHECKING

from ..theme import COLORS, FONTS, create_card_frame, create_button

if TYPE_CHECKING:
    from ..app import LifeHackApp


class CheckinView(ctk.CTkFrame):
    """View for daily check-in."""
    
    def __init__(self, parent, app: 'LifeHackApp'):
        super().__init__(parent, fg_color=COLORS['bg_primary'])
        self.app = app
        self._build_ui()
        self._load_today()
    
    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color='transparent')
        header.pack(fill='x', padx=24, pady=(24, 16))
        
        ctk.CTkLabel(
            header, text="Daily Check-in",
            font=FONTS['h1'], text_color=COLORS['text_primary']
        ).pack(side='left')
        
        self.date_label = ctk.CTkLabel(
            header, text=date.today().strftime("%A, %B %d"),
            font=FONTS['body'], text_color=COLORS['text_secondary']
        )
        self.date_label.pack(side='right')
        
        # Main form
        form = ctk.CTkScrollableFrame(
            self,
            fg_color='transparent'
        )
        form.pack(fill='both', expand=True, padx=24, pady=(0, 24))
        
        # What did I complete today?
        card1 = create_card_frame(form)
        card1.pack(fill='x', pady=8)
        
        ctk.CTkLabel(
            card1, text="What did I complete today?",
            font=FONTS['h3'], text_color=COLORS['text_primary']
        ).pack(anchor='w', padx=16, pady=(16, 8))
        
        self.completed_text = ctk.CTkTextbox(
            card1,
            height=100,
            fg_color=COLORS['bg_secondary'],
            corner_radius=6
        )
        self.completed_text.pack(fill='x', padx=16, pady=(0, 16))
        
        # Sobriety
        card2 = create_card_frame(form)
        card2.pack(fill='x', pady=8)
        
        ctk.CTkLabel(
            card2, text="🛡️ Did I avoid alcohol today?",
            font=FONTS['h3'], text_color=COLORS['sobriety']
        ).pack(anchor='w', padx=16, pady=(16, 8))
        
        self.sobriety_var = ctk.BooleanVar(value=True)
        
        sobriety_frame = ctk.CTkFrame(card2, fg_color='transparent')
        sobriety_frame.pack(fill='x', padx=16, pady=(0, 16))
        
        ctk.CTkRadioButton(
            sobriety_frame, text="Yes ✓",
            variable=self.sobriety_var, value=True,
            fg_color=COLORS['success']
        ).pack(side='left', padx=(0, 24))
        
        ctk.CTkRadioButton(
            sobriety_frame, text="No",
            variable=self.sobriety_var, value=False,
            fg_color=COLORS['danger']
        ).pack(side='left')
        
        # Future work
        card3 = create_card_frame(form)
        card3.pack(fill='x', pady=8)
        
        ctk.CTkLabel(
            card3, text="🚀 Did I work on my future?",
            font=FONTS['h3'], text_color=COLORS['accent']
        ).pack(anchor='w', padx=16, pady=(16, 8))
        
        ctk.CTkLabel(
            card3, text="Projects, skills, business, health — anything building toward your goals",
            font=FONTS['small'], text_color=COLORS['text_muted']
        ).pack(anchor='w', padx=16, pady=(0, 8))
        
        self.future_var = ctk.BooleanVar(value=False)
        
        future_frame = ctk.CTkFrame(card3, fg_color='transparent')
        future_frame.pack(fill='x', padx=16, pady=(0, 16))
        
        ctk.CTkRadioButton(
            future_frame, text="Yes ✓",
            variable=self.future_var, value=True,
            fg_color=COLORS['success']
        ).pack(side='left', padx=(0, 24))
        
        ctk.CTkRadioButton(
            future_frame, text="No",
            variable=self.future_var, value=False,
            fg_color=COLORS['text_muted']
        ).pack(side='left')
        
        # Mood & Energy
        card4 = create_card_frame(form)
        card4.pack(fill='x', pady=8)
        
        me_frame = ctk.CTkFrame(card4, fg_color='transparent')
        me_frame.pack(fill='x', padx=16, pady=16)
        
        # Mood
        mood_frame = ctk.CTkFrame(me_frame, fg_color='transparent')
        mood_frame.pack(side='left', fill='x', expand=True)
        
        ctk.CTkLabel(
            mood_frame, text="Mood (1-5)",
            font=FONTS['body_bold'], text_color=COLORS['text_primary']
        ).pack(anchor='w')
        
        self.mood_var = ctk.IntVar(value=3)
        mood_btns = ctk.CTkFrame(mood_frame, fg_color='transparent')
        mood_btns.pack(anchor='w', pady=(4, 0))
        
        for i in range(1, 6):
            ctk.CTkRadioButton(
                mood_btns, text=str(i), width=40,
                variable=self.mood_var, value=i,
                fg_color=COLORS['accent']
            ).pack(side='left')
        
        # Energy
        energy_frame = ctk.CTkFrame(me_frame, fg_color='transparent')
        energy_frame.pack(side='right', fill='x', expand=True)
        
        ctk.CTkLabel(
            energy_frame, text="Energy (1-5)",
            font=FONTS['body_bold'], text_color=COLORS['text_primary']
        ).pack(anchor='w')
        
        self.energy_var = ctk.IntVar(value=3)
        energy_btns = ctk.CTkFrame(energy_frame, fg_color='transparent')
        energy_btns.pack(anchor='w', pady=(4, 0))
        
        for i in range(1, 6):
            ctk.CTkRadioButton(
                energy_btns, text=str(i), width=40,
                variable=self.energy_var, value=i,
                fg_color=COLORS['warning']
            ).pack(side='left')
        
        # Improvement note
        card5 = create_card_frame(form)
        card5.pack(fill='x', pady=8)
        
        ctk.CTkLabel(
            card5, text="What needs improvement tomorrow?",
            font=FONTS['h3'], text_color=COLORS['text_primary']
        ).pack(anchor='w', padx=16, pady=(16, 8))
        
        self.improvement_text = ctk.CTkTextbox(
            card5,
            height=80,
            fg_color=COLORS['bg_secondary'],
            corner_radius=6
        )
        self.improvement_text.pack(fill='x', padx=16, pady=(0, 16))
        
        # Submit button
        btn_frame = ctk.CTkFrame(form, fg_color='transparent')
        btn_frame.pack(fill='x', pady=16)
        
        self.submit_btn = create_button(
            btn_frame, "Complete Check-in ✓",
            command=self._save,
            variant='success'
        )
        self.submit_btn.pack(side='right')
        
        self.status_label = ctk.CTkLabel(
            btn_frame, text="",
            font=FONTS['body'], text_color=COLORS['success']
        )
        self.status_label.pack(side='left')
    
    def _load_today(self):
        """Load existing check-in for today if exists."""
        checkin = self.app.checkin_repo.get_for_date(date.today())
        
        if checkin:
            self.completed_text.insert("1.0", checkin.completed_today)
            self.sobriety_var.set(checkin.avoided_alcohol)
            self.future_var.set(checkin.worked_on_future)
            self.mood_var.set(checkin.mood)
            self.energy_var.set(checkin.energy)
            self.improvement_text.insert("1.0", checkin.improvement_note)
            self.status_label.configure(text="✓ Check-in saved")
    
    def _save(self):
        from ...domain.entities import DailyCheckin
        
        config = self.app.config.checkin
        
        checkin = DailyCheckin(
            date=date.today(),
            completed_today=self.completed_text.get("1.0", "end-1c").strip(),
            avoided_alcohol=self.sobriety_var.get(),
            worked_on_future=self.future_var.get(),
            mood=self.mood_var.get(),
            energy=self.energy_var.get(),
            improvement_note=self.improvement_text.get("1.0", "end-1c").strip()
        )
        
        points = checkin.calculate_points(
            config.completion_points,
            config.sobriety_bonus,
            config.future_work_bonus
        )
        checkin.points_earned = points
        
        # Check if this is a new check-in or update
        existing = self.app.checkin_repo.get_for_date(date.today())
        is_new = existing is None
        
        self.app.checkin_repo.save(checkin)
        
        if is_new:
            self.app.stats_repo.add_points(
                'checkin', points,
                f"Daily check-in completed",
                checkin.id
            )
        
        self.status_label.configure(text=f"✓ Saved (+{points} XP)")
