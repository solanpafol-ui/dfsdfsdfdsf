"""계정 등록·로그·라이브뷰 창."""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from . import cookies as ck, store
except ImportError:
    import cookies as ck
    import store


class AccountDialog(tk.Toplevel):
    def __init__(self, master, cfg, name=None, on_save=None):
        super().__init__(master)
        self.cfg = cfg
        self.on_save = on_save
        self.title("계정")
        self.geometry("560x420")
        self.transient(master)

        ttk.Label(self, text="이름").pack(anchor="w", padx=12, pady=(12, 2))
        self.name = ttk.Entry(self)
        self.name.pack(fill="x", padx=12)
        if name:
            self.name.insert(0, name)
            self.name.configure(state="readonly")

        ttk.Label(self, text="쿠키 붙여넣기 (Netscape / JSON / key=value)").pack(
            anchor="w", padx=12, pady=(10, 2))
        self.box = tk.Text(self, height=12, wrap="none")
        self.box.pack(fill="both", expand=True, padx=12)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=12, pady=8)
        ttk.Button(bar, text="파일에서", command=self._from_file).pack(side="left")
        ttk.Button(bar, text="검사", command=self._check).pack(side="left", padx=6)
        self.badge = ttk.Label(bar, text="")
        self.badge.pack(side="left")

        foot = ttk.Frame(self)
        foot.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(foot, text="저장", command=self._save).pack(side="right")
        ttk.Button(foot, text="취소", command=self.destroy).pack(side="right", padx=6)

        if name:
            rows = store.get_cookies(cfg, name)
            if rows:
                self.box.insert("1.0", "\n".join(f"{c['name']}={c['value']}" for c in rows))
                self._set_badge(ck.check(rows))

    def _from_file(self):
        p = filedialog.askopenfilename(
            filetypes=[("쿠키", "*.txt"), ("모두", "*.*")])
        if not p:
            return
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                self.box.delete("1.0", "end")
                self.box.insert("1.0", f.read())
        except OSError as e:
            messagebox.showerror("파일", str(e))

    def _parse(self):
        return ck.parse(self.box.get("1.0", "end"))

    def _set_badge(self, state):
        text = {"ok": "사용 가능", "expired": "만료됨", "none": "없음"}[state]
        self.badge.configure(text=text)

    def _check(self):
        try:
            jar = self._parse()
        except ck.CookieError as e:
            self._set_badge("none")
            messagebox.showwarning("검사", str(e))
            return
        self._set_badge(ck.check(jar))
        messagebox.showinfo("검사", f"쿠키 {len(jar)}개, dola.com용으로 정리됨.")

    def _save(self):
        try:
            jar = self._parse()
        except ck.CookieError as e:
            messagebox.showerror("저장", str(e))
            return
        name = self.name.get().strip()
        try:
            store.add_account(self.cfg, name, jar)
        except ValueError as e:
            messagebox.showerror("저장", str(e))
            return
        store.save(self.cfg)
        if self.on_save:
            self.on_save(name)
        self.destroy()


class LogDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("로그")
        self.geometry("720x420")
        self.text = tk.Text(self, state="disabled", wrap="word")
        self.text.pack(fill="both", expand=True)

    def append(self, line):
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n")
        self.text.see("end")
        self.text.configure(state="disabled")


class LiveViewDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("라이브")
        self.geometry("420x260")
        self.line = ttk.Label(self, text="대기 중", anchor="w", justify="left")
        self.line.pack(fill="both", expand=True, padx=12, pady=12)

    def update_event(self, e):
        self.line.configure(text=str(e))


def open_account_dialog(master, cfg, name=None, on_save=None):
    return AccountDialog(master, cfg, name=name, on_save=on_save)


def open_log_dialog(master):
    return LogDialog(master)


def open_live_dialog(master):
    return LiveViewDialog(master)