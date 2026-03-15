"""Theme and styling configuration."""
import customtkinter as ctk

# Color palette - dark, masculine, minimal
COLORS = {
    # Base
    'bg_primary': '#0f0f0f',
    'bg_secondary': '#1a1a1a',
    'bg_card': '#242424',
    'bg_hover': '#2d2d2d',
    
    # Text
    'text_primary': '#ffffff',
    'text_secondary': '#a0a0a0',
    'text_muted': '#666666',
    
    # Accents
    'accent': '#3b82f6',       # Blue
    'accent_hover': '#2563eb',
    'success': '#10b981',      # Green
    'warning': '#f59e0b',      # Amber
    'danger': '#ef4444',       # Red
    'sobriety': '#14b8a6',     # Teal
    
    # Borders
    'border': '#333333',
    'border_light': '#444444',
    
    # Status
    'streak_fire': '#f97316',  # Orange
    'xp_gold': '#eab308',      # Yellow
}

# Font configurations
FONTS = {
    'h1': ('Inter', 28, 'bold'),
    'h2': ('Inter', 22, 'bold'),
    'h3': ('Inter', 18, 'bold'),
    'body': ('Inter', 14),
    'body_bold': ('Inter', 14, 'bold'),
    'small': ('Inter', 12),
    'mono': ('JetBrains Mono', 14),
    'mono_small': ('JetBrains Mono', 12),
}

# Spacing
SPACING = {
    'xs': 4,
    'sm': 8,
    'md': 16,
    'lg': 24,
    'xl': 32,
}


def configure_theme():
    """Configure CustomTkinter appearance."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")


def create_card_frame(parent, **kwargs):
    """Create a styled card frame."""
    return ctk.CTkFrame(
        parent,
        fg_color=COLORS['bg_card'],
        corner_radius=8,
        border_width=1,
        border_color=COLORS['border'],
        **kwargs
    )


def create_button(parent, text, command=None, variant='primary', **kwargs):
    """Create a styled button."""
    colors = {
        'primary': (COLORS['accent'], COLORS['accent_hover']),
        'success': (COLORS['success'], '#059669'),
        'danger': (COLORS['danger'], '#dc2626'),
        'ghost': (COLORS['bg_secondary'], COLORS['bg_hover']),
    }
    fg, hover = colors.get(variant, colors['primary'])
    
    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        fg_color=fg,
        hover_color=hover,
        corner_radius=6,
        height=36,
        **kwargs
    )


def create_entry(parent, placeholder="", **kwargs):
    """Create a styled entry field."""
    return ctk.CTkEntry(
        parent,
        placeholder_text=placeholder,
        fg_color=COLORS['bg_secondary'],
        border_color=COLORS['border'],
        corner_radius=6,
        height=36,
        **kwargs
    )


def create_label(parent, text, style='body', color='text_primary', **kwargs):
    """Create a styled label."""
    font = FONTS.get(style, FONTS['body'])
    text_color = COLORS.get(color, color)
    
    return ctk.CTkLabel(
        parent,
        text=text,
        font=font,
        text_color=text_color,
        **kwargs
    )
