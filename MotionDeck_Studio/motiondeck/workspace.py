"""Main window — the shell the original builds in `DolaStudioMaster`.

Layout is taken from the original source (`unpacked_main/app6.py`, line 104900+):

    sidebar (264)            brand · ACCOUNT · account dropdown + [+] · list
                             QUEUE & HISTORY · rows
                             tools_card: Total Rendered / Generations / Version
    main_frame               toolbar: New workspace · Auto · "0 of 2 workspaces"
                             panels row (one GenPanel per workspace)
    top centre               M1 | M2   (the method switch, `vp_method` 1 or 2)

Hotkeys in the original: F7 = logs, F8 = live view, F9 = browser toggle.

`vp_method` picks which route a generation takes. Method 1 and Method 2 both end
up driving dola.com in the original, and Method 2 is geo-gated there. That layer
is not copied and nothing was substituted for it — the engine slot stays empty.
"""
import os
import time
import tkinter as tk

from . import theme as T
from .dialogs import LiveView, LogDialog
from .panel import PanelCard
from .store import APP_NAME, VERSION
from .widgets import Card, RoundButton, round_rect

MAX_WORKSPACES = 2


class Workspace(tk.Tk):
    def __init__(self, store, engine, page="studio", size=(1280, 820),
                 position=(40, 16)):
        super().__init__()
        self.store = store
        self.engine = engine
        self.vp_method = 1
        self.panels = []
        self.log_lines = []
        self.log_window = None
        self.live_window = None
        self.history_rows = {}
        self._alive = True
        self._toast = None
        self._toast_after = None
        self._account_list_open = False

        self.title(f"{APP_NAME} {VERSION}")
        self.geometry(f"{size[0]}x{size[1]}+{position[0]}+{position[1]}")
        self.minsize(1120, 700)
        self.configure(bg=T.BG)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._build_sidebar()
        self._build_main()
        self._build_method_switch()

        self.bind_all("<F7>", self.toggle_log_popup)
        self.bind_all("<F8>", lambda _e: self.open_live())
        self.bind_all("<F9>", lambda _e: self.on_f9_toggle_browser())
        self.log(f"Studio Engine Initialized — F7 = Logs, F8 = Live View, F9 = Browser.")
        self.protocol("WM_DELETE_WINDOW", self.on_app_close)

        self.add_panel()
        self.after(1000, self._tick)

    # ------------------------------------------------------------- sidebar
    def _build_sidebar(self):
        side = tk.Frame(self, bg=T.BG_DEEP, width=264, highlightthickness=1,
                        highlightbackground=T.BORDER)
        side.grid(row=0, column=0, sticky="nsew")
        side.pack_propagate(False)
        self.sidebar = side

        tk.Label(side, text="MotionDeck", bg=T.BG_DEEP, fg=T.TEXT,
                 font=(T.FONT, 21, "bold")).pack(anchor="w", padx=16, pady=(18, 10))

        tk.Label(side, text="ACCOUNT", bg=T.BG_DEEP, fg=T.MUTED,
                 font=T.TINY).pack(anchor="w", padx=16, pady=(4, 4))
        acc_row = tk.Frame(side, bg=T.BG_DEEP)
        acc_row.pack(fill="x", padx=16)
        self.account_dropdown_btn = RoundButton(acc_row, "No Accounts",
                                                self.toggle_account_list, bg=T.SURFACE,
                                                fg=T.TEXT, hover=T.SURFACE_2, height=36,
                                                width=178, radius=8, font=T.SMALL_BOLD)
        self.account_dropdown_btn.pack(side="left", fill="x", expand=True)
        RoundButton(acc_row, "+", self.open_add_account_popup, bg=T.ACCENT,
                    hover=T.ACCENT_HOVER, height=36, width=36, radius=8,
                    font=(T.FONT, 13, "bold")).pack(side="left", padx=(6, 0))

        self.account_list_host = tk.Frame(side, bg=T.BG_DEEP)
        self.account_list_host.pack(fill="x", padx=16)

        tk.Label(side, text="QUEUE & HISTORY", bg=T.BG_DEEP, fg=T.MUTED,
                 font=T.TINY).pack(anchor="w", padx=16, pady=(12, 4))
        self.history_frame = tk.Frame(side, bg=T.BG_DEEP)
        self.history_frame.pack(fill="both", expand=True, padx=16)

        self.tools_card = Card(side, bg=T.SURFACE, pad=0, radius=12, border=T.BORDER,
                               height=96)
        self.tools_card.pack(fill="x", padx=12, pady=12)
        box = self.tools_card.body
        self.count_label = tk.Label(box, text="Total Rendered: 0", bg=T.SURFACE,
                                    fg=T.ACCENT_HOVER, font=T.SMALL_BOLD)
        self.count_label.pack(anchor="w", padx=12, pady=(8, 2))
        self.gen_limit_label = tk.Label(box, text="Generations: 0/∞", bg=T.SURFACE,
                                        fg=T.TEXT_DIM, font=T.SMALL_BOLD)
        self.gen_limit_label.pack(anchor="w", padx=12, pady=(0, 2))
        tk.Label(box, text=f"Version {VERSION}", bg=T.SURFACE, fg=T.MUTED,
                 font=T.TINY).pack(anchor="w", padx=12, pady=(0, 8))

    # ---------------------------------------------------------------- main
    def _build_main(self):
        main = tk.Frame(self, bg=T.BG)
        main.grid(row=0, column=1, padx=16, pady=14, sticky="nsew")
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)
        self.main_frame = main

        toolbar = tk.Frame(main, bg=T.BG, height=36)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.add_tab_btn = RoundButton(toolbar, "New workspace", self.add_panel,
                                       bg=T.SURFACE_2, fg=T.TEXT, hover=T.SURFACE_3,
                                       height=36, width=150, radius=8, font=T.SMALL_BOLD)
        self.add_tab_btn.pack(side="left")
        self.auto_btn = RoundButton(toolbar, "Auto", self.open_auto_wizard,
                                    bg=T.SURFACE_2, fg=T.TEXT, hover=T.SURFACE_3,
                                    height=36, width=80, radius=8, font=T.SMALL_BOLD)
        self.auto_btn.pack(side="left", padx=(8, 0))
        self.tab_info = tk.Label(toolbar, text="0 of 2 workspaces", bg=T.BG, fg=T.MUTED,
                                 font=T.SMALL)
        self.tab_info.pack(side="left", padx=(12, 0))

        body = tk.Frame(main, bg=T.BG)
        body.grid(row=1, column=0, sticky="nsew")
        canvas = tk.Canvas(body, bg=T.BG, highlightthickness=0, bd=0)
        bar = tk.Scrollbar(body, orient="horizontal", command=canvas.xview, width=6,
                           troughcolor=T.BG, bg=T.SURFACE_3, relief="flat", bd=0,
                           highlightthickness=0, activebackground=T.MUTED_DARK)
        canvas.configure(xscrollcommand=bar.set)
        canvas.pack(side="top", fill="both", expand=True)
        bar.pack(side="bottom", fill="x")
        self._scrollbar = bar
        self.panel_row = tk.Frame(canvas, bg=T.BG)
        window = canvas.create_window(0, 0, anchor="nw", window=self.panel_row)
        self.panel_row.bind("<Configure>",
                            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, height=e.height))
        canvas.bind("<Shift-MouseWheel>",
                    lambda e: canvas.xview_scroll(int(-e.delta / 120), "units"))
        self._canvas = canvas

    # -------------------------------------------------------- method switch
    def _build_method_switch(self):
        row = tk.Frame(self, bg=T.BG_DEEP, highlightthickness=1,
                       highlightbackground=T.BORDER)
        b1 = tk.Label(row, text="M1", font=T.SMALL_BOLD, padx=14, pady=5, cursor="hand2")
        b2 = tk.Label(row, text="M2", font=T.SMALL_BOLD, padx=14, pady=5, cursor="hand2")
        b1.pack(side="left", padx=(6, 2), pady=5)
        b2.pack(side="left", padx=(2, 6), pady=5)
        b1.bind("<Button-1>", lambda _e: self.set_method(1))
        b2.bind("<Button-1>", lambda _e: self.set_method(2))
        row.place(relx=0.5, rely=0.0, x=0, y=6, anchor="n")
        row.lift()
        self.vp_m1_btn, self.vp_m2_btn = b1, b2
        self._paint_method()

    def _paint_method(self):
        for method, btn in ((1, self.vp_m1_btn), (2, self.vp_m2_btn)):
            if method == self.vp_method:
                btn.configure(bg=T.ACCENT, fg="#ffffff")
            else:
                btn.configure(bg=T.BG_DEEP, fg=T.TEXT_DIM)

    def set_method(self, method):
        if method == self.vp_method:
            return
        self.vp_method = method
        self._paint_method()
        # ribbon-visible rule from the original: Method 2 hides the Auto button.
        if method == 1:
            self.auto_btn.pack(side="left", padx=(8, 0), after=self.add_tab_btn)
        else:
            self.auto_btn.pack_forget()
        self.log(f"Method {method} selected")

    # ------------------------------------------------------------- panels
    def _profiles(self):
        profiles = self.store.config.get("profiles")
        if not profiles:
            profiles = ["Profile 1"]
            self.store.config["profiles"] = profiles
            self.store.save_config()
        return profiles

    def add_panel(self):
        profiles = self._profiles()
        if len(self.panels) >= MAX_WORKSPACES:
            self.show_transient_popup(f"{MAX_WORKSPACES} workspaces is the limit")
            return
        index = len(self.panels)
        profile = profiles[min(index, len(profiles) - 1)]
        panel = PanelCard(self.panel_row, self, index, profile)
        panel.pack(side="left", fill="both", padx=(0, 12), pady=2)
        self.panels.append(panel)
        self._update_tab_info()
        self.refresh_account_ui()
        self.log(f"Workspace 0{index + 1} opened · {profile}")

    def remove_panel(self, panel):
        if len(self.panels) <= 1:
            self.show_transient_popup("Keep at least one workspace")
            return
        panel.destroy()
        self.panels.remove(panel)
        self._update_tab_info()
        self.refresh_account_ui()

    def _update_tab_info(self):
        self.tab_info.configure(
            text=f"{len(self.panels)} of {MAX_WORKSPACES} workspaces")

    # ----------------------------------------------------------- accounts
    def toggle_account_list(self):
        self._account_list_open = not self._account_list_open
        self.refresh_account_ui()

    def refresh_account_ui(self):
        profiles = self._profiles()
        self.account_dropdown_btn.set_text(
            f"{len(profiles)} Accounts" if len(profiles) != 1 else profiles[0])
        for w in self.account_list_host.winfo_children():
            w.destroy()
        if not self._account_list_open:
            return
        for name in profiles:
            self._account_row(self.account_list_host, name)

    def _account_row(self, host, name):
        credits = self.store.credits(name)
        renders = self.store.rendered_count(name)
        wait = self.store.cooldown_left(name)
        running = any(j.get("profile") == name and j.get("status") == "running"
                      for j in self.store.jobs)
        row = tk.Frame(host, bg=T.SURFACE, height=34, highlightthickness=1,
                       highlightbackground=T.BORDER)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=name, bg=T.SURFACE, fg=T.TEXT, font=T.SMALL_BOLD,
                 padx=8).pack(side="left")
        if running:
            state, fg = "rendering", T.ACCENT_HOVER
        elif wait:
            state, fg = f"cooldown {wait}s", T.YELLOW
        elif credits <= 0:
            state, fg = "no credits", T.RED
        else:
            state, fg = "ready", T.GREEN
        tk.Label(row, text=state, bg=T.SURFACE, fg=fg, font=T.TINY).pack(side="left")
        tk.Label(row, text=f"{renders} rendered · CR {credits}", bg=T.SURFACE,
                 fg=T.MUTED_DARK, font=T.TINY, padx=6).pack(side="right")

    def open_add_account_popup(self):
        profiles = self._profiles()
        profiles.append(f"Profile {len(profiles) + 1}")
        self.store.save_config()
        self.refresh_account_ui()
        self.show_transient_popup(f"Added Profile {len(profiles)}")

    # ------------------------------------------------------------ history
    def add_history_item(self, title):
        row = tk.Frame(self.history_frame, bg=T.SURFACE_2, height=36,
                       highlightthickness=1, highlightbackground=T.BORDER)
        row.pack(fill="x", pady=2)
        row.pack_propagate(False)
        dot = tk.Label(row, text="●", bg=T.SURFACE_2, fg=T.ACCENT_HOVER, font=T.TINY,
                       padx=8)
        dot.pack(side="left")
        name = tk.Label(row, text=title, bg=T.SURFACE_2, fg=T.TEXT_DIM, font=T.TINY,
                        anchor="w")
        name.pack(side="left", fill="x", expand=True)
        status = tk.Label(row, text="queued", bg=T.SURFACE_2, fg=T.MUTED, font=T.TINY,
                          padx=8)
        status.pack(side="right")
        self.history_rows[title] = (row, dot, status)

    def update_history_status(self, title, text, color):
        entry = self.history_rows.get(title)
        if not entry:
            return
        row, dot, status = entry
        status.configure(text=text, fg=color)
        dot.configure(fg=color)

    # -------------------------------------------------------------- events
    def on_event(self, kind, job):
        self.after(0, lambda: self._event(kind, job))

    def _event(self, kind, job):
        if kind == "finished":
            status = job.get("status")
            color = {"done": T.GREEN, "failed": T.RED}.get(status, T.MUTED)
            self.update_history_status((job.get("prompt") or "")[:40], status, color)
            self.log(f"[{job.get('profile', '—')}|TAB{job.get('panel', 0)}] "
                     f"{status} · {(job.get('prompt') or '')[:48]}")
        for panel in self.panels:
            panel.refresh()
        self.refresh_account_ui()
        self._update_tools_card()

    def _update_tools_card(self):
        self.count_label.configure(
            text=f"Total Rendered: {self.store.rendered_count()}")
        running = self.engine.stats()
        self.gen_limit_label.configure(
            text=f"Generations: {running['running'] + running['queued']}/∞")

    def _tick(self):
        if not self._alive:
            return
        try:
            for panel in self.panels:
                panel.refresh()
            self.refresh_account_ui()
            self._update_tools_card()
        except Exception:
            pass
        self.after(1000, self._tick)

    # ------------------------------------------------------------- windows
    def toggle_log_popup(self, event=None):
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.destroy()
            return
        LogDialog(self)

    def open_live(self):
        if self.live_window is not None and self.live_window.winfo_exists():
            self.live_window.lift()
            return
        LiveView(self)

    def on_f9_toggle_browser(self):
        self.show_transient_popup("Browser slot is empty — the original drives "
                                  "dola.com here")

    def log(self, message):
        stamp = time.strftime("%H:%M:%S")
        line = f"[{stamp}] {message}"
        self.log_lines.append(line)
        if len(self.log_lines) > 500:
            del self.log_lines[:100]
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.append(line)

    def play(self, job):
        files = [f for f in job.get("files", [])
                 if str(f).lower().endswith((".mp4", ".mov", ".webm"))]
        if not files:
            self.show_transient_popup("This clip has no video file yet")
            return
        try:
            os.startfile(files[0])
        except Exception as exc:
            self.show_transient_popup(f"Could not play it: {exc}")

    def show_transient_popup(self, text, ms=2500):
        if self._toast:
            self._toast.destroy()
        self._toast = tk.Label(self, text=text, bg=T.SURFACE_3, fg=T.TEXT,
                               font=T.SMALL, padx=16, pady=10)
        self._toast.place(relx=0.5, rely=0.97, anchor="s")
        if self._toast_after:
            self.after_cancel(self._toast_after)
        self._toast_after = self.after(ms, self._clear_toast)

    def _clear_toast(self):
        if self._toast:
            self._toast.destroy()
            self._toast = None

    # -------------------------------------------------------------- misc
    def open_auto_wizard(self):
        from .batch import AutoWizard
        AutoWizard(self, self.panels[0] if self.panels else None)

    def on_app_close(self):
        self._alive = False
        self.engine.shutdown()
        self.destroy()

    def capture(self, path, settle=0.35):
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.focus_force()
        self.update_idletasks()
        self.update()
        if settle:
            end = time.time() + settle
            while time.time() < end:
                self.update()
                time.sleep(0.02)
        from PIL import ImageGrab
        x, y = self.winfo_rootx(), self.winfo_rooty()
        img = ImageGrab.grab(bbox=(x, y, x + self.winfo_width(), y + self.winfo_height()))
        img.save(path)
        self.attributes("-topmost", False)
        return path

    # compatibility with the older page-based entry points
    def show(self, key):
        return None

    def set_service(self, key):
        return None

    def refresh_all(self):
        for panel in self.panels:
            panel.refresh()
        self.refresh_account_ui()
        self._update_tools_card()
