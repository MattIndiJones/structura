"""Small vector widgets for the desktop launcher; no additional dependency."""
import tkinter as tk

BACKGROUND = "#f7f6f2"
INK = "#193247"
MUTED = "#6c7b86"
BORDER = "#e0e4e3"
NAVY = "#173247"
COPPER = "#bf9563"


def rounded(canvas, x, y, box_width, box_height, radius, **options):
    radius = min(radius, box_width / 2, box_height / 2)
    right, bottom = x + box_width, y + box_height
    points = [x + radius, y, right - radius, y, right, y, right, y + radius,
              right, bottom - radius, right, bottom, right - radius, bottom,
              x + radius, bottom, x, bottom, x, bottom - radius, x, y + radius, x, y]
    return canvas.create_polygon(points, smooth=True, splinesteps=30, **options)


class RoundedPanel(tk.Canvas):
    def __init__(self, parent, fill="#ffffff", border=BORDER, padding=20, **options):
        super().__init__(parent, background=BACKGROUND, highlightthickness=0, borderwidth=0, **options)
        self.fill, self.border, self.padding = fill, border, padding
        self.body = tk.Frame(self, background=fill)
        self.window = self.create_window(padding, padding, anchor="nw", window=self.body)
        self.bind("<Configure>", self.redraw)
        self.body.bind("<Configure>", self.fit_height)

    def fit_height(self, event=None):
        height = self.body.winfo_reqheight() + self.padding * 2 + 6
        if int(self.cget("height")) != height:
            self.configure(height=height)

    def redraw(self, event):
        self.delete("surface")
        rounded(self, 2, 5, max(1, event.width - 4), max(1, event.height - 5), 18,
                fill="#eceeea", outline="", tags="surface")
        rounded(self, 1, 1, max(1, event.width - 3), max(1, event.height - 6), 18,
                fill=self.fill, outline=self.border, width=1, tags="surface")
        self.tag_lower("surface")
        self.itemconfigure(self.window, width=max(1, event.width - self.padding * 2),
                           height=max(1, event.height - self.padding * 2 - 6))


class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command, background="#ffffff", fill="#edf2f8",
                 foreground=INK, hover="#e1eaf5", width=118, height=38, radius=9,
                 border="", font=("Segoe UI", 10, "bold"), **options):
        super().__init__(parent, width=width, height=height, background=background,
                         highlightthickness=0, borderwidth=0, takefocus=1, cursor="hand2", **options)
        self.caption, self.command = text, command
        self.fill, self.foreground, self.hover, self.radius = fill, foreground, hover, radius
        self.border, self.caption_font = border, font
        self.enabled, self.over, self.focused = True, False, False
        self.bind("<Configure>", self.draw)
        self.bind("<Enter>", lambda event: self.highlight(True))
        self.bind("<Leave>", lambda event: self.highlight(False))
        self.bind("<FocusIn>", lambda event: self.focus(True))
        self.bind("<FocusOut>", lambda event: self.focus(False))
        self.bind("<ButtonRelease-1>", self.invoke)
        self.bind("<Return>", self.invoke)
        self.bind("<space>", self.invoke)

    def draw(self, event=None):
        self.delete("all")
        width, height = max(1, self.winfo_width()), max(1, self.winfo_height())
        fill = self.hover if self.over and self.enabled else self.fill
        foreground = self.foreground if self.enabled else "#9aa7b8"
        rounded(self, 1, 1, width - 2, height - 2, self.radius,
                fill=fill if self.enabled else "#ecefeb",
                outline=COPPER if self.focused else self.border, width=2 if self.focused else 1)
        self.create_text(width / 2, height / 2, text=self.caption, fill=foreground,
                         font=self.caption_font)

    def configure(self, cnf=None, **options):
        if isinstance(cnf, str):
            return super().configure(cnf)
        if cnf:
            options = {**cnf, **options}
        if "text" in options:
            self.caption = options.pop("text")
        if "state" in options:
            self.enabled = options["state"] != "disabled"
            options["cursor"] = "hand2" if self.enabled else ""
        result = super().configure(**options)
        if hasattr(self, "enabled"):
            self.draw()
        return result

    config = configure

    def highlight(self, value):
        self.over = value
        self.draw()

    def focus(self, value):
        self.focused = value
        self.draw()

    def invoke(self, event=None):
        if self.enabled:
            self.command()
        return "break"


def icon(parent, kind, background="#ffffff"):
    colors = {"admin": (NAVY, "#ffffff"), "simulation": ("#f0edf7", "#7b6a9d"),
              "all": ("#edf3ef", "#4e806f"), "platform": ("#eaf0f5", "#567b99"),
              "organization": ("#f6efe5", "#a7804b")}
    fill, stroke = colors[kind]
    canvas = tk.Canvas(parent, width=40, height=40, background=background, highlightthickness=0)
    rounded(canvas, 1, 1, 38, 38, 11, fill=fill, outline="")
    if kind == "admin":
        for x, height in ((12, 12), (19, 19), (26, 25)):
            canvas.create_line(x, 30, x, 30 - height, fill=stroke, width=3, capstyle="round")
    elif kind == "simulation":
        for first, second in (((12, 13), (29, 17)), ((29, 17), (18, 29)), ((18, 29), (12, 13))):
            canvas.create_line(*first, *second, fill=stroke, width=1.6)
        for x, y in ((12, 13), (29, 17), (18, 29)):
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=fill, outline=stroke, width=2)
    elif kind == "all":
        for x in (11, 23):
            for y in (11, 23):
                rounded(canvas, x, y, 7, 7, 2, fill="", outline=stroke, width=1.6)
    elif kind == "platform":
        for y in (12, 20, 28):
            canvas.create_oval(10, y - 2, 14, y + 2, fill=stroke, outline="")
            canvas.create_line(19, y, 30, y, fill=stroke, width=2, capstyle="round")
    else:
        canvas.create_rectangle(12, 11, 28, 30, outline=stroke, width=1.6)
        for x in (17, 23):
            for y in (16, 22):
                canvas.create_rectangle(x - 1, y - 1, x + 1, y + 1, fill=stroke, outline="")
    return canvas


class BrandPanel(tk.Canvas):
    """Scalable vector identity for the desktop menu, without bitmap assets."""

    def __init__(self, parent):
        super().__init__(parent, width=238, background=NAVY,
                         highlightthickness=0, borderwidth=0)
        self.bind("<Configure>", self.draw)

    def draw(self, event=None):
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        for y in range(0, height, 4):
            fraction = y / max(1, height)
            rgb = tuple(round(a + (b - a) * fraction)
                        for a, b in zip((18, 40, 58), (29, 59, 77)))
            color = "#%02x%02x%02x" % rgb
            self.create_rectangle(0, y, width, y + 4, fill=color, outline="")

        for x, top in ((31, 48), (42, 39), (53, 29)):
            self.create_line(x, 61, x, top, fill=COPPER, width=5, capstyle="round")
        self.create_text(29, 89, text="STRUCTURA", anchor="nw",
                         fill="#ffffff", font=("Segoe UI", 19, "bold"))
        self.create_text(30, 124, text="PRODUITS STRUCTURÉS", anchor="nw",
                         fill="#9eafbc", font=("Segoe UI", 8))
        self.create_line(30, 164, width - 30, 164, fill="#365064")

        y = max(204, min(270, height * .30))
        for index, text in enumerate(("Structurer.", "Valoriser.", "Accompagner.")):
            self.create_text(29, y + index * 39, text=text, anchor="nw",
                             fill="#ffffff" if index < 2 else "#d2b28b",
                             font=("Segoe UI", 19))

        # Abstract contract layers, kept in the available space on short displays.
        top = y + 155
        bottom = height - 130
        if bottom - top > 100:
            for offset, color in ((0, "#314c60"), (20, "#3d586b"), (40, "#4b6576")):
                self.create_line(30, top + offset, width - 30, top + offset,
                                 width - 30, bottom - 40 + offset, fill=color, width=1)
            self.create_line(30, bottom - 12, 76, bottom - 12, 107, bottom - 42,
                             148, bottom - 42, width - 30, bottom - 72,
                             fill=COPPER, width=2, capstyle="round", joinstyle="round")
            self.create_oval(width - 34, bottom - 76, width - 26, bottom - 68,
                             fill=COPPER, outline="")

        self.create_line(30, height - 100, width - 30, height - 100, fill="#3b5668")
        self.create_oval(30, height - 69, 36, height - 63, fill="#8eb8a9", outline="")
        self.create_text(45, height - 74, text="VOTRE ESPACE LOCAL", anchor="nw",
                         fill="#b5c4cd", font=("Segoe UI", 8, "bold"))
        self.create_text(30, height - 48, text="De l’idée au suivi du produit.", anchor="nw",
                         fill="#96acbb", font=("Segoe UI", 9))
