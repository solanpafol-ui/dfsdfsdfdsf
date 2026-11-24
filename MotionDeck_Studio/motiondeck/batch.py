"""The batch wizard: pipeline, prompts, assets, launch."""
import tkinter as tk
from pathlib import Path

from . import providers
from . import theme as T
from .store import new_job
from .widgets import Card, RoundButton, SegTabs, Select

RATIOS = ["16:9", "9:16", "1:1"]
DURATIONS = ["5", "10", "15", "30", "60"]


class AutoWizard(tk.Toplevel):
    """Four steps: pipeline, prompts, assets, launch."""

    STEPS = ["1. Mode", "2. Prompts", "3. Assets", "4. Launch"]

    def __init__(self, app, panel):
        super().__init__(app)
        self.app = app
        self.panel = panel
        self.title("Auto batch")
        self.configure(bg=T.BG)
        self.geometry("660x520")
        self.transient(app)
        self.grab_set()
        self.prompts = []
        self.assets_dir = ""
        self.step = 0
        self.mode_value = "Standard"

        head = tk.Frame(self, bg=T.BG)
        head.pack(fill="x", padx=24, pady=(20, 6))
        tk.Label(head, text="⚡ Auto batch", bg=T.BG, fg=T.TEXT, font=(T.FONT, 15, "bold")
                 ).pack(side="left")
        self.step_label = tk.Label(head, text="", bg=T.BG, fg=T.MUTED, font=T.SMALL)
        self.step_label.pack(side="right")

        self.steps = tk.Frame(self, bg=T.BG)
        self.steps.pack(fill="x", padx=24)
        self._step_chips = []
        for name in self.STEPS:
            lbl = tk.Label(self.steps, text=name, bg=T.SURFACE_2, fg=T.MUTED,
                           font=T.TINY, padx=12, pady=6)
            lbl.pack(side="left", padx=(0, 6))
            self._step_chips.append(lbl)

        self.body = Card(self, bg=T.SURFACE, pad=20, height=300)
        self.body.pack(fill="both", expand=True, padx=24, pady=16)

        footer = tk.Frame(self, bg=T.BG)
        footer.pack(fill="x", padx=24, pady=(0, 20))
        self.back = RoundButton(footer, "⬅ Back", self._prev, bg=T.SURFACE, fg=T.MUTED,
                                hover=T.SURFACE_2, height=36, width=96, radius=8,
                                font=T.SMALL)
        self.back.pack(side="left")
        self.next = RoundButton(footer, "Next step ➔", self._next, bg=T.ACCENT,
                                hover=T.ACCENT_HOVER, height=36, width=140, radius=8)
        self.next.pack(side="right")
        self._render()

    # ------------------------------------------------------------------- steps
    def _chip_paint(self):
        for i, lbl in enumerate(self._step_chips):
            if i == self.step:
                lbl.configure(bg=T.ACCENT, fg="#ffffff")
            elif i < self.step:
                lbl.configure(bg=T.GREEN_DIM, fg=T.GREEN)
            else:
                lbl.configure(bg=T.SURFACE_2, fg=T.MUTED)
        self.step_label.configure(text=f"Step {self.step + 1} of {len(self.STEPS)}")
        self.next.set_text("🚀 Start batch" if self.step == len(self.STEPS) - 1
                           else "Next step ➔")

    def _clear(self):
        for w in self.body.body.winfo_children():
            w.destroy()

    def _render(self):
        self._clear()
        b = self.body.body
        self._chip_paint()
        if self.step == 0:
            tk.Label(b, text="Choose generation pipeline", bg=T.SURFACE, fg=T.TEXT,
                     font=T.H2).pack(anchor="w")
            tk.Label(b, text="Standard writes from your briefs. Reference also attaches the "
                             "stills in the assets folder.",
                     bg=T.SURFACE, fg=T.MUTED, font=T.SMALL).pack(anchor="w", pady=(4, 14))
            self.mode_pick = SegTabs(b, ["Standard", "Reference"], self.mode_value,
                                     bg=T.SURFACE, on_change=self._set_mode)
            self.mode_pick.pack(anchor="w")
        elif self.step == 1:
            tk.Label(b, text="Batch prompts", bg=T.SURFACE, fg=T.TEXT,
                     font=T.H2).pack(anchor="w")
            tk.Label(b, text="Load a .txt file. One prompt per block, separated by a blank line.",
                     bg=T.SURFACE, fg=T.MUTED, font=T.SMALL).pack(anchor="w", pady=(4, 12))
            row = tk.Frame(b, bg=T.SURFACE)
            row.pack(fill="x")
            RoundButton(row, "📂 Load .txt file", self._load_txt, bg=T.SURFACE_2,
                        fg=T.TEXT_DIM, hover=T.SURFACE_3, height=32, width=138,
                        radius=8, font=T.SMALL).pack(side="left")
            self.txt_label = tk.Label(row, text=self._prompt_text(), bg=T.SURFACE,
                                      fg=T.MUTED_DARK, font=T.TINY)
            self.txt_label.pack(side="left", padx=10)
            self.preview = tk.Text(b, height=7, bg=T.INPUT, fg=T.TEXT_DIM, relief="flat",
                                   bd=0, font=T.TINY, wrap="word", padx=10, pady=8)
            self.preview.pack(fill="both", expand=True, pady=(12, 0))
            if self.prompts:
                self.preview.insert("1.0", "\n\n".join(self.prompts)[:1200])
            self.preview.configure(state="disabled")
        elif self.step == 2:
            tk.Label(b, text="Reference assets", bg=T.SURFACE, fg=T.TEXT,
                     font=T.H2).pack(anchor="w")
            tk.Label(b, text="Optional. Pick a folder; each sub-folder is one set of stills. "
                             "Only used by the Reference pipeline.",
                     bg=T.SURFACE, fg=T.MUTED, font=T.SMALL, justify="left").pack(anchor="w",
                                                                                  pady=(4, 12))
            row = tk.Frame(b, bg=T.SURFACE)
            row.pack(fill="x")
            RoundButton(row, "Browse folder", self._pick_assets, bg=T.SURFACE_2,
                        fg=T.TEXT_DIM, hover=T.SURFACE_3, height=32, width=124,
                        radius=8, font=T.SMALL).pack(side="left")
            tk.Label(row, text=self.assets_dir or "No folder selected yet", bg=T.SURFACE,
                     fg=T.MUTED_DARK, font=T.TINY).pack(side="left", padx=10)
        else:
            tk.Label(b, text="Aspect ratio and clip length", bg=T.SURFACE, fg=T.TEXT,
                     font=T.H2).pack(anchor="w")
            grid = tk.Frame(b, bg=T.SURFACE)
            grid.pack(fill="x", pady=14)
            tk.Label(grid, text="Aspect ratio", bg=T.SURFACE, fg=T.MUTED,
                     font=T.SMALL).pack(side="left")
            default_ratio = getattr(getattr(self.panel, "ratio", None), "get", lambda: "16:9")()
            self.ratio_pick = SegTabs(grid, RATIOS, default_ratio, bg=T.SURFACE)
            self.ratio_pick.pack(side="left", padx=(10, 20))
            tk.Label(grid, text="Duration", bg=T.SURFACE, fg=T.MUTED,
                     font=T.SMALL).pack(side="left")
            default_dur = getattr(getattr(self.panel, "duration", None), "get", lambda: "5")()
            self.duration_pick = Select(grid, "", DURATIONS, default_dur,
                                        bg=T.SURFACE, width=4)
            self.duration_pick._menu.configure(width=4)
            self.duration_pick.pack(side="left", padx=8)
            self.summary = tk.Label(b, text=self._summary(), bg=T.SURFACE, fg=T.TEXT_DIM,
                                    font=T.SMALL, justify="left", anchor="w")
            self.summary.pack(anchor="w", pady=12)

    def _set_mode(self, value):
        self.mode_value = value

    def _prompt_text(self):
        if not self.prompts:
            return "no file loaded"
        return f"{len(self.prompts)} prompt sets detected"

    def _load_txt(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(title="Prompts", filetypes=[("Text", "*.txt")])
        if not path:
            return
        try:
            raw = Path(path).read_text("utf-8", errors="replace")
        except Exception as exc:
            self.app.toast(f"TXT load error: {exc}")
            return
        blocks = [b.strip() for b in raw.replace("\r\n", "\n").split("\n\n") if b.strip()]
        if len(blocks) == 1:
            blocks = [line.strip() for line in raw.splitlines() if line.strip()]
        self.prompts = blocks
        self._render()

    def _pick_assets(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(title="Reference assets folder")
        if path:
            self.assets_dir = path
            self._render()

    def _summary(self):
        return (f"{len(self.prompts)} job(s) · mode {self.mode_value} · "
                f"ratio {self.ratio_pick.get() if hasattr(self, 'ratio_pick') else '16:9'} · "
                f"{self.duration_pick.get() if hasattr(self, 'duration_pick') else '5'}s\n"
                f"assets: {self.assets_dir or 'none'}")

    def _prev(self):
        if self.step == 0:
            self.destroy()
            return
        self.step -= 1
        self._render()

    def _next(self):
        if self.step < len(self.STEPS) - 1:
            self.step += 1
            self._render()
            return
        if not self.prompts:
            self.app.toast("Load a prompt file first")
            return
        self._start()

    def _start(self):
        pid = self.app.provider_id()
        ratio = self.ratio_pick.get()
        duration = self.duration_pick.get()
        model = providers.options_for(self.store_config())[0]
        made = 0
        for prompt in self.prompts:
            job = new_job(prompt, {
                "provider": pid, "model": model, "mode": self.mode_value,
                "reference": "", "references": [], "duration": duration,
                "resolution": "720p", "aspect": ratio,
                "skill": self.panel.current_skill(),
            })
            self.app.engine.submit(job)
            made += 1
        self.destroy()
        self.app.toast(f"{made} batch job(s) queued")
        self.app.show("queue")

    def store_config(self):
        return self.app.store.config
