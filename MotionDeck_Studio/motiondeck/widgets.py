"""Small Tk widgets: rounded cards, pill buttons, dark fields, scroll areas."""
import tkinter as tk

from . import theme as T


def _round_points(x1, y1, x2, y2, r):
    r = max(1, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


def round_rect(canvas, x1, y1, x2, y2, r, **kw):
    """A smooth polygon that reads as a rounded rectangle in Tk."""
    r = max(1, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return canvas.create_polygon(
        _round_points(x1, y1, x2, y2, r), smooth=True, splinesteps=24, **kw
    )


class Card(tk.Canvas):
    """Rounded panel. Put content in `card.body`."""

    def __init__(self, master, bg=T.SURFACE, outer=T.BG, radius=14, pad=18,
                 border=None, height=None):
        super().__init__(master, bg=outer, highlightthickness=0, bd=0,
                         height=height or 60)
        self._bg = bg
        self._border = border
        self._radius = radius
        self._pad = pad
        self.body = tk.Frame(self, bg=bg)
        self._win = self.create_window(pad, pad, anchor="nw", window=self.body)
        self._shape = None
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event):
        self.itemconfigure(self._win, width=max(1, event.width - 2 * self._pad))
        self._redraw(event.width, event.height)

    def _redraw(self, w, h):
        if self._shape:
            self.delete(self._shape)
        kw = {}
        if self._border:
            kw = {"fill": self._bg, "outline": self._border, "width": 1}
        else:
            kw = {"fill": self._bg, "outline": ""}
        self._shape = round_rect(self, 1, 1, w - 1, h - 1, self._radius, **kw)
        self.tag_lower(self._shape)

    def autofit(self):
        """Size the card to its content height."""
        self.update_idletasks()
        h = self.body.winfo_reqheight() + 2 * self._pad
        self.configure(height=h)
        self.itemconfigure(self._win, height=max(1, h - 2 * self._pad))
        self._redraw(self.winfo_width(), h)


class RoundButton(tk.Canvas):
    """Pill button drawn on a canvas so it can be truly rounded."""

    def __init__(self, master, text, command=None, bg=T.ACCENT, fg="#ffffff",
                 hover=None, radius=10, height=40, width=160, font=None,
                 state="normal", outline=None):
        super().__init__(master, height=height, width=width, bg=master["bg"],
                         highlightthickness=0, bd=0, cursor="hand2")
        self._text = text
        self._command = command
        self._bg = bg
        self._fg = fg
        self._hover = hover or bg
        self._radius = radius
        self._font = font or T.BODY_BOLD
        self._state = state
        self._outline = outline
        self._hovering = False
        self.bind("<Configure>", lambda e: self._render())
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._click)

    def _fill(self):
        if self._state == "disabled":
            return T.SURFACE_3
        return self._hover if self._hovering else self._bg

    def _fg_color(self):
        if self._state == "disabled":
            return T.MUTED_DARK
        return self._fg

    def _render(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            return
        round_rect(self, 1, 1, w - 1, h - 1, self._radius,
                   fill=self._fill(), outline=self._outline or "")
        self.create_text(w / 2, h / 2 + 1, text=self._text, fill=self._fg_color(),
                         font=self._font)

    def _enter(self, _e):
        self._hovering = True
        self._render()

    def _leave(self, _e):
        self._hovering = False
        self._render()

    def _click(self, _e):
        if self._state != "disabled" and self._command:
            self._command()

    def set_state(self, state):
        self._state = state
        self.configure(cursor="hand2" if state != "disabled" else "arrow")
        self._render()

    def set_text(self, text):
        self._text = text
        self._render()

    def set_colors(self, bg, hover=None, fg=None):
        self._bg = bg
        self._hover = hover or bg
        if fg:
            self._fg = fg
        self._render()


class Badge(tk.Canvas):
    def __init__(self, master, text, fg=T.MUTED, bg=T.SURFACE_3, font=None,
                 radius=7, padx=9, height=20):
        super().__init__(master, height=height, bg=master["bg"],
                         highlightthickness=0, bd=0)
        self._text = text
        self._fg = fg
        self._bgc = bg
        self._radius = radius
        self._padx = padx
        self._font = font or T.TINY
        self.bind("<Configure>", lambda e: self._render())

    def _render(self):
        self.delete("all")
        f = self._font
        tmp = self.create_text(0, 0, text=self._text, font=f, anchor="nw")
        w = self.bbox(tmp)[2] + 2 * self._padx
        self.delete(tmp)
        h = int(self["height"])
        round_rect(self, 0, 0, w, h, self._radius, fill=self._bgc, outline="")
        self.create_text(w / 2, h / 2 + 1, text=self._text, fill=self._fg, font=f)
        self.configure(width=w)

    def set(self, text=None, fg=None, bg=None):
        if text is not None:
            self._text = text
        if fg:
            self._fg = fg
        if bg:
            self._bgc = bg
        self._render()


class Scroll(tk.Frame):
    """Vertically scrolling container. Put content in `.inner`."""

    def __init__(self, master, bg=T.BG):
        super().__init__(master, bg=bg)
        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self._bar = tk.Scrollbar(self, orient="vertical", command=self._canvas.yview,
                                 width=8, troughcolor=bg, bg=T.SURFACE_3,
                                 activebackground=T.MUTED_DARK, relief="flat",
                                 bd=0, highlightthickness=0)
        self.inner = tk.Frame(self._canvas, bg=bg)
        self._win = self._canvas.create_window(0, 0, anchor="nw", window=self.inner)
        self._canvas.configure(yscrollcommand=self._bar.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._bar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._sync)
        self._canvas.bind("<Configure>", self._sync)
        for w in (self._canvas, self.inner):
            w.bind("<MouseWheel>", self._wheel)

    def _sync(self, _e=None):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        self._canvas.itemconfigure(self._win, width=self._canvas.winfo_width())

    def _wheel(self, event):
        self._canvas.yview_scroll(int(-event.delta / 120), "units")

    def to_top(self):
        self._canvas.yview_moveto(0)


class Field(tk.Frame):
    def __init__(self, master, label, value="", placeholder="", show=None,
                 bg=T.SURFACE, width=None):
        super().__init__(master, bg=bg)
        self.bg = bg
        tk.Label(self, text=label, bg=bg, fg=T.MUTED, font=T.SMALL,
                 anchor="w").pack(fill="x", pady=(0, 5))
        shell = tk.Frame(self, bg=T.INPUT, highlightthickness=1,
                         highlightbackground=T.BORDER, highlightcolor=T.ACCENT)
        shell.pack(fill="x")
        self.var = tk.StringVar(value=value)
        self.entry = tk.Entry(shell, textvariable=self.var, bg=T.INPUT, fg=T.TEXT,
                              insertbackground=T.TEXT, relief="flat", bd=0,
                              disabledbackground=T.INPUT, disabledforeground=T.MUTED_DARK,
                              font=T.BODY, show=show or "")
        self.entry.pack(fill="x", padx=10, pady=7)
        self._placeholder = placeholder
        if placeholder and not value:
            self._show_placeholder()
        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", self._focus_out)

    def _show_placeholder(self):
        self.entry.insert(0, self._placeholder)
        self.entry.configure(fg=T.MUTED_DARK)
        self._ph_on = True

    def _focus_in(self, _e):
        if getattr(self, "_ph_on", False):
            self.entry.delete(0, "end")
            self.entry.configure(fg=T.TEXT)
            self._ph_on = False

    def _focus_out(self, _e):
        if not self.entry.get() and self._placeholder:
            self._show_placeholder()

    def get(self):
        if getattr(self, "_ph_on", False):
            return ""
        return self.entry.get().strip()

    def set(self, value):
        self._ph_on = False
        self.entry.configure(fg=T.TEXT)
        self.var.set(value)


class TextBox(tk.Frame):
    def __init__(self, master, height=7, bg=T.SURFACE, placeholder=""):
        super().__init__(master, bg=T.INPUT, highlightthickness=1,
                         highlightbackground=T.BORDER, highlightcolor=T.ACCENT)
        self.text = tk.Text(self, height=height, bg=T.INPUT, fg=T.TEXT,
                            insertbackground=T.TEXT, relief="flat", bd=0,
                            wrap="word", font=T.BODY, padx=12, pady=10,
                            selectbackground=T.ACCENT_DIM, undo=True)
        self.text.pack(fill="both", expand=True)
        self._placeholder = placeholder
        self._ph_on = False
        if placeholder:
            self._show_ph()
            self.text.bind("<FocusIn>", self._focus_in)
            self.text.bind("<FocusOut>", self._focus_out)

    def _show_ph(self):
        self.text.insert("1.0", self._placeholder)
        self.text.configure(fg=T.MUTED_DARK)
        self._ph_on = True

    def _focus_in(self, _e):
        if self._ph_on:
            self.text.delete("1.0", "end")
            self.text.configure(fg=T.TEXT)
            self._ph_on = False

    def _focus_out(self, _e):
        if not self.text.get("1.0", "end").strip() and self._placeholder:
            self._show_ph()

    def get(self):
        if self._ph_on:
            return ""
        return self.text.get("1.0", "end").strip()

    def set(self, value):
        self._ph_on = False
        self.text.configure(fg=T.TEXT)
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)


class Select(tk.Frame):
    """Dark dropdown built on tk.OptionMenu."""

    def __init__(self, master, label, options, value=None, bg=T.SURFACE,
                 on_change=None, width=16):
        super().__init__(master, bg=bg)
        self.bg = bg
        if label:
            tk.Label(self, text=label, bg=bg, fg=T.MUTED, font=T.SMALL,
                     anchor="w").pack(fill="x", pady=(0, 5))
        self.var = tk.StringVar(value=value or options[0])
        self._choices = list(options)
        self._on_change = on_change
        self._menu = tk.OptionMenu(self, self.var, *self._choices,
                                   command=self._changed)
        self._menu.configure(bg=T.INPUT, fg=T.TEXT, activebackground=T.SURFACE_3,
                             activeforeground=T.TEXT, relief="flat", bd=0,
                             highlightthickness=1, highlightbackground=T.BORDER,
                             font=T.BODY, anchor="w", width=width, cursor="hand2")
        self._menu["menu"].configure(bg=T.SURFACE_2, fg=T.TEXT, bd=0,
                                     activebackground=T.ACCENT,
                                     activeforeground="#ffffff", font=T.BODY)
        self._menu.pack(fill="x")

    def _changed(self, *_):
        if self._on_change:
            self._on_change(self.var.get())

    def get(self):
        return self.var.get()

    def set(self, value):
        self.var.set(value)

    def set_options(self, options, value=None):
        self._choices = list(options)
        menu = self._menu["menu"]
        menu.delete(0, "end")
        for opt in self._choices:
            menu.add_command(label=opt, command=lambda v=opt: (self.var.set(v),
                                                               self._changed()))
        if value:
            self.var.set(value)


class SegTabs(tk.Frame):
    """Two-or-more segment control (Monthly / Annual)."""

    def __init__(self, master, options, value=None, bg=T.SURFACE, on_change=None):
        super().__init__(master, bg=bg)
        self._buttons = {}
        self._value = value or options[0]
        self._on_change = on_change
        holder = tk.Frame(self, bg=T.SURFACE_2, highlightthickness=1,
                          highlightbackground=T.BORDER)
        holder.pack()
        for opt in options:
            b = tk.Label(holder, text=opt, padx=22, pady=7, font=T.SMALL_BOLD,
                         cursor="hand2")
            b.pack(side="left", padx=2, pady=2)
            b.bind("<Button-1>", lambda _e, o=opt: self.set(o))
            self._buttons[opt] = b
        self._paint()

    def _paint(self):
        for opt, b in self._buttons.items():
            if opt == self._value:
                b.configure(bg=T.ACCENT, fg="#ffffff")
            else:
                b.configure(bg=T.SURFACE_2, fg=T.MUTED)

    def set(self, value):
        self._value = value
        self._paint()
        if self._on_change:
            self._on_change(value)

    def get(self):
        return self._value


class Progress(tk.Canvas):
    def __init__(self, master, height=6, bg=T.SURFACE_2, fg=T.ACCENT, width=200):
        super().__init__(master, height=height, width=width, bg=master["bg"],
                         highlightthickness=0, bd=0)
        self._bgc = bg
        self._fgc = fg
        self._value = 0.0
        self.bind("<Configure>", lambda e: self._render())

    def _render(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            return
        round_rect(self, 0, 0, w, h, h / 2, fill=self._bgc, outline="")
        if self._value > 0:
            round_rect(self, 0, 0, max(h, w * min(1.0, self._value)), h, h / 2,
                       fill=self._fgc, outline="")

    def set(self, value):
        self._value = max(0.0, min(1.0, value))
        self._render()


_THUMBS = {}


def thumb(path, w, h):
    """A rounded-off thumbnail of a poster, letterboxed on the card colour."""
    key = (str(path), w, h)
    if key in _THUMBS:
        return _THUMBS[key]
    from PIL import Image, ImageTk
    canvas = Image.new("RGB", (w, h), (23, 26, 35))
    try:
        from pathlib import Path
        if path and Path(path).exists():
            im = Image.open(str(path)).convert("RGB")
            im.thumbnail((w, h))
            canvas.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    except Exception:
        pass
    photo = ImageTk.PhotoImage(canvas)
    _THUMBS[key] = photo
    return photo
