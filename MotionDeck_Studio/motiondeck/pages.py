"""The studio pages: queue, library, settings."""
import os
import time
import tkinter as tk
from pathlib import Path

from . import providers
from . import theme as T
from .widgets import (Card, Progress, Field, RoundButton, Scroll, Select, round_rect)
from .widgets import thumb  # noqa: E402  (shared with the studio panels)


def clear(widget):
    for child in widget.winfo_children():
        child.destroy()


def muted(parent, text, font=None, fg=T.MUTED):
    return tk.Label(parent, text=text, bg=parent["bg"], fg=fg,
                    font=font or T.SMALL, anchor="w", justify="left")


def heading(parent, text, sub=None):
    box = tk.Frame(parent, bg=parent["bg"])
    tk.Label(box, text=text, bg=parent["bg"], fg=T.TEXT, font=T.H1,
             anchor="w").pack(anchor="w")
    if sub:
        muted(box, sub).pack(anchor="w", pady=(2, 0))
    return box


def status_pill(parent, status):
    fg, bg = T.STATUS_COLORS.get(status, (T.MUTED, T.SURFACE_3))
    return tk.Label(parent, text=status.capitalize(), bg=bg, fg=fg,
                    font=T.TINY, padx=9, pady=3)


def _fmt_when(ms):
    if not ms:
        return "—"
    return time.strftime("%m.%d %H:%M", time.localtime(ms / 1000))


def _duration(job):
    if job.get("started_ms") and job.get("finished_ms"):
        return f"{(job['finished_ms'] - job['started_ms']) / 1000:.1f}s"
    return "—"


# ------------------------------------------------------------------------ queue
class QueuePage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.store = app.store
        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=26, pady=(6, 12))
        self.counts = muted(top, "")
        self.counts.pack(side="left")
        RoundButton(top, "Clear finished", self.clear_finished, bg=T.SURFACE,
                    fg=T.MUTED, hover=T.SURFACE_2, height=28, width=112,
                    radius=7, font=T.TINY).pack(side="right")
        self.scroll = Scroll(self, T.BG)
        self.scroll.pack(fill="both", expand=True, padx=26, pady=(0, 26))
        self.refresh()

    def clear_finished(self):
        keep = [j for j in self.store.jobs if j.get("status") in ("queued", "running")]
        removed = len(self.store.jobs) - len(keep)
        self.store.jobs = keep
        self.store.save_jobs()
        self.app.toast(f"Removed {removed} finished job(s) from the list")
        self.refresh()

    def refresh(self):
        clear(self.scroll.inner)
        jobs = self.store.jobs
        running = sum(1 for j in jobs if j.get("status") == "running")
        queued = sum(1 for j in jobs if j.get("status") == "queued")
        self.counts.configure(text=f"{running} rendering · {queued} queued · {len(jobs)} total")
        if not jobs:
            card = Card(self.scroll.inner, bg=T.SURFACE, pad=20, height=110)
            card.pack(fill="x")
            muted(card.body, "The queue is empty. Compose a brief on the Generate page.",
                  fg=T.MUTED_DARK).pack(anchor="w", pady=12)
            return
        for job in jobs:
            self._row(job)

    def _row(self, job):
        card = Card(self.scroll.inner, bg=T.SURFACE, pad=12, height=112)
        card.pack(fill="x", pady=(0, 10))
        b = card.body

        img = thumb(job.get("poster"), 124, 70)
        lbl = tk.Label(b, image=img, bg=T.SURFACE_2, bd=0)
        lbl.image = img
        lbl.pack(side="left", pady=2)

        mid = tk.Frame(b, bg=T.SURFACE)
        mid.pack(side="left", padx=14, fill="both", expand=True)
        prompt = (job.get("prompt") or "").replace("\n", " ")
        tk.Label(mid, text=prompt[:96] + ("…" if len(prompt) > 96 else ""),
                 bg=T.SURFACE, fg=T.TEXT, font=T.BODY_BOLD, anchor="w",
                 justify="left", wraplength=470).pack(anchor="w")
        meta = (f"{job.get('provider')} · {job.get('model')} · {job.get('duration')}s · "
                f"{job.get('aspect')} · {job.get('resolution')}")
        muted(mid, meta, font=T.TINY, fg=T.MUTED_DARK).pack(anchor="w", pady=(2, 6))
        if job.get("status") == "failed":
            muted(mid, job.get("error", "")[:150], font=T.TINY, fg=T.RED).pack(anchor="w")
        else:
            bar = Progress(mid, height=5, width=380)
            bar.pack(anchor="w")
            bar.set(job.get("progress", 0.0))
            muted(mid, f"{job.get('stage', '')}  ·  {int(job.get('progress', 0) * 100)}%",
                  font=T.TINY, fg=T.MUTED_DARK).pack(anchor="w", pady=(3, 0))

        right = tk.Frame(b, bg=T.SURFACE)
        right.pack(side="right", fill="y")
        status_pill(right, job.get("status", "queued")).pack(anchor="e")
        muted(right, _fmt_when(job.get("created_ms")), font=T.TINY,
              fg=T.MUTED_DARK).pack(anchor="e", pady=(4, 6))
        actions = tk.Frame(right, bg=T.SURFACE)
        actions.pack(anchor="e")
        if job.get("status") in ("queued", "running"):
            RoundButton(actions, "Cancel", lambda j=job: self._cancel(j), bg=T.SURFACE_2,
                        fg=T.TEXT_DIM, hover=T.SURFACE_3, height=26, width=62,
                        radius=6, font=T.TINY).pack(side="left")
        elif job.get("status") in ("failed", "cancelled"):
            RoundButton(actions, "Retry", lambda j=job: self._retry(j), bg=T.SURFACE_2,
                        fg=T.TEXT_DIM, hover=T.SURFACE_3, height=26, width=62,
                        radius=6, font=T.TINY).pack(side="left")
        if job.get("status") == "done":
            RoundButton(actions, "Play", lambda j=job: self.app.play(j), bg=T.SURFACE_2,
                        fg=T.TEXT_DIM, hover=T.SURFACE_3, height=26, width=52,
                        radius=6, font=T.TINY).pack(side="left")
            RoundButton(actions, "Folder", lambda j=job: self.app.open_folder(j),
                        bg=T.SURFACE_2, fg=T.TEXT_DIM, hover=T.SURFACE_3, height=26,
                        width=62, radius=6, font=T.TINY).pack(side="left", padx=(6, 0))

    def _cancel(self, job):
        self.app.engine.cancel(job["id"])
        self.refresh()

    def _retry(self, job):
        self.app.engine.retry(job["id"])
        self.refresh()


# ---------------------------------------------------------------------- library
class LibraryPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.store = app.store
        top = tk.Frame(self, bg=T.BG)
        top.pack(fill="x", padx=26, pady=(6, 12))
        self.counts = muted(top, "")
        self.counts.pack(side="left")
        RoundButton(top, "Open folder", lambda: self.app.open_output(), bg=T.SURFACE,
                    fg=T.MUTED, hover=T.SURFACE_2, height=28, width=112, radius=7,
                    font=T.TINY).pack(side="right")
        self.scroll = Scroll(self, T.BG)
        self.scroll.pack(fill="both", expand=True, padx=26, pady=(0, 26))
        self.refresh()

    def refresh(self):
        clear(self.scroll.inner)
        done = [j for j in self.store.jobs if j.get("status") == "done"]
        self.counts.configure(text=f"{len(done)} finished clip(s) in {self.store.output_root()}")
        if not done:
            card = Card(self.scroll.inner, bg=T.SURFACE, pad=20, height=120)
            card.pack(fill="x")
            muted(card.body, "No finished clips yet. Renders land here when the queue is done.",
                  fg=T.MUTED_DARK).pack(anchor="w", pady=12)
            return
        grid = tk.Frame(self.scroll.inner, bg=T.BG)
        grid.pack(fill="both", expand=True)
        for i in range(3):
            grid.grid_columnconfigure(i, weight=1, uniform="lib")
        for idx, job in enumerate(done):
            tile = Card(grid, bg=T.SURFACE, pad=10, height=246)
            tile.grid(row=idx // 3, column=idx % 3, sticky="nsew", padx=(0, 12),
                      pady=(0, 12))
            b = tile.body
            img = thumb(job.get("poster"), 268, 138)
            lbl = tk.Label(b, image=img, bg=T.SURFACE_2, bd=0)
            lbl.image = img
            lbl.pack(fill="x")
            prompt = (job.get("prompt") or "").replace("\n", " ")
            tk.Label(b, text=prompt[:70] + ("…" if len(prompt) > 70 else ""),
                     bg=T.SURFACE, fg=T.TEXT, font=T.SMALL, anchor="w",
                     justify="left", wraplength=264).pack(anchor="w", pady=(8, 2))
            muted(b, f"{_fmt_when(job.get('created_ms'))} · {job.get('duration')}s · "
                     f"{job.get('aspect')} · {_duration(job)}", font=T.TINY,
                  fg=T.MUTED_DARK).pack(anchor="w")
            row = tk.Frame(b, bg=T.SURFACE)
            row.pack(anchor="w", pady=(8, 0))
            RoundButton(row, "Play", lambda j=job: self.app.play(j), bg=T.ACCENT,
                        hover=T.ACCENT_HOVER, height=26, width=62, radius=6,
                        font=T.TINY).pack(side="left")
            RoundButton(row, "Folder", lambda j=job: self.app.open_folder(j),
                        bg=T.SURFACE_2, fg=T.TEXT_DIM, hover=T.SURFACE_3, height=26,
                        width=66, radius=6).pack(side="left", padx=(6, 0))


# --------------------------------------------------------------------- settings
class SettingsPage(tk.Frame):
    LABELS = {"browser": "Seedance via dola.com (browser)",
              "ark": "Seedance via Ark API (your key)"}

    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.store = app.store
        scroll = Scroll(self, T.BG)
        scroll.pack(fill="both", expand=True)
        root = tk.Frame(scroll.inner, bg=T.BG)
        root.pack(fill="both", expand=True, padx=26, pady=(6, 26))

        card = Card(root, bg=T.SURFACE, pad=22, height=596)
        card.pack(fill="x", pady=(0, 16))
        b = card.body
        heading(b, "Render backend",
                "Pick where clips come from. The browser backend opens d