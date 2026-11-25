"""Palette and type scale for MotionDeck Studio.

Own design. Colours were chosen from scratch for a dark editing tool; nothing
here is sampled from the app under study.
"""

BG = "#0e1014"
BG_DEEP = "#0a0c10"
SURFACE = "#171a23"
SURFACE_2 = "#1e2230"
SURFACE_3 = "#272c3b"
BORDER = "#2a3040"
BORDER_SOFT = "#20242f"

TEXT = "#eef1f7"
TEXT_DIM = "#b9c0d0"
MUTED = "#8b93a7"
MUTED_DARK = "#5f6678"

ACCENT = "#6c63ff"
ACCENT_HOVER = "#8179ff"
ACCENT_DIM = "#312c66"

GREEN = "#22c55e"
GREEN_DIM = "#12351f"
YELLOW = "#f5b942"
YELLOW_DIM = "#3a2c10"
RED = "#ef4444"
RED_DIM = "#3a1618"

INPUT = "#0b0d12"

FONT = "Malgun Gothic"
MONO = "Consolas"

def f(size, weight="normal"):
    return (FONT, size, weight)

BODY = f(10)
BODY_BOLD = f(10, "bold")
SMALL = f(9)
SMALL_BOLD = f(9, "bold")
TINY = f(8)
TITLE = f(20, "bold")
H1 = f(15, "bold")
H2 = f(12, "bold")
MONO_SMALL = (MONO, 9)

STATUS_COLORS = {
    "queued": (MUTED, SURFACE_3),
    "running": (ACCENT_HOVER, ACCENT_DIM),
    "done": (GREEN, GREEN_DIM),
    "failed": (RED, RED_DIM),
    "cancelled": (MUTED, SURFACE_3),
}
