"""F7 log tail and F8 live view, kept out of the shell module."""
import tkinter as tk

from . import theme as T
from .widgets import RoundButton


class LogWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Logs")
        self.geometry("780x420")
        self.configure(bg=T.BG_DEEP)
        self.body = tk.Text(self, bg=T.BG_DEEP, fg=T.TEXT_DIM, bd=0, wrap="word",
                            font=(T.MONO, 9), padx=10, pady=10)
        self.body.pack(fill="both", expand=True)
        for line in app.log_lines:
            self.body.insert("end", line + "\n")
        self.body.see("end")
        self.protocol("WM_DELETE_WINDOW", self._close)

    def append(self, line):
        try:
            self.body.insert("end", line + "\n")
            self.body.see("end")
        except Exception:
            pass

    def _close(self):
        self.app.log_window = None
        self.destroy()


class LiveView(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Live view")
        self.geometry("720x560")
        self.configure(bg=T.BG)
        tk.Label(self, text="LIVE", bg=T.BG, fg=T.MUTED_DARK,
                 font=(T.MONO, 8)).pack(anchor="w", padx=18, pady=(14, 6))
        self.host = tk.Frame(self, bg=T.BG)
        self.host.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self._alive = True
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.refresh()
        self.after(1000, self._tick)

    def refresh(self):
        for w in self.host.winfo_children():
            w.destroy()
        jobs = [j for j in self.app.store.jobs if j.get("status") in ("queued", "running")]
        done = [j for j in self.app.store.jobs if j.get("status") == "done"][:8]
        if not jobs and not done:
            tk.Label(self.host, text="Nothing is running.", bg=T.BG, fg=T.MUTED,
                     font=T.SMALL).pack(anchor="w")
            return
        for job in jobs:
            row = tk.Frame(self.host, bg=T.SURFACE, highlightthickness=1,
                           highlightbackground=T.BORDER)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=f"{job.get('profile', '-')} · {job.get('stage', '')}",
                     bg=T.SURFACE, fg=T.ACCENT_HOVER, font=T.SMALL_BOLD,
                     anchor="w").pack(side="left", padx=10, pady=6)
            tk.Label(row, text=(job.get("prompt") or "")[:60], bg=T.SURFACE,
                     fg=T.TEXT_DIM, font=T.TINY, anchor="w").pack(side="left", padx=6)
            tk.Label(row, text=f"{int(job.get('progress', 0) * 100)}%", bg=T.SURFACE,
                     fg=T.MUTED, font=T.TINY).pack(side="right", padx=10)
        if done:
            tk.Label(self.host, text="RECENT", bg=T.BG, fg=T.MUTED_DARK,
                     font=(T.MONO, 8)).pack(anchor="w", pady=(14, 4))
        for job in done:
            row = tk.Frame(self.host, bg=T.BG_DEEP)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=(job.get("prompt") or "")[:64], bg=T.BG_DEEP,
                     fg=T.TEXT_DIM, font=T.TINY, anchor="w").pack(side="left", padx=10, pady=5)
            RoundButton(row, "Play", lambda j=job: self.app.play(j), bg=T.SURFACE_2,
                        fg=T.TEXT_DIM, hover=T.SURFACE_3, height=24, width=52,
                        radius=6, font=T.TINY).pack(side="right", padx=6, pady=3)

    def _tick(self):
        if not self._alive:
            return
        try:
            self.refresh()
        except Exception:
            pass
        self.after(1000, self._tick)

    def _close(self):
        self._alive = False
        self.app.live_window = None
        self.destroy()