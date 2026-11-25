"""Workspace chooser: the small first window."""
import tkinter as tk

from . import theme as T
from .store import APP_NAME, VERSION
from .widgets import round_rect


class WorkspaceButton(tk.Canvas):
    def __init__(self, master, label, glyph, command, enabled=True,
                 primary=False, badge=None, height=64):
        super().__init__(master, height=height, bg=T.BG, highlightthickness=0,
                         bd=0, cursor="hand2" if enabled else "arrow")
        self._label = label
        self._glyph = glyph
        self._command = command
        self._enabled = enabled
        self._primary = primary
        self._badge = badge
        self._hover = False
        self.bind("<Configure>", lambda e: self._render())
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._click)

    def _enter(self, _e):
        if self._enabled:
            self._hover = True
            self._render()

    def _leave(self, _e):
        self._hover = False
        self._render()

    def _click(self, _e):
        if self._enabled and self._command:
            self._command()

    def _render(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            return
        if self._primary:
            fill = T.ACCENT_HOVER if self._hover else T.ACCENT
            fg = "#ffffff"
            glyph_fg = "#e9e7ff"
        else:
            fill = "#21242e" if self._hover else "#f2f3f7"
            fg = "#11131a" if self._enabled else "#9aa1b2"
            glyph_fg = "#43485c"
            if self._hover and self._enabled:
                fill = "#ffffff"
        round_rect(self, 1, 1, w - 1, h - 1, 14, fill=fill, outline="")
        if self._glyph:
            self.create_text(34, h / 2, text=self._glyph, fill=glyph_fg,
                             font=("Segoe UI Emoji", 14))
        self.create_text(w / 2, h / 2, text=self._label, fill=fg,
                         font=(T.FONT, 12, "bold"))
        if self._badge:
            bw = 52
            round_rect(self, w - bw - 22, h / 2 - 11, w - 22, h / 2 + 11, 9,
                       fill="#2b2f3d", outline="")
            self.create_text(w - bw / 2 - 22, h / 2, text=self._badge,
                             fill="#aeb5c6", font=T.TINY)


class Launcher(tk.Tk):
    def __init__(self, on_choose):
        super().__init__()
        self._on_choose = on_choose
        self.title(APP_NAME)
        self.configure(bg=T.BG)
        w, h = 560, 500
        self.geometry(f"{w}x{h}")
        self.resizable(False, False)
        self._center(w, h)

        head = tk.Frame(self, bg=T.BG)
        head.pack(fill="x", padx=44, pady=(40, 0))
        mark = tk.Canvas(head, width=54, height=54, bg=T.BG, highlightthickness=0)
        mark.pack(side="left")
        round_rect(mark, 2, 2, 52, 52, 14, fill=T.ACCENT, outline="")
        mark.create_text(27, 27, text="▶", fill="#ffffff", font=("Segoe UI", 18, "bold"))
        titles = tk.Frame(head, bg=T.BG)
        titles.pack(side="left", padx=(16, 0), anchor="w")
        tk.Label(titles, text=APP_NAME, bg=T.BG, fg=T.TEXT,
                 font=(T.FONT, 21, "bold"), anchor="w").pack(anchor="w")
        tk.Label(titles, text="Choose a workspace to continue", bg=T.BG, fg=T.MUTED,
                 font=T.BODY, anchor="w").pack(anchor="w", pady=(3, 0))

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=44, pady=(30, 0))
        self._buttons = []
        for label, glyph, page, enabled, badge in (
            ("Image Generation", "🖼", "image", False, "Soon"),
            ("Video Generation", "🎞", "video", True, None),
            ("Motion Control", "🎛", "motion", False, "Soon"),
        ):
            b = WorkspaceButton(body, label, glyph,
                                command=(lambda p=page: self._choose(p)) if enabled else None,
                                enabled=enabled, primary=(page == "video"), badge=badge)
            b.pack(fill="x", pady=6)
            self._buttons.append(b)

        tk.Label(self, text=f"Version {VERSION}  ·  local build", bg=T.BG,
                 fg=T.MUTED_DARK, font=T.SMALL).pack(side="bottom", pady=18)

    def _center(self, w, h):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(40, (sh - h) // 2 - 60)}")

    def _choose(self, page):
        self._on_choose(page)

    def capture(self, path):
        from PIL import ImageGrab
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.focus_force()
        self.update_idletasks()
        self.update()
        x, y = self.winfo_rootx(), self.winfo_rooty()
        img = ImageGrab.grab(bbox=(x, y, x + self.winfo_width(), y + self.winfo_height()))
        img.save(path)
        self.attributes("-topmost", False)
        return path
