"""Progress bar component."""
import customtkinter as ctk
from ..theme import COLORS


class ProgressBar(ctk.CTkFrame):
    """A styled progress bar with label."""
    
    def __init__(self, parent, value: float = 0, label: str = "",
                 show_percentage: bool = True, color: str = None, 
                 height: int = 8, **kwargs):
        super().__init__(parent, fg_color='transparent', **kwargs)
        
        self.color = color or COLORS['accent']
        self.show_percentage = show_percentage
        
        # Label row
        if label or show_percentage:
            label_frame = ctk.CTkFrame(self, fg_color='transparent')
            label_frame.pack(fill='x', pady=(0, 4))
            
            if label:
                self.label = ctk.CTkLabel(
                    label_frame,
                    text=label,
                    font=('Inter', 12),
                    text_color=COLORS['text_secondary']
                )
                self.label.pack(side='left')
            
            if show_percentage:
                self.pct_label = ctk.CTkLabel(
                    label_frame,
                    text=f"{int(value * 100)}%",
                    font=('Inter', 12),
                    text_color=COLORS['text_secondary']
                )
                self.pct_label.pack(side='right')
        
        # Progress bar
        self.progress = ctk.CTkProgressBar(
            self,
            height=height,
            corner_radius=height // 2,
            fg_color=COLORS['bg_secondary'],
            progress_color=self.color
        )
        self.progress.pack(fill='x')
        self.progress.set(value)
    
    def set(self, value: float):
        """Update the progress value (0-1)."""
        self.progress.set(value)
        if self.show_percentage and hasattr(self, 'pct_label'):
            self.pct_label.configure(text=f"{int(value * 100)}%")
