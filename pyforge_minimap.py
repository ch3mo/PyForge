"""Minimap: scaled line preview synced with a tk Text widget."""
import tkinter as tk

# Keep in sync with PyForge.Theme (avoid circular import)
_MINIMAP_MUTED = "#2a2d30"
_MINIMAP_COMMENT = "#3d4d3d"
_MINIMAP_DEF = "#3a3a55"
_MINIMAP_IMPORT = "#3a4555"
_MINIMAP_DEFAULT = "#2f2f35"
_VIEWPORT_ACCENT = "#0078d4"


def _line_color(line):
    s = line.strip()
    if not s:
        return _MINIMAP_MUTED
    if s.startswith("#"):
        return _MINIMAP_COMMENT
    if s.startswith(("def ", "class ", "async def")):
        return _MINIMAP_DEF
    if s.startswith(("import ", "from ")):
        return _MINIMAP_IMPORT
    return _MINIMAP_DEFAULT


class EditorMinimap(tk.Canvas):
    def __init__(self, master, editor, width=80, bg="#161616", **kw):
        super().__init__(master, width=width, highlightthickness=0, bg=bg, **kw)
        self.editor = editor
        self._width = width
        self._cached_n_lines = 0
        self._cached_w = 0
        self._cached_h = 0
        self.bind("<Configure>", self._schedule)
        for seq in ("<<Modified>>", "<KeyRelease>", "<ButtonRelease-1>", "<<Paste>>", "<<Cut>>"):
            editor.bind(seq, self._schedule)
        self.bind("<Button-1>", self._on_click)
        self.bind("<B1-Motion>", self._on_drag)

    def _schedule(self, event=None):
        self.after_idle(self.redraw)

    def redraw(self):
        self.delete("all")
        try:
            h = max(1, int(self.winfo_height()))
            w = max(1, int(self.winfo_width()))
        except tk.TclError:
            return
        text = self.editor.get("1.0", "end-1c")
        lines = text.split("\n")
        n = max(1, len(lines))
        self._cached_n_lines = n
        self._cached_w = w
        self._cached_h = h
        for i, line in enumerate(lines):
            y0 = i * h / n
            y1 = max(y0 + 1, (i + 1) * h / n)
            color = _line_color(line)
            self.create_rectangle(0, y0, w, y1, fill=color, outline="", width=0, tags=("lines",))
        self._draw_viewport_band(w, h)

    def _draw_viewport_band(self, w, h):
        self.delete("vp")
        try:
            lo, hi = self.editor.yview()
        except tk.TclError:
            lo, hi = 0.0, 1.0
        vp0 = lo * h
        vp1 = hi * h
        self.create_rectangle(0, vp0, w, vp1, outline=_VIEWPORT_ACCENT, width=1, tags=("vp",))

    def sync_viewport(self):
        """Cheap scroll sync: move viewport band only. Full redraw runs on text change."""
        try:
            h = max(1, int(self.winfo_height()))
            w = max(1, int(self.winfo_width()))
        except tk.TclError:
            return
        try:
            n = max(1, int(self.editor.index("end-1c").split(".")[0]))
        except (tk.TclError, ValueError):
            n = 1
        if n != self._cached_n_lines or w != self._cached_w or h != self._cached_h or not self.find_withtag("lines"):
            self.redraw()
            return
        self._draw_viewport_band(w, h)

    def _y_from_event(self, event):
        try:
            h = max(1, int(self.winfo_height()))
        except tk.TclError:
            return 0.0
        y = max(0, min(h, event.y))
        return y / h

    def _on_click(self, event):
        frac = self._y_from_event(event)
        self.editor.yview_moveto(frac)
        self.sync_viewport()

    def _on_drag(self, event):
        self._on_click(event)
