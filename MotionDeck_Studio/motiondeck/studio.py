"""The workspace: one panel per account, a history strip under them."""
import time
import tkinter as tk

from . import theme as T
from .panel import PanelCard
from .widgets import RoundButton, round_rect


class StudioPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.store = app.store
        self.panels = []
        self._signature = None
        self._scroll = None

    # ------------------------------------------------------------------ layout
    def refresh(self):
        signature = tuple(self._profiles())
        if signature != self._signature:
            self._signature = signature
            self._rebuild()
        self._fill_accounts()
        for panel in self.panels:
            panel.refresh()
        self._fill_history()

    def _profiles(self):
        profiles = self.store.config.get("profiles")
        if not profiles:
            profiles = ["Profile 1"]
            self.store.config["profiles"] = profiles
            self.store.save_config()
        return profiles

    def _rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.panels = []

        self._build_accounts()

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=18, pady=(2, 8))

        canvas = tk.Canvas(body, bg=T.BG, highlightthickness=0, bd=0)
        bar = tk.Scrollbar(body, orient="horizontal", command=canvas.xview, width=6,
                           troughcolor=T.BG, bg=T.SURFACE_3, relief="flat", bd=0,
                           highlightthickness=0, activebackground=T.MUTED_DARK)
        canvas.configure(xscrollcommand=bar.set)
        canvas.pack(side="top", fill="both", expand=True)
        bar.pack(side="bottom", fill="x")
        self._scrollbar = bar
        self.after(80, lambda: self._maybe_scrollbar(canvas, bar, row))

        row = tk.Frame(canvas, bg=T.BG)
        window = canvas.create_window(0, 0, anchor="nw", window=row)
        row.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, height=e.height))
        canvas.bind("<Shift-MouseWheel>",
                    lambda e: canvas.xview_scroll(int(-e.delta / 120), "units"))

        for i, profile in enumerate(self._profiles()):
            panel = PanelCard(row, self.app, i, profile)
            panel.pack(side="left", fill="both", padx=(0, 12))
            self.panels.append(panel)

        self._build_history()

    def _maybe_scrollbar(self, canvas, bar, row):
        try:
            if row.winfo_reqwidth() <= canvas.winfo_width() + 4:
                bar.pack_forget()
            elif not bar.winfo_ismapped():
                bar.pack(side="bottom", fill="x")
        except Exception:
            pass

    # ---------------------------------------------------------------- accounts
    def _build_accounts(self):
        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=24, pady=(2, 8))
        tk.Label(bar, text="ACCOUNTS", bg=T.BG, fg=T.MUTED_DARK,
                 font=(T.MONO, 7)).pack(side="left")
        self._chips = tk.Frame(bar, bg=T.BG)
        self._chips.pack(side="left")
        RoundButton(bar, "+ Add account", self._add_profile, bg=T.SURFACE, fg=T.MUTED,
                    hover=T.SURFACE_2, height=24, width=104, radius=6,
                    font=T.TINY).pack(side="left", padx=10)
        tk.Label(bar, text="accounts here are local profiles: name, key and defaults",
                 bg=T.BG, fg=T.MUTED_DARK, font=T.TINY).pack(side="left", padx=8)
        self._account_sig = None
        self._fill_accounts()

    def _account_state(self, name):
        credits = self.store.credits(name)
        renders = self.store.rendered_count(name)
        wait = self.store.cooldown_left(name)
        running = any(j.get("profile") == name and j.get("status") == "running"
                      for j in self.store.jobs)
        return credits, renders, wait, running

    def _fill_accounts(self):
        """Rebuild the chips only when what they say has actually changed."""
        if not hasattr(self, "_chips") or not self._chips.winfo_exists():
            return
        state = tuple((n,) + self._account_state(n) for n in self._profiles())
        if state == self._account_sig:
            return
        self._account_sig = state
        for w in self._chips.winfo_children():
            w.destroy()
        for name, credits, renders, wait, running in state:
            self._account_chip(self._chips, name, credits, renders, wait, running)

    def _account_chip(self, bar, name, credits, renders, wait, running):
        """One account: renders so far, credits left, and what it is doing now."""
        chip = tk.Frame(bar, bg=T.SURFACE_2)
        chip.pack(side="left", padx=(10, 0))
        tk.Label(chip, text=name, bg=T.SURFACE_2, fg=T.TEXT_DIM, font=T.TINY,
                 padx=10, pady=4).pack(side="left")
        if running:
            state, fg = "rendering", T.ACCENT_HOVER
        elif wait:
            state, fg = f"cooldown {wait}s", T.YELLOW
        elif credits <= 0:
            state, fg = "no credits", T.RED
        else:
            state, fg = "ready", T.GREEN
        tk.Label(chip, text=state, bg=T.SURFACE_2, fg=fg, font=T.TINY,
                 padx=2).pack(side="left")
        tk.Label(chip, text=f"{renders} rendered · CR {credits}", bg=T.SURFACE_2,
                 fg=T.MUTED_DARK, font=T.TINY, padx=6).pack(side="left")
        close = tk.Label(chip, text="✕", bg=T.SURFACE_2, fg=T.MUTED_DARK, font=T.TINY,
                         padx=6, cursor="hand2")
        close.pack(side="left")
        close.bind("<Button-1>", lambda _e, n=name: self._remove_profile(n))

    def _add_profile(self):
        profiles = self._profiles()
        profiles.append(f"Profile {len(profiles) + 1}")
        self.store.save_config()
        self.refresh()

    def _remove_profile(self, name):
        profiles = self._profiles()
        if len(profiles) <= 1:
            self.app.toast("Keep at least one account")
            return
        profiles.remove(name)
        self.store.save_config()
        self.refresh()

    # ----------------------------------------------------------------- history
    def _build_history(self):
        self.history = tk.Frame(self, bg=T.BG_DEEP)
        self.history.pack(fill="x", side="bottom")
        self._fill_history()

    def _fill_history(self):
        if not hasattr(self, "history"):
            return
        jobs = self.store.jobs[:5]
        done = sum(1 for j in self.store.jobs if j.get("status") == "done")
        sig = (tuple((j["id"], j.get("status")) for j in jobs), done)
        if sig == getattr(self, "_history_sig", None):
            return
        self._history_sig = sig
        for w in self.history.winfo_children():
            w.destroy()
        row = tk.Frame(self.history, bg=T.BG_DEEP)
        row.pack(fill="x", padx=24, pady=7)
        tk.Label(row, text="HISTORY", bg=T.BG_DEEP, fg=T.MUTED_DARK,
                 font=(T.MONO, 7)).pack(side="left")
        if not jobs:
            tk.Label(row, text="nothing yet", bg=T.BG_DEEP, fg=T.MUTED_DARK,
                     font=T.TINY).pack(side="left", padx=12)
        for job in jobs:
            status = job.get("status", "")
            fg = {"done": T.GREEN, "failed": T.RED,
                  "running": T.ACCENT_HOVER}.get(status, T.MUTED)
            text = (job.get("prompt") or "")[:30].replace("\n", " ")
            chip = tk.Label(row, text=f"{text} · {status}", bg=T.BG_DEEP, fg=fg,
                            font=T.TINY, padx=6, cursor="hand2")
            chip.pack(side="left", padx=(8, 0))
            chip.bind("<Button-1>", lambda _e, j=job: self.app.play(j))
        tk.Label(row, text=f"total rendered {done}", bg=T.BG_DEEP, fg=T.MUTED_DARK,
                 font=T.TINY).pack(side="right")
