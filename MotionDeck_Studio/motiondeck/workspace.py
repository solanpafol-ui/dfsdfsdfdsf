"""Main window shell: sidebar, toolbar, method switch, panel row."""
import os
import time
import tkinter as tk

from . import theme as T
from .panel import PanelCard
from .store import APP_NAME, VERSION
from .widgets import Card, RoundButton
from .windows import LiveView, LogWindow

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
        self.log("Studio Engine Initialized — F7 = Logs, F8 = Live View, F9 = Browser.")
        self.protocol("WM_DELETE_WINDOW", self.on_app_close)
        self.add_panel()
        self.after(1000, self._tick)

    def _btn(self, parent, text, command, width, height=36, bg=T.SURFACE_2,
             fg=T.TEXT, hover=T.SURFACE_3, radius=8, font=T.SMALL_BOLD):
        return RoundButton(parent, text, command, bg=bg, fg=fg, hover=hover,
                           height=height, width=width, radius=radius, font=font)

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
        self.account_dropdown_btn = self._btn(acc_row, "No Accounts",
                                              self.toggle_account_list, 178,
                                              bg=T.SURFACE)
        self.account_dropdown_btn.pack(side="left", fill="x", expand=True)
        self._btn(acc_row, "+", self.open_accounts, 36, bg=T.ACCENT,
                  hover=T.ACCENT_HOVER,
                  font=(T.FONT, 13, "bold")).pack(side="left", padx=(6, 0))
        self.account_list_host = tk.Frame(side, bg=T.BG_DEEP)
        self.account_list_host.pack(fill="x", padx=16)
        tk.Label(side, text="QUEUE & HISTORY", bg=T.BG_DEEP, fg=T.MUTED,
                 font=T.TINY).pack(anchor="w", padx=16, pady=(12, 4))
        self.history_frame = tk.Frame(side, bg=T.BG_DEEP)
        self.history_frame.pack(fill="both", expand=True, padx=16)
        self.tools_card = Card(side, bg=T.SURFACE, pad=0, radius=12,
                               border=T.BORDER, height=96)
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
        self.add_tab_btn = self._btn(toolbar, "New workspace", self.add_panel, 150)
        self.add_tab_btn.pack(side="left")
        self.auto_btn = self._btn(toolbar, "Auto", self.open_auto_wizard, 80)
        self.auto_btn.pack(side="left", padx=(8, 0))
        self.settings_btn = self._btn(toolbar, "Settings", self.open_settings, 90)
        self.settings_btn.pack(side="left", padx=(8, 0))
        self.tab_info = tk.Label(toolbar, text="0 of 2 workspaces", bg=T.BG,
                                 fg=T.MUTED, font=T.SMALL)
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
        self.panel_row = tk.Frame(canvas, bg=T.BG)
        window = canvas.create_window(0, 0, anchor="nw", window=self.panel_row)
        self.panel_row.bind("<Configure>",
                            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(window, height=e.height))
        canvas.bind("<Shift-MouseWheel>",
                    lambda e: canvas.xview_scroll(int(-e.delta / 120), "units"))
        self._canvas = canvas

    # -------------------------------------------------------- method switch
    def _build_method_switch(self):
        row = tk.Frame(self, bg=T.BG_DEEP, highlightthickness=1,
                       highlightbackground=T.BORDER)
        b1 = tk.Label(row, text="M1", font=T.SMALL_BOLD, padx=14, pady=5,
                      cursor="hand2")
        b2 = tk.Label(row, text="M2", font=T.SMALL_BOLD, padx=14, pady=5,
                      cursor="hand2")
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
    def open_accounts(self, initial=None):
        from .accounts import AccountDialog
        AccountDialog(self, initial=initial)

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
        row.bind("<Button-1>", lambda _e, n=name: self.open_accounts(n))
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
        self.open_accounts()

    # ------------------------------------------------------------ history
    def add_history_item(self, title):
        row = tk.Frame(self.history_frame, bg=T.SURFACE_2, height=36,
                       highlightthickness=1, highlightbackground=T.BORDER)
        row.pack(fill="x", pady=2)
        row.pack_propagate(False)
        dot = tk.Label(row, text="●", bg=T.SURFACE_2, fg=T.ACCENT_HOVER,
                       font=T.TINY, padx=8)
        dot.pack(side="left")
        tk.Label(row, text=title, bg=T.SURFACE_2, fg=T.TEXT_DIM, font=T.TINY,
                 anchor="w").pack(side="left", fill="x", expand=True)
        status = tk.Label(row, text="queued", bg=T.SURFACE_2, fg=T.MUTED,
                          font=T.TINY, padx=8)
        status.pack(side="right")
        self.history_rows[title] = (row, dot, status)

    def update_history_status(self, title, text, color):
        entry = self.history_rows.get(title)
        if not entry:
            return
        _row, dot, status = entry
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
            self.log(f"[{job.get('profile', '-')}|TAB{job.get('panel', 0)}] "
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
            self.log_window = None
            return
        self.log_window = LogWindow(self)

    def open_live(self):
        if self.live_window is not None and self.live_window.winfo_exists():
            self.live_window.lift()
            return
        self.live_window = LiveView(self)

    def on_f9_toggle_browser(self):
        self.show_transient_popup("The browser window opens on the first Generate press")

    def log(self, message):
        line = f"[{time.strftime('%H:%M:%S')}] {message}"
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

    # ------------------------------------------------ compatibility aliases
    def toast(self, text, ms=2500):
        self.show_transient_popup(text, ms)

    def open_folder(self, job):
        folder = job.get("folder") or str(self.store.job_folder(job))
        try:
            os.startfile(folder)
        except Exception:
            self.show_transient_popup("Could not open the folder")

    def open_output(self):
        try:
            os.startfile(str(self.store.output_root()))
        except Exception:
            self.show_transient_popup("Could not open the output folder")

    def open_settings(self):
        from .pages import SettingsPage
        win = tk.Toplevel(self)
        win.title("Settings")
        win.configure(bg=T.BG)
        win.geometry("900x740")
        page = SettingsPage(win, self)
        page.pack(fill="both", expand=True)
        page.refresh()

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
        img = ImageGrab.grab(bbox=(x, y, x + self.winfo_width(),
                                   y + self.winfo_height()))
        img.save(path)
        self.attributes("-topmost", False)
        return path

    def show(self, key):
        return None

    def set_service(self, key):
        return None

    def refresh_all(self):
        for panel in self.panels:
            panel.refresh()
        self.refresh_account_ui()
        self._update_tools_card()