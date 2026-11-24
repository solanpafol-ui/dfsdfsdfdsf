"""Secondary windows: the live view and the log."""
import time
import tkinter as tk

from . import theme as T
from .widgets import Progress, RoundButton, Scroll, thumb


class LogDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Log")
        self.configure(bg=T.BG)
        self.geometry("720x420+140+90")
        self.transient(app)

        head = tk.Frame(self, bg=T.BG)
        head.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(head, text="Log", bg=T.BG, fg=T.TEXT, font=T.H1).pack(side="left")
        RoundButton(head, "Clear", self._clear, bg=T.SURFACE, fg=T.MUTED,
                    hover=T.SURFACE_2, height=26, width=70, radius=6,
                    font=T.TINY).pack(side="right")

        self.text = tk.Text(self, bg=T.INPUT, fg=T.TEXT_DIM, relief="flat", bd=0,
                            font=(T.MONO, 8), wrap="word", padx=12, pady=10)
        self.text.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        for line in app.log_lines:
            self._append(line)
        app.log_window = self
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _append(self, line):
        self.text.insert("end", line + "\n")
        self.text.see("end")

    def append(self, line):
        self._append(line)

    def _clear(self):
        self.app.log_lines.clear()
        self.text.delete("1.0", "end")

    def _close(self):
        self.app.log_window = None
        self.destroy()


class LiveView(tk.Toplevel):
    """The panel the original calls 'Live view': what the current job looks like."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Live view")
        self.configure(bg=T.BG)
        self.geometry("560x520+140+90")
        self.transient(app)
        self._after = None

        self.frame = tk.Frame(self, bg=T.BG)
        self.frame.pack(fill="both", expand=True, padx=16, pady=14)

        self.poster = tk.Canvas(self.frame, bg=T.SURFACE_2, height=280,
                                highlightthickness=0, bd=0)
        self.poster.pack(fill="x")
        self.poster.create_text(250, 140, text="no render yet", fill=T.MUTED_DARK,
                                font=T.SMALL, tags="empty")
        self.title_lbl = tk.Label(self.frame, text="", bg=T.BG, fg=T.TEXT, font=T.BODY_BOLD,
                                  anchor="w", justify="left", wraplength=500)
        self.title_lbl.pack(fill="x", pady=(10, 4))
        self.meta = tk.Label(self.frame, text="", bg=T.BG, fg=T.MUTED, font=T.TINY,
                             anchor="w")
        self.meta.pack(fill="x")
        self.bar = Progress(self.frame, height=8, width=500)
        self.bar.pack(fill="x", pady=(10, 4))
        self.stage = tk.Label(self.frame, text="", bg=T.BG, fg=T.MUTED_DARK, font=T.TINY,
                              anchor="w")
        self.stage.pack(fill="x")
        actions = tk.Frame(self.frame, bg=T.BG)
        actions.pack(fill="x", pady=(12, 0))
        RoundButton(actions, "Play", self._play, bg=T.ACCENT, hover=T.ACCENT_HOVER,
                    height=30, width=80, radius=7, font=T.SMALL).pack(side="left")
        RoundButton(actions, "Open folder", self._folder, bg=T.SURFACE_2, fg=T.TEXT_DIM,
                    hover=T.SURFACE_3, height=30, width=110, radius=7,
                    font=T.SMALL).pack(side="left", padx=8)
        tk.Label(actions, text="F9 closes this window", bg=T.BG, fg=T.MUTED_DARK,
                 font=T.TINY).pack(side="right")

        app.live_window = self
        self.bind("<F9>", lambda _e: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._tick()

    def _job(self):
        for job in self.app.store.jobs:
            if job.get("status") in ("running", "queued"):
                return job
        return self.app.store.jobs[0] if self.app.store.jobs else None

    def _tick(self):
        job = self._job()
        if job:
            prompt = (job.get("prompt") or "").replace("\n", " ")
            self.title_lbl.configure(text=prompt[:160])
            self.meta.configure(text=f"{job.get('profile', '—')} · {job.get('provider')} · "
                                     f"{job.get('duration')}s · {job.get('aspect')} · "
                                     f"{job.get('status')}")
            self.bar.set(job.get("progress", 0.0))
            self.stage.configure(text=f"{job.get('stage', '')} · "
                                      f"{int(job.get('progress', 0) * 100)}%")
            if job.get("poster"):
                img = thumb(job["poster"], 528, 280)
                self.poster.delete("all")
                self.poster.create_image(264, 140, image=img)
                self.poster.image = img
            else:
                self.poster.delete("all")
                self.poster.create_text(264, 140, text="rendering…", fill=T.MUTED_DARK,
                                        font=T.SMALL)
            self.job = job
        else:
            self.title_lbl.configure(text="No job yet")
            self.meta.configure(text="")
            self.stage.configure(text="")
            self.bar.set(0)
            self.job = None
        self._after = self.after(700, self._tick)

    def _play(self):
        job = getattr(self, "job", None)
        if job:
            self.app.play(job)

    def _folder(self):
        job = getattr(self, "job", None)
        if job:
            self.app.open_folder(job)

    def _close(self):
        if self._after:
            self.after_cancel(self._after)
        self.app.live_window = None
        self.destroy()
