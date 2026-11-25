"""Account manager: local names, credits, and the per-account sign-in window."""
import shutil
import threading
import tkinter as tk

from . import browser
from . import cookies as ck
from . import store as store_mod
from . import theme as T
from .widgets import Field, RoundButton


class AccountDialog(tk.Toplevel):
    def __init__(self, app, initial=None):
        super().__init__(app)
        self.app = app
        self.store = app.store
        self.title("Accounts")
        self.configure(bg=T.BG)
        self.geometry("560x520")
        self.resizable(False, False)

        tk.Label(self, text="ACCOUNTS", bg=T.BG, fg=T.MUTED,
                 font=T.TINY).pack(anchor="w", padx=22, pady=(18, 4))
        tk.Label(self, text="One local profile per dola login. Sign in once per "
                            "account — the Chrome profile keeps it.",
                 bg=T.BG, fg=T.MUTED_DARK, font=T.TINY).pack(anchor="w", padx=22)

        self.list = tk.Listbox(self, bg=T.SURFACE, fg=T.TEXT, bd=0, height=7,
                               highlightthickness=1, highlightbackground=T.BORDER,
                               selectbackground=T.ACCENT, selectforeground="#ffffff",
                               font=T.SMALL)
        self.list.pack(fill="x", padx=22, pady=(10, 12))
        self.list.bind("<<ListboxSelect>>", self._selected)

        self.name = Field(self, "Account name", "", bg=T.BG)
        self.name.pack(fill="x", padx=22, pady=(0, 10))
        self.credit = Field(self, "Renders allowed", "", bg=T.BG)
        self.credit.pack(fill="x", padx=22, pady=(0, 14))

        row = tk.Frame(self, bg=T.BG)
        row.pack(fill="x", padx=22)
        self.signin_btn = RoundButton(row, "Sign in", self._signin, bg=T.ACCENT,
                                      hover=T.ACCENT_HOVER, height=38, width=110,
                                      radius=8, font=T.SMALL_BOLD)
        self.signin_btn.pack(side="left")
        RoundButton(row, "Save", self._save, bg=T.SURFACE_2, fg=T.TEXT,
                    hover=T.SURFACE_3, height=38, width=80, radius=8,
                    font=T.SMALL_BOLD).pack(side="left", padx=8)
        RoundButton(row, "Add", self._add, bg=T.SURFACE_2, fg=T.TEXT,
                    hover=T.SURFACE_3, height=38, width=80, radius=8,
                    font=T.SMALL_BOLD).pack(side="left")
        RoundButton(row, "Delete", self._delete, bg=T.SURFACE_2, fg=T.RED,
                    hover=T.SURFACE_3, height=38, width=90, radius=8,
                    font=T.SMALL_BOLD).pack(side="left", padx=8)

        self.msg = tk.Label(self, text="", bg=T.BG, fg=T.MUTED_DARK, font=T.TINY,
                            wraplength=500, justify="left")
        self.msg.pack(anchor="w", padx=22, pady=(12, 0))
        RoundButton(self, "Close", self.destroy, bg=T.SURFACE, fg=T.MUTED,
                    hover=T.SURFACE_2, height=32, width=90, radius=8,
                    font=T.SMALL).pack(anchor="w", padx=22, pady=16)

        self._fill()
        if initial:
            self._pick(initial)

    def _profiles(self):
        return self.store.config.setdefault("profiles", ["Profile 1"])

    def _fill(self):
        self.list.delete(0, "end")
        for name in self._profiles():
            state = ck.check(ck.account_cookies(self.store.config, name))
            badge = {"ok": "cookie ok", "expired": "cookie expired",
                     "none": "no cookie"}.get(state, "no cookie")
            self.list.insert("end", f"{name}  ·  CR {self.store.credits(name)}  ·  {badge}")

    def _current(self):
        sel = self.list.curselection()
        if not sel:
            return None
        return self._profiles()[sel[0]]

    def _pick(self, name):
        profiles = self._profiles()
        if name not in profiles:
            return
        index = profiles.index(name)
        self.list.selection_clear(0, "end")
        self.list.selection_set(index)
        self.list.see(index)
        self._selected()

    def _selected(self, event=None):
        name = self._current()
        if not name:
            return
        self.name.set(name)
        self.credit.set(str(self.store.credits(name)))
        state = ck.check(ck.account_cookies(self.store.config, name))
        if state == "none":
            self.msg.configure(text=f"{name} has no saved cookie yet — press Sign in.",
                               fg=T.MUTED)
        elif state == "expired":
            self.msg.configure(text=f"{name}'s saved cookie is expired — press Sign in.",
                               fg=T.RED)
        else:
            self.msg.configure(text="", fg=T.MUTED_DARK)

    def _save(self):
        name = (self.name.get() or "").strip()
        if not name:
            self.msg.configure(text="Give the account a name.", fg=T.RED)
            return
        current = self._current()
        profiles = self._profiles()
        if current and current != name:
            if name in profiles:
                self.msg.configure(text="That name is already used.", fg=T.RED)
                return
            profiles[profiles.index(current)] = name
            for table in ("credits", "cooldown_until", "accounts"):
                bucket = self.store.config.setdefault(table, {})
                if current in bucket:
                    bucket[name] = bucket.pop(current)
        try:
            self.store.config["credits"][name] = max(0, int(self.credit.get() or 0))
        except ValueError:
            pass
        store_mod.account_entry(self.store.config, name, create=True)
        self.store.save_config()
        self._fill()
        self._pick(name)
        self.msg.configure(text=f"Saved {name}.", fg=T.GREEN)
        self.app.refresh_account_ui()

    def _add(self):
        profiles = self._profiles()
        name = f"Profile {len(profiles) + 1}"
        while name in profiles:
            name += "+"
        profiles.append(name)
        self.store.config["credits"][name] = \
            int(self.store.config.get("credits_start", 40) or 0)
        store_mod.account_entry(self.store.config, name, create=True)
        self.store.save_config()
        self._fill()
        self._pick(name)
        self.msg.configure(text=f"{name} added — now press Sign in.", fg=T.GREEN)
        self.app.refresh_account_ui()

    def _delete(self):
        name = self._current()
        if not name:
            return
        profiles = self._profiles()
        if len(profiles) <= 1:
            self.msg.configure(text="Keep at least one account.", fg=T.RED)
            return
        acc = (self.store.config.get("accounts") or {}).get(name) or {}
        profiles.remove(name)
        for table in ("credits", "cooldown_until", "accounts"):
            (self.store.config.get(table) or {}).pop(name, None)
        self.store.save_config()
        key = acc.get("id") or name
        folder = browser.profile_folder(self.store.config.get("data_dir"), key,
                                        legacy_key=name)
        shutil.rmtree(str(folder), ignore_errors=True)
        self._fill()
        self.name.set("")
        self.credit.set("")
        self.msg.configure(text=f"{name} removed (login folder deleted).", fg=T.MUTED)
        self.app.refresh_account_ui()

    def _signin(self):
        name = (self.name.get() or "").strip() or self._current()
        if not name:
            self.msg.configure(text="Pick an account first.", fg=T.RED)
            return
        store_mod.account_entry(self.store.config, name, create=True)
        self.store.save_config()
        key = store_mod.account_id(self.store.config, name) or name
        self.signin_btn.set_state("disabled")
        self.msg.configure(text="Chrome is opening… (F7 shows the progress lines)",
                           fg=T.MUTED)

        def say(line):
            try:
                self.app.log(line)
            except Exception:
                pass
            try:
                self.app.after(0, lambda l=line: self.msg.configure(text=l[:160], fg=T.MUTED))
            except Exception:
                pass

        def work():
            try:
                ok = browser.open_signin(key, self.store.config.get("data_dir", ""),
                                         log=say)
                self.app.after(0, lambda: self._signin_done(name, ok, ""))
            except Exception as exc:
                self.app.after(0, lambda e=f"{type(exc).__name__}: {exc}":
                               self._signin_done(name, False, e))

        threading.Thread(target=work, daemon=True).start()

    def _signin_done(self, name, ok, error):
        try:
            self.signin_btn.set_state("normal")
        except Exception:
            pass
        if ok:
            self.msg.configure(text=f"{name} is signed in on this machine.", fg=T.GREEN)
        elif error:
            self.msg.configure(text=f"Sign-in window failed: {error}", fg=T.RED)
        else:
            self.msg.configure(
                text=f"{name} did not finish signing in. Press F7 and read the last "
                     f"'signin:' line — it names the step that failed.", fg=T.RED)
        self._fill()
        self._pick(name)