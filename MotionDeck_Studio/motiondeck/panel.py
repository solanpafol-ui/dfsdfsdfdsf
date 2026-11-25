"""One workspace panel — the same card the original builds in `GenPanel`."""
import shutil
import time
import tkinter as tk
from pathlib import Path

from . import browser as browser_mod
from . import cookies as ck
from . import skills as skills_mod
from . import store as store_mod
from . import theme as T
from .store import new_job
from .widgets import Card, Progress, RoundButton, Select, TextBox, thumb

MODES = [("t2v", "Standard Mode"), ("r2v", "Pro Mode"), ("legit", "Legit Mode")]
DURATIONS = ["5s", "10s", "15s", "30s", "45s", "60s"]
RATIOS = ["16:9", "9:16", "1:1"]
LEGIT_IMAGE_CAP = 15          # legit-dur-cap-v16: Legit + images => 15s max


class PanelCard(tk.Frame):
    def __init__(self, parent, app, index, profile):
        super().__init__(parent, bg=T.BG)
        self.app = app
        self.store = app.store
        self.index = index
        self.profile = profile
        self.references = []
        self.last_ids = []
        self.mode_key = "t2v"
        self._result_sig = "__init__"
        self.configure(width=392)
        self.pack_propagate(False)

        self.card = Card(self, bg=T.SURFACE, pad=14, radius=12, border=T.BORDER)
        self.card.pack(fill="both", expand=True)
        b = self.card.body
        self.body = b

        # ---------------------------------------------------------- header
        head = tk.Frame(b, bg=T.SURFACE, height=36)
        head.pack(fill="x")
        self.title_lbl = tk.Label(head, text=f"Workspace 0{index + 1}", bg=T.SURFACE,
                                  fg=T.TEXT, font=T.H1)
        self.title_lbl.pack(side="left")
        self.close_btn = tk.Label(head, text="✕", bg=T.SURFACE, fg=T.MUTED_DARK,
                                  font=T.TINY, padx=6, cursor="hand2")
        self.close_btn.pack(side="right")
        self.close_btn.bind("<Button-1>", lambda _e: self.app.remove_panel(self))
        self.stream_badge = tk.Label(head, text="Standby", bg=T.SURFACE_2, fg=T.TEXT_DIM,
                                     font=T.TINY, padx=8, pady=2)
        self.stream_badge.pack(side="right", padx=(0, 6))
        self.account_badge = tk.Label(head, text=self.profile, bg=T.ACCENT_DIM,
                                      fg=T.ACCENT_HOVER, font=T.TINY, padx=8, pady=2,
                                      cursor="hand2")
        self.account_badge.pack(side="right", padx=(0, 6))
        self.account_badge.bind("<Button-1>", self._account_menu)
        self._account_menu_obj = tk.Menu(self, tearoff=0, bg=T.SURFACE, fg=T.TEXT,
                                         activebackground=T.ACCENT,
                                         activeforeground="#ffffff", bd=0)

        # -------------------------------------------------------- mode row
        mode_row = tk.Frame(b, bg=T.BG_DEEP, highlightthickness=1,
                            highlightbackground=T.BORDER, height=36)
        mode_row.pack(fill="x", pady=(8, 0))
        self._mode_buttons = {}
        for key, label in MODES:
            btn = tk.Label(mode_row, text=label, font=T.SMALL_BOLD, padx=10, pady=5,
                           cursor="hand2")
            btn.pack(side="left", padx=2, pady=3)
            btn.bind("<Button-1>", lambda _e, k=key: self.switch_mode(k))
            self._mode_buttons[key] = btn

        # ------------------------------------------------------ prompt box
        self.prompt = TextBox(b, height=5,
                              placeholder="Write the brief for this workspace…")
        self.prompt.pack(fill="x", pady=(8, 0))

        # --------------------------------------------------------- img row
        img_row = tk.Frame(b, bg=T.SURFACE, height=68)
        img_row.pack(fill="x", pady=(8, 0))
        self.img_counter = tk.Label(img_row, text="0/10 reference images", bg=T.SURFACE,
                                    fg=T.MUTED, font=T.TINY)
        self.img_counter.pack(side="left")
        RoundButton(img_row, "+ Add reference images", self.choose_images_dialog,
                    bg=T.SURFACE_2, fg=T.TEXT, hover=T.SURFACE_3, height=28, width=156,
                    radius=8, font=T.TINY).pack(side="right")
        RoundButton(img_row, "Clear all", self.clear_images, bg=T.SURFACE,
                    fg=T.TEXT_DIM, hover=T.SURFACE_2, height=24, width=66, radius=6,
                    font=T.TINY).pack(side="right", padx=6)
        self.thumb_host = tk.Frame(b, bg=T.BG_DEEP, highlightthickness=1,
                                   highlightbackground=T.BORDER, height=56)
        self.thumb_host.pack(fill="x", pady=(4, 0))
        self._fill_thumbs()

        # --------------------------------------------------- settings row
        srow = tk.Frame(b, bg=T.SURFACE, height=30)
        srow.pack(fill="x", pady=(8, 0))
        tk.Label(srow, text="Duration: ", bg=T.SURFACE, fg=T.MUTED,
                 font=T.SMALL_BOLD).pack(side="left")
        self.duration = Select(srow, "", DURATIONS,
                               f"{int(self.store.config.get('duration', 5))}s",
                               bg=T.SURFACE, width=4, on_change=lambda _v: self._paint_modes())
        self.duration._menu.configure(width=4)
        self.duration.pack(side="left", padx=(2, 10))
        tk.Label(srow, text="Ratio: ", bg=T.SURFACE, fg=T.MUTED,
                 font=T.SMALL_BOLD).pack(side="left")
        self.ratio = Select(srow, "", RATIOS, self.store.config.get("aspect", "16:9"),
                            bg=T.SURFACE, width=5, on_change=self._ratio_changed)
        self.ratio._menu.configure(width=5)
        self.ratio.pack(side="left", padx=(2, 0))
        self.skill_names = {entry["name"]: entry["id"] for entry in skills_mod.catalog()}
        # 기본값을 "none" 이 아니라 첫 스킬로 둔다. M1 은 스킬이 있어야 한다.
        skill_default = next(iter(self.skill_names), "none")
        self.skill = Select(srow, "", ["none"] + list(self.skill_names), skill_default,
                            bg=T.SURFACE, width=14)
        self.skill._menu.configure(width=14)
        self.skill.pack(side="right")
        self._paint_modes()

        # -------------------------------------------------------- generate
        self.gen_btn = RoundButton(b, "Generate video", self.start_generation,
                                   bg=T.ACCENT, hover=T.ACCENT_HOVER, height=44,
                                   width=300, radius=8, font=(T.FONT, 11, "bold"))
        self.gen_btn.pack(fill="x", pady=(10, 0))

        self.bar = Progress(b, height=4, width=300)
        self.bar.pack(fill="x", pady=(8, 0))

        # ---------------------------------------------------- result row
        res = tk.Frame(b, bg=T.SURFACE, height=48)
        res.pack(fill="x", pady=(8, 0))
        self.result_label = tk.Label(res, text="Ready", bg=T.SURFACE, fg=T.MUTED,
                                     font=T.SMALL)
        self.result_label.pack(side="left")
        self.save_btn = RoundButton(res, "Save", self._save_as, bg=T.ACCENT_DIM,
                                    fg=T.TEXT, hover=T.ACCENT, height=28, width=64,
                                    radius=8, font=T.TINY)
        self.save_btn.pack(side="right")
        self.play_btn = RoundButton(res, "Play", self.play_video, bg=T.SURFACE,
                                    fg=T.TEXT_DIM, hover=T.SURFACE_2, height=28, width=56,
                                    radius=8, font=T.TINY)
        self.play_btn.pack(side="right", padx=6)
        self.result_box = tk.Frame(res, bg=T.SURFACE, width=96, height=54)
        self.result_box.pack(side="right", padx=6)
        self.result_box.pack_propagate(False)
        self.thumb_label = tk.Label(self.result_box, bg=T.SURFACE_2, bd=0)
        self.thumb_label.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ modes
    def _paint_modes(self):
        for key, btn in self._mode_buttons.items():
            if key == self.mode_key:
                btn.configure(bg=T.ACCENT, fg="#ffffff")
            else:
                btn.configure(bg=T.BG_DEEP, fg=T.TEXT_DIM)
        self._paint_durations()

    def _paint_durations(self):
        """Legit Mode with stills on: the original locks the menu to 15s and below."""
        capped = self.mode_key == "legit" and bool(self.references)
        allowed = [d for d in DURATIONS
                   if not capped or int(d.rstrip("s")) <= LEGIT_IMAGE_CAP]
        self.duration.set_options(allowed)
        if self.duration.get() not in allowed:
            self.duration.set(allowed[-1])

    def switch_mode(self, key):
        self.mode_key = key
        self._paint_modes()

    def _account_menu(self, event=None):
        menu = self._account_menu_obj
        menu.delete(0, "end")
        for name in self.store.config.get("profiles") or []:
            menu.add_command(label=name, command=lambda n=name: self.set_account(n))
        menu.add_separator()
        menu.add_command(label="Manage accounts…", command=self.app.open_accounts)
        try:
            menu.tk_popup(event.x_root if event else self.winfo_pointerx(),
                          event.y_root if event else self.winfo_pointery())
        finally:
            menu.grab_release()

    def set_account(self, name):
        self.profile = name
        self.account_badge.configure(text=f"{name} · CR {self.store.credits(name)}")
        self.refresh()

    def _ratio_changed(self, value):
        self.store.config["aspect"] = value
        self.store.save_config()

    def current_skill(self):
        return self.skill_names.get(self.skill.get()) or ""

    # -------------------------------------------------------------- stills
    def choose_images_dialog(self):
        from tkinter import filedialog
        paths = filedialog.askopenfilenames(
            title="Reference images",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp")])
        for path in paths:
            if len(self.references) >= 10:
                self.app.show_transient_popup("Maximum 10 images limit")
                break
            if path not in self.references:
                self.references.append(path)
        self._fill_thumbs()
        self._paint_durations()

    def clear_images(self):
        self.references = []
        self._fill_thumbs()
        self._paint_durations()

    def _fill_thumbs(self):
        for w in self.thumb_host.winfo_children():
            w.destroy()
        self.img_counter.configure(text=f"{len(self.references)}/10 reference images")
        if not self.references:
            tk.Label(self.thumb_host, text="no stills attached", bg=T.BG_DEEP,
                     fg=T.MUTED_DARK, font=T.TINY).pack(side="left", padx=8)
            return
        for path in self.references:
            slot = tk.Frame(self.thumb_host, bg=T.SURFACE_2)
            slot.pack(side="left", padx=3, pady=3)
            img = thumb(path, 46, 26)
            lbl = tk.Label(slot, image=img, bg=T.SURFACE_2, bd=0)
            lbl.image = img
            lbl.pack(side="left", padx=2)
            close = tk.Label(slot, text="✕", bg=T.SURFACE_2, fg=T.MUTED, font=T.TINY,
                             padx=3, cursor="hand2")
            close.pack(side="left")
            close.bind("<Button-1>", lambda _e, p=path: self._remove_image(p))

    def _remove_image(self, path):
        if path in self.references:
            self.references.remove(path)
        self._fill_thumbs()
        self._paint_durations()

    # ------------------------------------------------------------- generate
    def start_generation(self):
        prompt = self.prompt.get()
        if not prompt:
            self.app.show_transient_popup("Write a brief first")
            return
        if int(getattr(self.app, "vp_method", 1) or 1) == 1 and not self.current_skill():
            self.app.show_transient_popup(
                "Method 1 renders through a Dola skill — pick one in the skill menu "
                "(or switch to M2)")
            return
        wait = self.store.cooldown_left(self.profile)
        if wait:
            self.app.show_transient_popup(f"{self.profile} is cooling down — {wait}s left")
            return
        acc_id = store_mod.account_id(self.store.config, self.profile)
        folder = browser_mod.profile_folder(self.store.config.get("data_dir"),
                                            acc_id or self.profile,
                                            legacy_key=self.profile)
        if not folder.exists() and not ck.account_cookies(self.store.config, self.profile):
            self.app.show_transient_popup(
                f"{self.profile} is not signed in — account badge → Manage accounts")
            return
        if not self.store.spend_credit(self.profile):
            self.app.show_transient_popup(f"{self.profile} has no renders left")
            return
        job = new_job(prompt, {
            "mode": self.mode_key,
            "reference": self.references[0] if self.references else "",
            "references": list(self.references),
            "duration": int(self.duration.get().rstrip("s")),
            "aspect": self.ratio.get(),
            "skill": self.current_skill(),
            "skill_row": self.store.config.get("skill_row_name", ""),
            "method": int(getattr(self.app, "vp_method", 1) or 1),
            "profile": self.profile,
            "account": self.profile,
            "account_id": acc_id or self.profile,
            "cookies": ck.account_cookies(self.store.config, self.profile),
            "panel": self.index,
        })
        job["credit_spent"] = 1
        self.app.engine.submit(job)
        self.last_ids.insert(0, job["id"])
        self.app.log(f"[{self.profile}|TAB{self.index}] Mode: "
                     f"{dict(MODES).get(self.mode_key)} queued")
        self.app.add_history_item(prompt[:40])
        self._result_sig = None
        self.refresh()

    # --------------------------------------------------------------- result
    def _job(self):
        for jid in self.last_ids:
            job = self.store.get(jid)
            if job:
                return job
        return None

    def refresh(self):
        self._refund_dead_jobs()
        wait = self.store.cooldown_left(self.profile)
        self.gen_btn.set_state("disabled" if wait else "normal")
        self.gen_btn.set_text(f"Cooling down · {wait}s" if wait else "Generate video")
        self.account_badge.configure(
            text=f"{self.profile} · CR {self.store.credits(self.profile)}")
        job = self._job()
        if job and job.get("status") in ("queued", "running"):
            p = job.get("progress", 0.0)
            self.bar.set(p)
            self.result_label.configure(
                text=f"{job.get('stage', 'Working')} · {int(p * 100)}% · {self._eta(job)}")
            self.stream_badge.configure(text="Processing", bg=T.YELLOW_DIM, fg=T.YELLOW)
        elif job and job.get("status") == "done":
            self.bar.set(1.0)
            self.result_label.configure(
                text=f"Done · {job.get('duration')}s · {job.get('aspect')}")
            self.stream_badge.configure(text="Standby", bg=T.GREEN_DIM, fg=T.GREEN)
        elif job and job.get("status") == "failed":
            self.bar.set(0)
            self.result_label.configure(text=(job.get("error") or "failed")[:60])
            self.stream_badge.configure(text="Failed", bg=T.RED_DIM, fg=T.RED)
        self._fill_result()

    def _refund_dead_jobs(self):
        changed = False
        for job in self.store.jobs:
            if job.get("profile") != self.profile or not job.get("credit_spent"):
                continue
            if job.get("status") in ("failed", "cancelled"):
                job["credit_spent"] = 0
                self.store.refund_credit(self.profile)
                changed = True
        if changed:
            self.store.save_jobs()

    def _eta(self, job):
        started = job.get("started_ms")
        p = job.get("progress", 0.0)
        if not started or p <= 0.04:
            return "estimating…"
        elapsed = (time.time() * 1000 - started) / 1000
        left = max(0, elapsed / max(0.02, p) - elapsed)
        return f"~{int(left)}s left"

    def _fill_result(self):
        job = self._job()
        sig = (job["id"], job.get("status"), job.get("poster")) if job else None
        if sig == self._result_sig:
            return
        self._result_sig = sig
        self.thumb_label.configure(image="", bg=T.SURFACE_2)
        if not job or job.get("status") != "done":
            return
        img = thumb(job.get("poster"), 96, 54)
        self.thumb_label.configure(image=img, bg=T.SURFACE_2)
        self.thumb_label.image = img
        self.thumb_label.bind("<Button-1>", lambda _e: self.play_video())

    def play_video(self):
        job = self._job()
        if not job:
            self.app.show_transient_popup("Nothing rendered here yet")
            return
        self.app.play(job)

    def _save_as(self):
        job = self._job()
        files = [f for f in (job or {}).get("files", []) if str(f).lower().endswith(".mp4")]
        if not files:
            self.app.show_transient_popup("There is no MP4 to save yet")
            return
        from tkinter import filedialog
        target = filedialog.asksaveasfilename(
            title="Save video", defaultextension=".mp4",
            initialfile=Path(files[0]).name, filetypes=[("MP4 video", "*.mp4")])
        if target:
            shutil.copyfile(files[0], target)
            self.app.show_transient_popup(f"Saved: {Path(target).name}")