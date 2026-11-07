"""Generate vertical (9:16) TikTok videos from storyboards or MT5 trade history."""
from .renderer import render, render_still
from .storyboard import Storyboard, from_dict, load

__all__ = ["Storyboard", "from_dict", "load", "render", "render_still"]
__version__ = "0.1.0"
