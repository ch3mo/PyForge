import os
import json
import re
import shutil
import subprocess
import sys
import queue
import threading
import hashlib
import time
import shlex
import ctypes
from tkinter import messagebox, simpledialog, filedialog, ttk, font as tkfont
import tkinter as tk
import customtkinter as ctk
import idlelib.colorizer as ic
import idlelib.percolator as ip
from pyforge_minimap import EditorMinimap
from pyforge_pty import PtySession
from pyforge_debug import PdbPipeSession
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
# CustomTkinter's CTkToplevel applies the Windows dark title bar by withdraw() + after(5ms) deiconify().
# If the window is destroyed first (e.g. closing a dialog quickly), the deferred deiconify() raises
# TclError: bad window path name. We disable that path and use _apply_windows_dark_titlebar (DWM) instead.
if sys.platform.startswith("win"):
    ctk.CTkToplevel._deactivate_windows_window_header_manipulation = True
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_ROOT = os.path.join(_TOOLS_DIR, "pyforge_projects")
os.makedirs(TOOLS_ROOT, exist_ok=True)


def _is_portable_mode():
    return os.environ.get("PYFORGE_PORTABLE", "").lower() in ("1", "true", "yes") or os.path.isfile(
        os.path.join(_TOOLS_DIR, "portable.txt")
    )


def _portable_data_dir():
    if _is_portable_mode():
        d = os.path.join(_TOOLS_DIR, "pyforge_data")
        os.makedirs(d, exist_ok=True)
        return d
    return os.path.expanduser("~")


_DATA_BASE = _portable_data_dir()
STATE_FILE = os.path.join(_DATA_BASE, ".pyforge_state.json")
RECENT_FILE = os.path.join(_DATA_BASE, ".pyforge_recent.json")
SETTINGS_FILE = os.path.join(_DATA_BASE, ".pyforge_settings.json")


class Theme:
    """Cursor-like dark: charcoal surfaces, zinc borders, crisp blue accent."""
    APP = "#18181b"
    PANEL = "#1e1e1e"
    RAISED = "#252526"
    HOVER = "#2a2d30"
    HOVER_LIGHT = "#323232"
    BORDER = "#3f3f46"
    BORDER_SUBTLE = "#27272a"
    ACCENT = "#0078d4"
    ACCENT_HOVER = "#1a8cff"
    ACCENT_PRESS = "#006cbd"
    TEXT = "#e4e4e7"
    TEXT_SECONDARY = "#a1a1aa"
    TEXT_MUTED = "#71717a"
    TEXT_DIM = "#52525b"
    EDITOR = "#1e1e1e"
    GUTTER = "#252526"
    GUTTER_FG = "#6b7280"
    GUTTER_ACTIVE = "#d4d4d8"
    LINE_HL = "#2a2d30"
    SELECTION = "#264f78"
    MINIMAP = "#161616"
    SUCCESS = "#4ade80"
    DANGER = "#f87171"
    RADIUS = 6
    RADIUS_LG = 8
    RADIUS_PILL = 10
    TAB_ACTIVE = "#1e1e1e"
    TAB_INACTIVE = "#2d2d30"
    TAB_HOVER = "#323232"
    ENTRY_BG = "#252526"
    BTN_SECONDARY = "#3f3f46"
    BTN_SECONDARY_HOVER = "#52525b"
    # First open: 0 = next idle (instant feel). >0 = delay for accidental bar crossings.
    MENU_HOVER_DELAY_MS = 0
    MENU_LEAVE_DEBOUNCE_MS = 90
    MENU_POPUP_OVERLAP_PX = 3
    MENU_BRIDGE_BELOW_PX = 56


def _dialog_entry_kwargs(**extra):
    d = {
        "fg_color": Theme.ENTRY_BG,
        "border_color": Theme.BORDER,
        "text_color": Theme.TEXT,
        "placeholder_text_color": Theme.TEXT_MUTED,
        "corner_radius": Theme.RADIUS,
    }
    d.update(extra)
    return d


def _dialog_option_kwargs(**extra):
    d = {
        "fg_color": Theme.ENTRY_BG,
        "button_color": Theme.BTN_SECONDARY,
        "button_hover_color": Theme.BTN_SECONDARY_HOVER,
        "text_color": Theme.TEXT,
        "dropdown_fg_color": Theme.RAISED,
        "dropdown_hover_color": Theme.HOVER,
        "dropdown_text_color": Theme.TEXT,
        "corner_radius": Theme.RADIUS,
    }
    d.update(extra)
    return d


def _ctk_scrollbar_kwargs(**extra):
    d = {
        "fg_color": Theme.PANEL,
        "button_color": Theme.BTN_SECONDARY,
        "button_hover_color": Theme.BTN_SECONDARY_HOVER,
        "width": 12,
        "corner_radius": 6,
    }
    d.update(extra)
    return d


def _apply_windows_dark_titlebar(window):
    """Native title bar + menu strip follow dark mode on Windows 10/11."""
    if not sys.platform.startswith("win"):
        return
    try:
        wid = int(window.winfo_id())
        hwnd = ctypes.wintypes.HWND(wid)
        try:
            parent_hwnd = ctypes.windll.user32.GetParent(hwnd)
            if parent_hwnd:
                hwnd = ctypes.wintypes.HWND(parent_hwnd)
        except (AttributeError, ctypes.ArgumentError, OSError, ValueError):
            pass
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        val = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(val),
            ctypes.sizeof(val),
        )
    except (ctypes.ArgumentError, AttributeError, OSError, tk.TclError, ValueError):
        pass


def _configure_ctk_dialog(window, *, transient_parent=None, grab=False, resizable=(False, False)):
    """Dark client area + Windows dark title bar; optional transient/grab/resize policy."""
    window.configure(fg_color=Theme.APP)
    if transient_parent is not None:
        window.transient(transient_parent)
    if grab:
        window.grab_set()
    window.resizable(*resizable)

    def apply_dark():
        _apply_windows_dark_titlebar(window)

    for delay in (0, 80, 200):
        window.after(delay, apply_dark)


def _center_window_on_screen(window):
    """Place window's top-left so the window is centered on the primary screen."""
    try:
        window.update_idletasks()
        g = window.geometry()
        if "+" in g:
            wxh = g.split("+", 1)[0]
        else:
            wxh = g
        parts = wxh.split("x")
        w = int(parts[0])
        h = int(parts[1])
        sw = int(window.winfo_screenwidth())
        sh = int(window.winfo_screenheight())
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        window.geometry(f"{w}x{h}+{x}+{y}")
    except (tk.TclError, ValueError, IndexError, AttributeError):
        pass


def _center_main_window(app):
    """Use the full work area: maximized on Windows; nearly full screen (96%) on Linux/macOS."""
    # Do not call app.minsize() — CTk can pass None internally when frozen (exe) and raise TypeError.
    mw, mh = 1100, 600
    try:
        app.update_idletasks()
        sw = int(app.winfo_screenwidth())
        sh = int(app.winfo_screenheight())

        if sys.platform.startswith("win"):
            try:
                app.state("zoomed")
                return
            except tk.TclError:
                pass

        w = max(int(sw * 0.96), mw)
        h = max(int(sh * 0.96), mh)
        w = min(w, sw - 16)
        h = min(h, sh - 16)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        app.geometry(f"{w}x{h}+{x}+{y}")
    except (tk.TclError, ValueError, TypeError):
        pass


def _fit_ctk_dialog_geometry(window, *, min_w=400, min_h=200, margin_w=16, margin_h=16, center=True):
    """Size window to packed content. By default centers on screen; set center=False to keep position."""

    def apply():
        try:
            if not window.winfo_exists():
                return
        except tk.TclError:
            return
        window.update_idletasks()
        try:
            rw = int(window.winfo_reqwidth())
            rh = int(window.winfo_reqheight())
            tw = int(window.winfo_width())
            th = int(window.winfo_height())
            if tw > 1:
                rw = max(rw, tw)
            if th > 1:
                rh = max(rh, th)
        except (tk.TclError, ValueError):
            return
        w = max(rw + margin_w, min_w)
        h = max(rh + margin_h, min_h)
        if center:
            try:
                sw = int(window.winfo_screenwidth())
                sh = int(window.winfo_screenheight())
                x = max(0, (sw - w) // 2)
                y = max(0, (sh - h) // 2)
                window.geometry(f"{w}x{h}+{x}+{y}")
            except (tk.TclError, ValueError):
                window.geometry(f"{w}x{h}")
        else:
            g = window.geometry()
            if "+" in g:
                plus = g.index("+")
                window.geometry(f"{w}x{h}{g[plus:]}")
            else:
                window.geometry(f"{w}x{h}")

    apply()
    window.after(50, apply)


def _ctk_dialog_button_row(parent, *, padx=20, pady=16):
    """Full-width bottom strip with a centered button group."""
    outer = ctk.CTkFrame(parent, fg_color="transparent")
    outer.pack(fill="x", padx=padx, pady=pady)
    inner = ctk.CTkFrame(outer, fg_color="transparent")
    inner.pack(anchor="center")
    return inner


def _ctk_prompt_string(parent, title, message, *, initialvalue="", entry_width=400):
    dlg = ctk.CTkToplevel(parent)
    dlg.title(title)
    _configure_ctk_dialog(dlg, transient_parent=parent, grab=True)
    result = [None]

    ctk.CTkLabel(
        dlg,
        text=message,
        text_color=Theme.TEXT,
        font=("Segoe UI", 11),
        wraplength=max(360, entry_width + 40),
        anchor="w",
        justify="left",
    ).pack(fill="x", padx=20, pady=(12, 6))
    ent = ctk.CTkEntry(dlg, width=entry_width, **_dialog_entry_kwargs())
    ent.insert(0, initialvalue)
    ent.pack(padx=20, fill="x")

    def ok():
        result[0] = ent.get()
        dlg.destroy()

    def cancel():
        result[0] = None
        dlg.destroy()

    row = _ctk_dialog_button_row(dlg)
    ctk.CTkButton(
        row,
        text="Cancel",
        command=cancel,
        fg_color=Theme.BTN_SECONDARY,
        hover_color=Theme.BTN_SECONDARY_HOVER,
        corner_radius=Theme.RADIUS,
        width=100,
    ).pack(side="left", padx=(0, 8))
    ctk.CTkButton(
        row,
        text="OK",
        command=ok,
        fg_color=Theme.ACCENT,
        hover_color=Theme.ACCENT_HOVER,
        corner_radius=Theme.RADIUS,
        width=100,
    ).pack(side="left")
    ent.bind("<Return>", lambda e: ok())
    dlg.bind("<Escape>", lambda e: cancel())
    dlg.protocol("WM_DELETE_WINDOW", cancel)
    _fit_ctk_dialog_geometry(dlg, min_w=400, min_h=200, margin_w=24, margin_h=24)
    ent.focus_set()
    try:
        ent.select_range(0, "end")
    except tk.TclError:
        pass
    dlg.wait_window()
    return result[0]


def _ctk_prompt_integer(parent, title, message, *, minvalue=1):
    dlg = ctk.CTkToplevel(parent)
    dlg.title(title)
    _configure_ctk_dialog(dlg, transient_parent=parent, grab=True)
    result = [None]

    ctk.CTkLabel(
        dlg,
        text=message,
        text_color=Theme.TEXT,
        font=("Segoe UI", 11),
        anchor="w",
    ).pack(fill="x", padx=20, pady=(12, 6))
    ent = ctk.CTkEntry(dlg, width=200, **_dialog_entry_kwargs())
    ent.pack(padx=20, fill="x")

    def ok():
        try:
            v = int(ent.get().strip())
        except ValueError:
            return
        if v < minvalue:
            return
        result[0] = v
        dlg.destroy()

    def cancel():
        result[0] = None
        dlg.destroy()

    row = _ctk_dialog_button_row(dlg)
    ctk.CTkButton(
        row,
        text="Cancel",
        command=cancel,
        fg_color=Theme.BTN_SECONDARY,
        hover_color=Theme.BTN_SECONDARY_HOVER,
        corner_radius=Theme.RADIUS,
        width=100,
    ).pack(side="left", padx=(0, 8))
    ctk.CTkButton(
        row,
        text="OK",
        command=ok,
        fg_color=Theme.ACCENT,
        hover_color=Theme.ACCENT_HOVER,
        corner_radius=Theme.RADIUS,
        width=100,
    ).pack(side="left")
    ent.bind("<Return>", lambda e: ok())
    dlg.bind("<Escape>", lambda e: cancel())
    dlg.protocol("WM_DELETE_WINDOW", cancel)
    _fit_ctk_dialog_geometry(dlg, min_w=320, min_h=200, margin_w=24, margin_h=24)
    ent.focus_set()
    dlg.wait_window()
    return result[0]


def _ctk_ask_yes_no(parent, title, message):
    dlg = ctk.CTkToplevel(parent)
    dlg.title(title)
    _configure_ctk_dialog(dlg, transient_parent=parent, grab=True)
    result = [None]

    ctk.CTkLabel(
        dlg,
        text=message,
        text_color=Theme.TEXT,
        font=("Segoe UI", 11),
        wraplength=420,
        anchor="w",
        justify="left",
    ).pack(fill="x", padx=20, pady=(14, 10))

    def yes():
        result[0] = True
        dlg.destroy()

    def no():
        result[0] = False
        dlg.destroy()

    row = _ctk_dialog_button_row(dlg)
    ctk.CTkButton(
        row,
        text="No",
        command=no,
        fg_color=Theme.BTN_SECONDARY,
        hover_color=Theme.BTN_SECONDARY_HOVER,
        corner_radius=Theme.RADIUS,
        width=100,
    ).pack(side="left", padx=(0, 8))
    ctk.CTkButton(
        row,
        text="Yes",
        command=yes,
        fg_color=Theme.ACCENT,
        hover_color=Theme.ACCENT_HOVER,
        corner_radius=Theme.RADIUS,
        width=100,
    ).pack(side="left")
    dlg.bind("<Escape>", lambda e: no())
    dlg.protocol("WM_DELETE_WINDOW", no)
    _fit_ctk_dialog_geometry(dlg, min_w=360, min_h=200, margin_w=24, margin_h=24)
    dlg.wait_window()
    return bool(result[0])


def _style_ttk_treeview(style):
    """Dark ttk.Treeview + headings; kill clam's light 3D edge on Windows (lightcolor/darkcolor)."""
    try:
        style.theme_use("clam")
        # Match wrapper fg_color so no inner rim; light/dark must match bg or clam draws a pale box.
        bg = Theme.PANEL
        hd = Theme.RAISED
        style.configure(
            "Treeview",
            background=bg,
            foreground=Theme.TEXT,
            fieldbackground=bg,
            font=("Consolas", 11),
            borderwidth=0,
            relief="flat",
            lightcolor=bg,
            darkcolor=bg,
        )
        style.configure(
            "Treeview.Heading",
            background=hd,
            foreground=Theme.TEXT_SECONDARY,
            borderwidth=0,
            relief="flat",
            lightcolor=hd,
            darkcolor=hd,
        )
        style.map("Treeview", background=[("selected", Theme.ACCENT)])
        style.map("Treeview.Heading", background=[("active", Theme.HOVER)])
        try:
            # Drop Treeview.field chrome — often draws a pale outline on Windows clam.
            style.layout(
                "Treeview",
                [("Treeview.padding", {"sticky": "nswe", "children": [("Treeview.treearea", {"sticky": "nswe"})]})],
            )
        except tk.TclError:
            pass
    except tk.TclError:
        pass


class VSSyntaxText(tk.Text):
    def __init__(self, master, font_size=13, **kwargs):
        self._font_size = font_size
        super().__init__(master, **kwargs)
        self.tagdefs = {
            'COMMENT': {'foreground': '#6A9955'},
            'KEYWORD': {'foreground': '#C586C0'},
            'BUILTIN': {'foreground': '#DCDCAA'},
            'STRING': {'foreground': '#CE9178'},
            'DOCSTRING': {'foreground': '#6A9955'},
            'TYPES': {'foreground': '#4EC9B0'},
            'NUMBER': {'foreground': '#B5CEA8'},
            'CLASSDEF': {'foreground': '#4EC9B0'},
            'DECORATOR': {'foreground': '#D7BA7D'},
            'INSTANCE': {'foreground': '#9CDCFE'},
            'DEFINITION': {'foreground': '#DCDCAA'},
            'EXCEPTION': {'foreground': '#F44747'},
        }
        font = ("Consolas", font_size)
        italic_font = ("Consolas", font_size, "italic")
        for tag, config in self.tagdefs.items():
            config["font"] = italic_font if tag in ("COMMENT", "DOCSTRING") else font
            self.tag_configure(tag, **config)
        KEYWORD = r"\b(?P<KEYWORD>False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b"
        EXCEPTION = r"([^.'\"\\#]\b|^)(?P<EXCEPTION>ArithmeticError|AssertionError|AttributeError|BaseException|BlockingIOError|BrokenPipeError|BufferError|BytesWarning|ChildProcessError|ConnectionAbortedError|ConnectionError|ConnectionRefusedError|ConnectionResetError|DeprecationWarning|EOFError|Ellipsis|EnvironmentError|Exception|FileExistsError|FileNotFoundError|FloatingPointError|FutureWarning|GeneratorExit|IOError|ImportError|ImportWarning|IndentationError|IndexError|InterruptedError|IsADirectoryError|KeyError|KeyboardInterrupt|LookupError|MemoryError|ModuleNotFoundError|NameError|NotADirectoryError|NotImplemented|NotImplementedError|OSError|OverflowError|PendingDeprecationWarning|PermissionError|ProcessLookupError|RecursionError|ReferenceError|ResourceWarning|RuntimeError|RuntimeWarning|StopAsyncIteration|StopIteration|SyntaxError|SyntaxWarning|SystemError|SystemExit|TabError|TimeoutError|TypeError|UnboundLocalError|UnicodeDecodeError|UnicodeEncodeError|UnicodeError|UnicodeTranslateError|UnicodeWarning|UserWarning|ValueError|Warning|WindowsError|ZeroDivisionError)\b"
        BUILTIN = r"([^.'\"\\#]\b|^)(?P<BUILTIN>abs|all|any|ascii|bin|breakpoint|callable|chr|classmethod|compile|complex|copyright|credits|delattr|dir|divmod|enumerate|eval|exec|exit|filter|format|frozenset|getattr|globals|hasattr|hash|help|hex|id|input|isinstance|issubclass|iter|len|license|locals|map|max|memoryview|min|next|oct|open|ord|pow|print|quit|range|repr|reversed|round|set|setattr|slice|sorted|staticmethod|sum|type|vars|zip)\b"
        DOCSTRING = r"(?P<DOCSTRING>(?i:r|u|f|fr|rf|b|br|rb)?'''[^'\\]*((\\.|'(?!''))[^'\\]*)*(''')?|(?i:r|u|f|fr|rf|b|br|rb)?\"\"\"[^\"\\]*((\\.|\"(?!\"\"))[^\"\\]*)*(\"\"\")?)"
        STRING = r"(?P<STRING>(?i:r|u|f|fr|rf|b|br|rb)?'[^'\\\n]*(\\.[^'\\\n]*)*'?|(?i:r|u|f|fr|rf|b|br|rb)?\"[^\"\\\n]*(\\.[^\"\\\n]*)*\"?)"
        TYPES = r"\b(?P<TYPES>bool|bytearray|bytes|dict|float|int|list|str|tuple|object)\b"
        NUMBER = r"\b(?P<NUMBER>((0x|0b|0o|#)[\da-fA-F]+)|((\d*\.)?\d+))\b"
        CLASSDEF = r"(?<=\bclass)[ \t]+(?P<CLASSDEF>\w+)[ \t]*[:\(]"
        DECORATOR = r"(^[ \t]*(?P<DECORATOR>@[\w\d\.]+))"
        INSTANCE = r"\b(?P<INSTANCE>super|self|cls)\b"
        COMMENT = r"(?P<COMMENT>#[^\n]*)"
        SYNC = r"(?P<SYNC>\n)"
        PROG = rf"{KEYWORD}|{BUILTIN}|{EXCEPTION}|{TYPES}|{COMMENT}|{DOCSTRING}|{STRING}|{SYNC}|{INSTANCE}|{DECORATOR}|{NUMBER}|{CLASSDEF}"
        IDPROG = r"(?<!class)\s+(\w+)"
        self.cd = ic.ColorDelegator()
        self.cd.prog = re.compile(PROG, re.S | re.M)
        self.cd.idprog = re.compile(IDPROG, re.S)
        self.cd.tagdefs = {**self.cd.tagdefs, **self.tagdefs}
        ip.Percolator(self).insertfilter(self.cd)
        self.tag_configure("current_line", background=Theme.LINE_HL)

    def set_font_size(self, size):
        self._font_size = size
        font = ("Consolas", size)
        italic = ("Consolas", size, "italic")
        self.configure(font=font)
        for tag, cfg in self.tagdefs.items():
            cfg["font"] = italic if tag in ("COMMENT", "DOCSTRING") else font
            self.tag_configure(tag, **cfg)

    def set_current_line(self, line):
        self.tag_remove("current_line", "1.0", "end")
        if line > 0:
            self.tag_add("current_line", f"{line}.0", f"{line}.0 lineend + 1 char")
class LiveConsole(ctk.CTkFrame):
    """Console output: tk Text + CTkScrollbar (native ScrolledText scrollbars stay light on Windows)."""

    def __init__(self, master, height=8, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self.text = tk.Text(
            self,
            height=height,
            bg=Theme.EDITOR,
            fg=Theme.TEXT,
            font=("Consolas", 11),
            insertbackground=Theme.TEXT,
            selectbackground=Theme.SELECTION,
            highlightthickness=0,
            borderwidth=0,
            wrap="word",
        )
        self._sb = ctk.CTkScrollbar(self, command=self.text.yview, orientation="vertical", **_ctk_scrollbar_kwargs())
        self.text.configure(yscrollcommand=self._sb.set)
        self.text.pack(side="left", fill="both", expand=True)
        self._sb.pack(side="right", fill="y")

    def write(self, text, color=None):
        self.text.insert("end", text)
        self.text.see("end")

    def flush(self):
        pass
class PyForgePro(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.configure(fg_color=Theme.APP)
        self.title("PyForge Pro")
        self.geometry("1400x1150")
        self.minsize(1100, 600)
        self.settings = self.load_settings()
        ctk.set_appearance_mode(self.settings.get("appearance", "dark"))
        self.project_path = None
        self.current_file = None
        self.open_files = {}
        self.recent_projects = self.load_recent_projects()
        self.last_project = None
        self.last_file = None
        self._recovery_tick = 0
        self.tab_order = []
        self.secondary_file = None
        self._split_visible = False
        self._pty_session = None
        self._pdb_session = None
        self.breakpoints = {}
        self.load_last_state()
        self.setup_ui()
        self.after_idle(self._apply_main_window_geometry)
        self.after(250, self._apply_main_window_geometry)
        self.after(500, self._apply_main_window_geometry)
        self.after(80, lambda: _apply_windows_dark_titlebar(self))
        self.setup_bindings()
        self.start_autosave()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        if self.last_project and os.path.isdir(self.last_project):
            self.open_project_folder(self.last_project, restore=True)
            if self.last_file and os.path.exists(self.last_file) and self.last_file.startswith(self.last_project + os.sep):
                self.open_file(self.last_file)

    def _apply_main_window_geometry(self):
        """Apply default size + center after CTk has built the layout (avoids tiny first-frame geometry)."""
        _center_main_window(self)

    def load_last_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.last_project = data.get("last_project")
                    self.last_file = data.get("last_file")
            except (OSError, json.JSONDecodeError):
                pass
    def save_state(self):
        if not self.project_path or not os.path.isdir(self.project_path):
            if os.path.exists(STATE_FILE):
                try:
                    os.remove(STATE_FILE)
                except OSError:
                    pass
            return
        data = {
            "last_project": self.project_path,
            "last_file": self.current_file if self.current_file else None
        }
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass
    def on_closing(self):
        self.save_current_file(silent=True)
        self.save_state()
        self.save_settings()
        self.destroy()
    def load_settings(self):
        default = {"font_size": 13, "appearance": "dark", "format_on_save": False, "formatter": "ruff"}
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    default.update(json.load(f))
            except (OSError, json.JSONDecodeError):
                pass
        return default
    def save_settings(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except OSError:
            pass
    def load_recent_projects(self):
        if os.path.exists(RECENT_FILE):
            try:
                with open(RECENT_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("recent", [])
            except (OSError, json.JSONDecodeError):
                pass
        return []
    def save_recent_projects(self):
        data = {"recent": self.recent_projects}
        try:
            with open(RECENT_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass
    def add_to_recent(self, path):
        if not path or not os.path.isdir(path):
            return
        self.recent_projects = [p for p in self.recent_projects if p != path]
        self.recent_projects.insert(0, path)
        self.recent_projects = self.recent_projects[:8]
        self.save_recent_projects()
        self.refresh_recent_ui()
    def setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_ctk_menubar()
        main = ctk.CTkFrame(self, fg_color=Theme.APP, corner_radius=0)
        main.grid(row=1, column=1, sticky="nsew", padx=(8, 10), pady=10)
        main.grid_rowconfigure(3, weight=1)
        main.grid_columnconfigure(1, weight=1)
        _fs = int(self.settings.get("font_size", 13))
        self.search_frame = ctk.CTkFrame(
            main,
            height=42,
            fg_color=Theme.RAISED,
            corner_radius=Theme.RADIUS,
            border_width=1,
            border_color=Theme.BORDER_SUBTLE,
        )
        self.search_frame.grid(row=0, column=0, columnspan=4, sticky="ew")
        self.search_frame.grid_remove()
        self.match_case_var = tk.BooleanVar(value=False)
        ctk.CTkLabel(self.search_frame, text="Find:", text_color=Theme.TEXT_SECONDARY).pack(side="left", padx=(10, 5))
        self.search_entry = ctk.CTkEntry(
            self.search_frame,
            placeholder_text="Search",
            width=300,
            fg_color=Theme.ENTRY_BG,
            border_color=Theme.BORDER,
            text_color=Theme.TEXT,
            placeholder_text_color=Theme.TEXT_MUTED,
            corner_radius=Theme.RADIUS,
            height=32,
        )
        self.search_entry.pack(side="left", padx=5)
        self.find_next_btn = ctk.CTkButton(
            self.search_frame,
            text="Next",
            command=self.find_next,
            width=88,
            height=30,
            corner_radius=Theme.RADIUS,
            fg_color=Theme.BTN_SECONDARY,
            hover_color=Theme.BTN_SECONDARY_HOVER,
            text_color=Theme.TEXT,
        )
        self.find_next_btn.pack(side="left", padx=4)
        self.find_prev_btn = ctk.CTkButton(
            self.search_frame,
            text="Previous",
            command=self.find_previous,
            width=88,
            height=30,
            corner_radius=Theme.RADIUS,
            fg_color=Theme.BTN_SECONDARY,
            hover_color=Theme.BTN_SECONDARY_HOVER,
            text_color=Theme.TEXT,
        )
        self.find_prev_btn.pack(side="left", padx=4)
        self.match_case_chk = ctk.CTkCheckBox(
            self.search_frame,
            text="Match case",
            variable=self.match_case_var,
            text_color=Theme.TEXT_SECONDARY,
            fg_color=Theme.RAISED,
            hover_color=Theme.HOVER,
        )
        self.match_case_chk.pack(side="left", padx=5)
        self.close_search_btn = ctk.CTkButton(
            self.search_frame,
            text="×",
            command=self.hide_search,
            width=36,
            height=36,
            corner_radius=18,
            fg_color="transparent",
            hover_color=Theme.HOVER,
            text_color=Theme.TEXT_MUTED,
            font=("Segoe UI", 18, "normal"),
        )
        self.close_search_btn.pack(side="right", padx=(8, 10))
        self.close_search_btn.bind("<Enter>", lambda e: self.close_search_btn.configure(text_color=Theme.DANGER))
        self.close_search_btn.bind("<Leave>", lambda e: self.close_search_btn.configure(text_color=Theme.TEXT_MUTED))
        self.tab_bar = ctk.CTkScrollableFrame(
            main,
            height=38,
            orientation="horizontal",
            fg_color=Theme.BORDER_SUBTLE,
            corner_radius=Theme.RADIUS,
            border_width=0,
            scrollbar_fg_color=Theme.PANEL,
            scrollbar_button_color=Theme.BTN_SECONDARY,
            scrollbar_button_hover_color=Theme.BTN_SECONDARY_HOVER,
        )
        self.tab_bar.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 6))
        self.breadcrumb = ctk.CTkLabel(
            main, text="", anchor="w", font=("Segoe UI", 11), text_color=Theme.TEXT_MUTED
        )
        self.breadcrumb.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(0, 4))
        self.line_numbers = tk.Text(
            main,
            width=6,
            padx=12,
            pady=0,
            takefocus=0,
            bg=Theme.GUTTER,
            fg=Theme.GUTTER_FG,
            font=("Consolas", _fs),
            state="disabled",
            relief="flat",
            highlightthickness=0,
            borderwidth=0,
            cursor="arrow",
        )
        self.line_numbers.grid(row=3, column=0, sticky="ns")
        tk.Frame(main, width=1, bg=Theme.BORDER_SUBTLE).grid(row=3, column=0, sticky="ns", padx=(58, 0))
        self.editor = VSSyntaxText(
            main,
            font_size=_fs,
            undo=True,
            wrap="none",
            bg=Theme.EDITOR,
            fg=Theme.TEXT,
            insertbackground=Theme.TEXT,
            selectbackground=Theme.SELECTION,
            font=("Consolas", _fs),
            borderwidth=0,
            highlightthickness=0,
        )
        self.editor.grid(row=3, column=1, sticky="nsew")
        self.vsb = ctk.CTkScrollbar(
            main,
            orientation="vertical",
            command=self.yview_both,
            **_ctk_scrollbar_kwargs(),
        )
        self.vsb.grid(row=3, column=2, sticky="ns")
        self.minimap = EditorMinimap(main, self.editor, width=72, bg=Theme.MINIMAP)
        self.minimap.grid(row=3, column=3, sticky="ns")
        self.editor.configure(yscrollcommand=self._yscroll_cmd)
        self.line_numbers.configure(yscrollcommand=self._yscroll_cmd)
        self.editor.bind("<MouseWheel>", self.on_mousewheel)
        self.line_numbers.bind("<MouseWheel>", self.on_mousewheel)
        self.editor.bind("<Button-4>", lambda e: self.yview_both("scroll", -1, "units"))
        self.editor.bind("<Button-5>", lambda e: self.yview_both("scroll", 1, "units"))
        self.line_numbers.bind("<Button-4>", lambda e: self.yview_both("scroll", -1, "units"))
        self.line_numbers.bind("<Button-5>", lambda e: self.yview_both("scroll", 1, "units"))
        self.editor.bind("<Button-1>", self.on_click_place_cursor)
        self.line_numbers.bind("<Button-1>", self.on_line_number_click)
        update_events = [
            "<<Modified>>", "<Key>", "<KeyRelease>", "<ButtonRelease-1>",
            "<<Paste>>", "<<Cut>>", "<<Undo>>", "<<Redo>>",
            "<FocusIn>", "<FocusOut>",
        ]
        for ev in update_events:
            self.editor.bind(ev, lambda e=None: self.after(50, self.update_highlight_and_lines))
        self.editor.bind("<Configure>", lambda e=None: self.after(100, self.update_highlight_and_lines))
        self.bottom_tabs = ctk.CTkTabview(
            main,
            height=200,
            fg_color=Theme.PANEL,
            segmented_button_fg_color=Theme.RAISED,
            segmented_button_selected_color=Theme.TAB_ACTIVE,
            segmented_button_selected_hover_color=Theme.HOVER,
            segmented_button_unselected_color=Theme.TAB_INACTIVE,
            segmented_button_unselected_hover_color=Theme.TAB_HOVER,
            text_color=Theme.TEXT,
            text_color_disabled=Theme.TEXT_DIM,
        )
        self.bottom_tabs.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self.bottom_tabs.add("Console")
        self.bottom_tabs.add("Terminal")
        self.bottom_tabs.add("Debug")
        self.bottom_tabs.add("Pylint")
        self.console = LiveConsole(self.bottom_tabs.tab("Console"), height=8)
        self.console.pack(fill="both", expand=True, padx=4, pady=4)
        term_f = ctk.CTkFrame(self.bottom_tabs.tab("Terminal"), fg_color="transparent")
        term_f.pack(fill="both", expand=True, padx=4, pady=4)
        term_out_wrap = ctk.CTkFrame(term_f, fg_color="transparent")
        term_out_wrap.pack(fill="both", expand=True)
        self.term_out = tk.Text(
            term_out_wrap,
            height=7,
            bg=Theme.EDITOR,
            fg=Theme.TEXT,
            font=("Consolas", 10),
            insertbackground=Theme.TEXT,
            selectbackground=Theme.SELECTION,
            highlightthickness=0,
            borderwidth=0,
            wrap="word",
        )
        self._term_sb = ctk.CTkScrollbar(
            term_out_wrap, command=self.term_out.yview, orientation="vertical", **_ctk_scrollbar_kwargs()
        )
        self.term_out.configure(yscrollcommand=self._term_sb.set)
        self.term_out.pack(side="left", fill="both", expand=True)
        self._term_sb.pack(side="right", fill="y")
        tf = ctk.CTkFrame(term_f, fg_color="transparent")
        tf.pack(fill="x", pady=(4, 0))
        self.term_in = ctk.CTkEntry(
            tf,
            placeholder_text="Shell input (Enter) — Start terminal first",
            fg_color=Theme.ENTRY_BG,
            border_color=Theme.BORDER,
            text_color=Theme.TEXT,
            placeholder_text_color=Theme.TEXT_MUTED,
            corner_radius=Theme.RADIUS,
            height=32,
        )
        self.term_in.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            tf,
            text="Start",
            width=70,
            height=30,
            corner_radius=Theme.RADIUS,
            command=self.start_embedded_terminal,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
        ).pack(side="right")
        ctk.CTkButton(
            tf,
            text="Stop",
            width=50,
            height=30,
            corner_radius=Theme.RADIUS,
            command=self.stop_embedded_terminal,
            fg_color=Theme.BTN_SECONDARY,
            hover_color=Theme.BTN_SECONDARY_HOVER,
        ).pack(side="right", padx=(0, 6))
        self.term_in.bind("<Return>", self._terminal_send_line)
        dbg_f = ctk.CTkFrame(self.bottom_tabs.tab("Debug"), fg_color="transparent")
        dbg_f.pack(fill="both", expand=True, padx=4, pady=4)
        db_btn = ctk.CTkFrame(dbg_f, fg_color="transparent")
        db_btn.pack(fill="x")
        for lab, cmd in [
            ("Continue", "c"),
            ("Next", "n"),
            ("Step", "s"),
            ("Finish", "r"),
            ("Quit", "q"),
        ]:
            ctk.CTkButton(
                db_btn,
                text=lab,
                width=72,
                height=28,
                corner_radius=Theme.RADIUS,
                command=lambda c=cmd: self._pdb_send(c),
                fg_color=Theme.BTN_SECONDARY,
                hover_color=Theme.BTN_SECONDARY_HOVER,
            ).pack(side="left", padx=2)
        ctk.CTkButton(
            db_btn,
            text="Start pdb",
            width=90,
            height=28,
            corner_radius=Theme.RADIUS,
            command=self.start_visual_debugger,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
        ).pack(side="right", padx=8)
        self.dbg_stack = ctk.CTkLabel(
            dbg_f, text="Stack: (see pdb output below)", anchor="w", text_color=Theme.TEXT_MUTED
        )
        self.dbg_stack.pack(fill="x", pady=(4, 0))
        dbg_out_wrap = ctk.CTkFrame(dbg_f, fg_color="transparent")
        dbg_out_wrap.pack(fill="both", expand=True, pady=(4, 0))
        self.dbg_out = tk.Text(
            dbg_out_wrap,
            height=5,
            bg=Theme.EDITOR,
            fg=Theme.TEXT,
            font=("Consolas", 10),
            insertbackground=Theme.TEXT,
            selectbackground=Theme.SELECTION,
            highlightthickness=0,
            borderwidth=0,
            wrap="word",
        )
        self._dbg_sb = ctk.CTkScrollbar(
            dbg_out_wrap, command=self.dbg_out.yview, orientation="vertical", **_ctk_scrollbar_kwargs()
        )
        self.dbg_out.configure(yscrollcommand=self._dbg_sb.set)
        self.dbg_out.pack(side="left", fill="both", expand=True)
        self._dbg_sb.pack(side="right", fill="y")
        df2 = ctk.CTkFrame(dbg_f, fg_color="transparent")
        df2.pack(fill="x")
        self.dbg_in = ctk.CTkEntry(
            df2,
            placeholder_text="pdb command",
            fg_color=Theme.ENTRY_BG,
            border_color=Theme.BORDER,
            text_color=Theme.TEXT,
            placeholder_text_color=Theme.TEXT_MUTED,
            corner_radius=Theme.RADIUS,
            height=32,
        )
        self.dbg_in.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            df2,
            text="Send",
            width=60,
            height=30,
            corner_radius=Theme.RADIUS,
            command=self._pdb_send_entry,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
        ).pack(side="right")
        self.dbg_in.bind("<Return>", lambda e: self._pdb_send_entry())
        pl_f = ctk.CTkFrame(self.bottom_tabs.tab("Pylint"), fg_color="transparent")
        pl_f.pack(fill="both", expand=True, padx=4, pady=4)
        ctk.CTkButton(
            pl_f,
            text="Run pylint",
            command=self.run_pylint_ui,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            corner_radius=Theme.RADIUS,
        ).pack(anchor="w", pady=(0, 6))
        pl_wrap = ctk.CTkFrame(
            pl_f,
            fg_color=Theme.PANEL,
            corner_radius=Theme.RADIUS,
            border_width=0,
        )
        pl_wrap.pack(fill="both", expand=True)
        psb = ctk.CTkScrollbar(pl_wrap, orientation="vertical", **_ctk_scrollbar_kwargs())
        self.pylint_tree = ttk.Treeview(
            pl_wrap,
            columns=("path", "line", "msg"),
            displaycolumns=("path", "line", "msg"),
            yscrollcommand=psb.set,
            height=8,
        )
        self.pylint_tree.heading("path", text="File")
        self.pylint_tree.heading("line", text="Line")
        self.pylint_tree.heading("msg", text="Message")
        self.pylint_tree.column("path", width=180)
        self.pylint_tree.column("line", width=50)
        self.pylint_tree.column("msg", width=400)
        psb.configure(command=self.pylint_tree.yview)
        self.pylint_tree.pack(side="left", fill="both", expand=True, padx=0, pady=0)
        psb.pack(side="right", fill="y", padx=0, pady=0)
        self.pylint_tree.bind("<Double-1>", self._pylint_goto)
        sidebar = ctk.CTkFrame(
            self,
            width=300,
            fg_color=Theme.RAISED,
            corner_radius=Theme.RADIUS_LG,
            border_width=1,
            border_color=Theme.BORDER_SUBTLE,
        )
        sidebar.grid(row=1, column=2, sticky="ns", pady=10, padx=(0, 10))
        sidebar.grid_propagate(False)
        ctk.CTkLabel(sidebar, text="PYFORGE PRO", font=("Segoe UI", 24, "bold"), text_color=Theme.TEXT).pack(
            pady=(20, 5)
        )
        ctk.CTkLabel(sidebar, text="Developer Edition", font=("Segoe UI", 10), text_color=Theme.TEXT_MUTED).pack()
        self.project_btn = ctk.CTkButton(
            sidebar,
            text="Open Project",
            width=260,
            height=50,
            corner_radius=Theme.RADIUS,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            font=("Segoe UI", 14, "bold"),
            command=self.toggle_project,
        )
        self.project_btn.pack(pady=20, padx=20)
        ctk.CTkButton(
            sidebar,
            text="Create Project",
            width=260,
            height=40,
            corner_radius=Theme.RADIUS,
            fg_color=Theme.BTN_SECONDARY,
            hover_color=Theme.BTN_SECONDARY_HOVER,
            command=self.create_project,
        ).pack(pady=5, padx=20)
        self.project_label = ctk.CTkLabel(sidebar, text="No project open", text_color=Theme.TEXT_MUTED)
        self.project_label.pack(pady=(0, 4))
        self.git_label = ctk.CTkLabel(sidebar, text="", text_color=Theme.SUCCESS, font=("Segoe UI", 11))
        self.git_label.pack(pady=(0, 8), anchor="w", padx=20)
        ctk.CTkButton(
            sidebar,
            text="Open project folder",
            width=260,
            height=36,
            corner_radius=Theme.RADIUS,
            fg_color=Theme.BTN_SECONDARY,
            hover_color=Theme.BTN_SECONDARY_HOVER,
            font=("Segoe UI", 12),
            command=self.open_project_folder_explorer,
        ).pack(pady=(0, 16), padx=20)
        btn_style = {
            "width": 260,
            "height": 40,
            "fg_color": Theme.BTN_SECONDARY,
            "hover_color": Theme.BTN_SECONDARY_HOVER,
            "corner_radius": Theme.RADIUS,
        }
        for text, cmd in [
            ("New File", self.new_file),
            ("Save File", self.save_current_file),
            ("Run Current", self.run_current_file),
            ("Build .exe", self.build_exe),
        ]:
            ctk.CTkButton(sidebar, text=text, command=cmd, **btn_style).pack(pady=4, padx=20)
        ctk.CTkLabel(sidebar, text="Project tree", font=("Segoe UI", 14, "bold"), text_color=Theme.TEXT_SECONDARY)\
            .pack(pady=(20, 5), anchor="w", padx=20)
        tree_wrap = ctk.CTkFrame(
            sidebar,
            fg_color=Theme.PANEL,
            corner_radius=Theme.RADIUS,
            border_width=0,
        )
        tree_wrap.pack(fill="both", expand=True, padx=20, pady=5)
        tsb = ctk.CTkScrollbar(tree_wrap, orientation="vertical", **_ctk_scrollbar_kwargs())
        _style_ttk_treeview(ttk.Style())
        self.file_tree = ttk.Treeview(
            tree_wrap,
            columns=("fp",),
            displaycolumns=(),
            selectmode="browse",
            yscrollcommand=tsb.set,
        )
        tsb.configure(command=self.file_tree.yview)
        tsb.pack(side="right", fill="y", padx=0, pady=0)
        self.file_tree.pack(side="left", fill="both", expand=True, padx=0, pady=0)
        self.file_tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.file_tree.bind("<Button-3>", self.show_tree_menu)
        ctk.CTkLabel(sidebar, text="Recent Projects", font=("Segoe UI", 14, "bold"), text_color=Theme.TEXT_SECONDARY)\
            .pack(pady=(20, 5), anchor="w", padx=20)
        self.recent_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        self.recent_frame.pack(fill="x", padx=20, pady=5)
        self.recent_labels = []
        self.refresh_recent_ui()
        ctk.CTkLabel(sidebar, text="© 2026 • PyForge", font=("Segoe UI", 9), text_color=Theme.TEXT_DIM)\
            .pack(side="bottom", pady=15)
        self.search_entry.bind("<Return>", lambda e: self.find_next())
    def _yscroll_cmd(self, *args):
        self.vsb.set(*args)
        try:
            self.minimap.sync_viewport()
        except tk.TclError:
            pass

    def yview_both(self, *args):
        self.editor.yview(*args)
        self.line_numbers.yview(*args)

    def on_mousewheel(self, event):
        if sys.platform.startswith("win"):
            delta = -1 * (event.delta // 120)
        else:
            delta = -1 if event.delta > 0 else 1
        self.yview_both("scroll", delta, "units")
        return "break"
    def on_click_place_cursor(self, event):
        self.update_highlight_and_lines()
        return None
    def on_line_number_click(self, event):
        index = self.line_numbers.index(f"@{event.x},{event.y}")
        line = int(index.split('.')[0])
        self.editor.mark_set("insert", f"{line}.0")
        self.editor.see(f"{line}.0")
        self.update_highlight_and_lines()
        return "break"
    def update_highlight_and_lines(self, event=None):
        try:
            idx = self.editor.index("insert")
            line = int(idx.split(".")[0])
        except tk.TclError:
            line = 1
        self.editor.set_current_line(line)
        self.update_line_numbers(line)
    def update_line_numbers(self, current_line=None):
        self.line_numbers.config(state="normal")
        self.line_numbers.delete("1.0", "end")
        content = self.editor.get("1.0", "end-1c")
        line_count = len(content.split("\n"))
        numbers = "\n".join(str(i).rjust(5) for i in range(1, line_count + 1))
        self.line_numbers.insert("1.0", numbers)
        self.line_numbers.tag_remove("current", "1.0", "end")
        if current_line and current_line > 0:
            self.line_numbers.tag_add("current", f"{current_line}.0", f"{current_line}.end")
        self.line_numbers.tag_configure(
            "current",
            foreground=Theme.GUTTER_ACTIVE,
            font=("Consolas", getattr(self.editor, "_font_size", 13), "bold"),
        )
        self.line_numbers.tag_configure("right", justify="right")
        self.line_numbers.tag_add("right", "1.0", "end")
        self.line_numbers.config(state="disabled")
        top_fraction = self.editor.yview()[0]
        self.line_numbers.yview_moveto(top_fraction)
    def refresh_recent_ui(self):
        for widget in self.recent_frame.winfo_children():
            widget.destroy()
        self.recent_labels.clear()
        for path in self.recent_projects:
            if not os.path.isdir(path):
                continue
            name = os.path.basename(path)
            lbl = ctk.CTkLabel(
                self.recent_frame,
                text=name,
                text_color=Theme.TEXT_MUTED,
                font=("Segoe UI", 12),
                anchor="w",
                cursor="hand2",
            )
            lbl.pack(fill="x", pady=3)
            lbl.bind("<Button-1>", lambda e, p=path: self.open_project_folder(p))
            lbl.bind("<Enter>", lambda e, l=lbl: l.configure(text_color=Theme.TEXT))
            lbl.bind("<Leave>", lambda e, l=lbl: l.configure(text_color=Theme.TEXT_MUTED))
            lbl.bind("<Button-3>", lambda e, p=path: self.show_remove_menu(e, p))
            self.recent_labels.append(lbl)
    def refresh_file_tabs(self):
        for w in self.tab_bar.winfo_children():
            w.destroy()
        for path in self.tab_order:
            if path not in self.open_files:
                continue
            name = os.path.basename(path)
            active = path == self.current_file
            row = ctk.CTkFrame(self.tab_bar, fg_color="transparent")
            tab_btn = ctk.CTkButton(
                row,
                text=name,
                width=min(168, 18 + len(name) * 8),
                height=30,
                corner_radius=Theme.RADIUS,
                fg_color=Theme.TAB_ACTIVE if active else Theme.TAB_INACTIVE,
                hover_color=Theme.HOVER if active else Theme.TAB_HOVER,
                border_width=1 if active else 0,
                border_color=Theme.ACCENT if active else Theme.BORDER_SUBTLE,
                text_color=Theme.TEXT if active else Theme.TEXT_SECONDARY,
                command=lambda p=path: self.open_file(p),
            )
            tab_btn.pack(side="left", padx=(2, 0), pady=4)
            ctk.CTkButton(
                row,
                text="×",
                width=28,
                height=28,
                corner_radius=4,
                fg_color=Theme.TAB_INACTIVE if not active else Theme.TAB_ACTIVE,
                hover_color=Theme.DANGER,
                text_color=Theme.TEXT_MUTED,
                font=("Segoe UI", 16),
                command=lambda p=path: self.close_file(p),
            ).pack(side="left", padx=(1, 2), pady=4)
            row.pack(side="left", padx=1)
    def show_remove_menu(self, event, path):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Remove from Recents", command=lambda: self.remove_recent(path))
        menu.post(event.x_root, event.y_root)
    def remove_recent(self, path):
        if path in self.recent_projects:
            self.recent_projects.remove(path)
            self.save_recent_projects()
            self.refresh_recent_ui()
    def _tree_skip_dir(self, name):
        if name.startswith("."):
            return True
        return name in {
            "__pycache__", ".git", ".venv", "venv", "node_modules", "build", "dist", ".idea", ".tox", ".mypy_cache"
        }
    def _populate_file_tree(self, parent_id, base_path):
        try:
            entries = sorted(
                os.listdir(base_path),
                key=lambda x: (not os.path.isdir(os.path.join(base_path, x)), x.lower()),
            )
        except OSError:
            return
        for name in entries:
            if self._tree_skip_dir(name):
                continue
            full = os.path.join(base_path, name)
            if os.path.isdir(full):
                nid = self.file_tree.insert(parent_id, "end", text=name, values=(full,))
                self._populate_file_tree(nid, full)
            elif name.endswith(".py"):
                self.file_tree.insert(parent_id, "end", text=name, values=(full,))
    def _walk_py_files(self, root_dir):
        root_dir = os.path.abspath(root_dir)
        skip = {
            "__pycache__", ".git", ".venv", "venv", "node_modules", "build", "dist", ".idea", ".tox", ".mypy_cache"
        }
        for r, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in skip and not d.startswith(".")]
            for f in sorted(files):
                if f.endswith(".py"):
                    yield os.path.join(r, f)
    def _first_py_in_project(self):
        for p in self._walk_py_files(self.project_path):
            return p
        return None
    def _tree_select_by_path(self, path):
        if not self.project_path:
            return
        want = os.path.normcase(os.path.abspath(path))

        def walk(iid):
            vals = self.file_tree.item(iid, "values")
            if vals and vals[0] and os.path.normcase(os.path.abspath(vals[0])) == want:
                return iid
            for c in self.file_tree.get_children(iid):
                r = walk(c)
                if r:
                    return r
            return None

        for top in self.file_tree.get_children():
            r = walk(top)
            if r:
                self.file_tree.selection_set(r)
                self.file_tree.see(r)
                return
    def refresh_git_status(self):
        if not self.project_path:
            self.git_label.configure(text="")
            return
        git_dir = os.path.join(self.project_path, ".git")
        if not os.path.isdir(git_dir):
            self.git_label.configure(text="")
            return
        try:
            git_kw = {}
            if sys.platform.startswith("win"):
                cf = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if cf:
                    git_kw["creationflags"] = cf
            r = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=15,
                **git_kw,
            )
            if r.returncode != 0:
                self.git_label.configure(text="Git: (error)")
                return
            lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
            n = len(lines)
            self.git_label.configure(text=f"Git: {n} changed" if n else "Git: clean")
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            self.git_label.configure(text="")
    def _update_breadcrumb(self):
        if not self.project_path:
            self.breadcrumb.configure(text="")
            return
        rel = ""
        if self.current_file:
            try:
                rel = os.path.relpath(self.current_file, self.project_path)
            except ValueError:
                rel = os.path.basename(self.current_file)
        self.breadcrumb.configure(
            text=f"{os.path.basename(self.project_path)}  ›  {rel or '(no file)'}"
        )
    def show_tree_menu(self, event):
        if not self.project_path:
            return
        iid = self.file_tree.identify_row(event.y)
        if not iid:
            return
        self.file_tree.selection_set(iid)
        vals = self.file_tree.item(iid, "values")
        if not vals or not vals[0]:
            return
        path = vals[0]
        if not path.endswith(".py") or not os.path.isfile(path):
            return
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Rename…", command=lambda p=path: self.rename_project_file(p))
        menu.post(event.x_root, event.y_root)
    def rename_project_file(self, old_path):
        if not self.project_path or not old_path.endswith(".py"):
            return
        if not os.path.isfile(old_path):
            messagebox.showwarning("Rename", "That file is no longer on disk.")
            self.load_project_files()
            return
        self._sync_editor_to_open_files()
        old_name = os.path.basename(old_path)
        new_name = simpledialog.askstring("Rename file", "New filename:", initialvalue=old_name)
        if new_name is None:
            return
        new_name = new_name.strip()
        if not new_name:
            return
        if not new_name.endswith(".py"):
            new_name += ".py"
        if "/" in new_name or "\\" in new_name or ".." in new_name:
            messagebox.showerror("Invalid name", "Use a simple filename only.")
            return
        new_name = os.path.basename(new_name)
        if not new_name.endswith(".py"):
            new_name += ".py"
        new_path = os.path.join(os.path.dirname(old_path), new_name)
        if os.path.normcase(new_path) == os.path.normcase(old_path):
            return
        if os.path.exists(new_path):
            messagebox.showerror("Rename", "A file with that name already exists.")
            return
        try:
            os.rename(old_path, new_path)
        except OSError as e:
            messagebox.showerror("Rename failed", str(e))
            return
        if old_path in self.open_files:
            buf = self.open_files.pop(old_path)
        else:
            try:
                with open(new_path, "r", encoding="utf-8") as f:
                    buf = f.read()
            except OSError:
                buf = ""
        self.open_files[new_path] = buf
        if self.current_file and os.path.normcase(self.current_file) == os.path.normcase(old_path):
            self.current_file = new_path
            self.title(f"PyForge Pro — {os.path.basename(new_path)}")
        self.load_project_files()
        self._tree_select_by_path(new_path)
        self.save_state()
    def open_project_folder(self, path, restore=False):
        if not os.path.isdir(path):
            messagebox.showwarning("Not Found", f"Project folder no longer exists:\n{path}")
            self.recent_projects = [p for p in self.recent_projects if p != path]
            self.save_recent_projects()
            self.refresh_recent_ui()
            return
        if self.project_path == path:
            return
        if self.project_path:
            self.save_current_file(silent=True)
        self.project_path = path
        self.tab_order = []
        self.open_files.clear()
        self.current_file = None
        self.editor.delete("1.0", "end")
        self.title("PyForge Pro")
        self.project_btn.configure(text="Close Project")
        self.project_label.configure(text=os.path.basename(path))
        self.load_project_files()
        fp = self._first_py_in_project()
        if fp:
            self.open_file(fp)
        if not restore:
            self.add_to_recent(path)
        self.save_state()
    def setup_bindings(self):
        self.bind("<Control-n>", lambda e: self.new_file())
        self.bind("<Control-s>", lambda e: self.save_current_file())
        self.bind("<Control-r>", lambda e: self.run_current_file())
        self.bind("<Control-b>", lambda e: self.build_exe())
        self.bind("<Control-f>", lambda e: self.toggle_search())
        self.bind("<Control-F>", lambda e: self.toggle_search())
        self.bind("<Control-g>", lambda e: self.go_to_line())
        self.bind("<Control-Shift-F>", lambda e: self.find_in_project())
        self.bind("<Control-Shift-f>", lambda e: self.find_in_project())
        self.bind("<F9>", self.toggle_breakpoint)
        self.bind("<Escape>", lambda e: self.hide_search() if self.search_frame.winfo_ismapped() else None)
    def start_autosave(self):
        def save():
            if self.current_file:
                try:
                    content = self.editor.get("1.0", "end-1c")
                    with open(self.current_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    self.open_files[self.current_file] = content
                except OSError:
                    pass
            self._recovery_tick += 1
            if self._recovery_tick >= 10:
                self._recovery_tick = 0
                self._save_recovery_snapshot()
            self.after(3000, save)
        self.after(3000, save)
    def create_project(self):
        name = simpledialog.askstring("Create Project", "Project name:")
        if not name or not name.strip():
            return
        name = name.strip()
        path = os.path.join(TOOLS_ROOT, name)
        if os.path.exists(path):
            messagebox.showerror("Error", "Project already exists!")
            return
        os.makedirs(path)
        main_py = os.path.join(path, "main.py")
        with open(main_py, "w", encoding="utf-8") as f:
            f.write(f'"""{name} — Created with PyForge Pro"""\n\nprint("Hello from {name}!")\n')
        messagebox.showinfo("Success", f"Project '{name}' created!")
        self.open_project_folder(path)
    def toggle_project(self):
        if self.project_path:
            if messagebox.askyesno("Close Project", "Close current project?"):
                self.save_current_file(silent=True)
                self.project_path = None
                self.current_file = None
                self.open_files.clear()
                self.file_tree.delete(*self.file_tree.get_children())
                for w in self.tab_bar.winfo_children():
                    w.destroy()
                self.tab_order = []
                self.editor.delete("1.0", "end")
                self.project_btn.configure(text="Open Project")
                self.project_label.configure(text="No project open")
                self.git_label.configure(text="")
                self._update_breadcrumb()
                self.save_state()
        else:
            path = filedialog.askdirectory(title="Open Project", initialdir=TOOLS_ROOT)
            if path and os.path.isdir(path):
                self.open_project_folder(path)
    def open_project_folder_explorer(self):
        if not self.project_path or not os.path.isdir(self.project_path):
            messagebox.showinfo("No project", "Open or create a project first.")
            return
        path = os.path.normpath(os.path.abspath(self.project_path))
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=False)
            else:
                subprocess.run(["xdg-open", path], check=False)
        except OSError as e:
            messagebox.showerror("Could not open folder", str(e))
    def load_project_files(self):
        self.file_tree.delete(*self.file_tree.get_children())
        if not self.project_path:
            return
        root = os.path.abspath(self.project_path)
        rid = self.file_tree.insert("", "end", text=os.path.basename(root), open=True, values=(root,))
        self._populate_file_tree(rid, root)
        valid = set(self._walk_py_files(self.project_path))
        for k in list(self.open_files.keys()):
            if k not in valid:
                del self.open_files[k]
        for p in valid:
            if p not in self.open_files:
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        self.open_files[p] = f.read()
                except OSError:
                    self.open_files[p] = ""
        self.refresh_git_status()
    def new_file(self):
        if not self.project_path:
            messagebox.showinfo("No Project", "Open or create a project first!")
            return
        name = simpledialog.askstring("New File", "Filename (.py):")
        if name and name.strip():
            if not name.endswith(".py"):
                name += ".py"
            path = os.path.join(self.project_path, name)
            if os.path.exists(path):
                messagebox.showinfo("Exists", "File already exists")
                return
            with open(path, "w", encoding="utf-8") as f:
                f.write(f'"""{name} — Created with PyForge Pro"""\n\n')
            self.open_files[path] = f'"""{name} — Created with PyForge Pro"""\n\n'
            self.load_project_files()
            self.open_file(path)
    def _sync_editor_to_open_files(self):
        if not self.current_file:
            return
        try:
            self.open_files[self.current_file] = self.editor.get("1.0", "end-1c")
        except tk.TclError:
            pass
    def on_tree_select(self, event):
        sel = self.file_tree.selection()
        if not sel:
            return
        vals = self.file_tree.item(sel[0], "values")
        if not vals or not vals[0]:
            return
        path = vals[0]
        if path.endswith(".py") and os.path.isfile(path):
            self.open_file(path)
    def open_file(self, path):
        if path not in self.open_files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.open_files[path] = f.read()
            except OSError:
                return
        self._sync_editor_to_open_files()
        self.current_file = path
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", self.open_files[path])
        self.editor.mark_set("insert", "1.0")
        self.update_highlight_and_lines()
        self.title(f"PyForge Pro — {os.path.basename(path)}")
        self._update_breadcrumb()
        if path not in self.tab_order:
            self.tab_order.append(path)
        self.refresh_file_tabs()
        self.save_state()

    def close_file(self, path):
        if path not in self.open_files:
            return
        was_current = self.current_file == path
        if was_current:
            self._sync_editor_to_open_files()
            self.current_file = None
        del self.open_files[path]
        if path in self.tab_order:
            self.tab_order.remove(path)
        self.breakpoints.pop(path, None)
        if not was_current:
            self.refresh_file_tabs()
            self.save_state()
            return
        if self.tab_order:
            self.open_file(self.tab_order[-1])
        else:
            self.editor.delete("1.0", "end")
            self.title("PyForge Pro")
            self._update_breadcrumb()
            self.update_highlight_and_lines()
            self.refresh_file_tabs()
            self.save_state()

    def save_current_file(self, silent=False):
        if not self.current_file:
            if not silent:
                messagebox.showinfo("No File", "Nothing to save.")
            return False
        try:
            content = self.editor.get("1.0", "end-1c")
            with open(self.current_file, "w", encoding="utf-8") as f:
                f.write(content)
            self.open_files[self.current_file] = content
            if self.settings.get("format_on_save"):
                self._format_current_file(silent=True)
            if not silent:
                messagebox.showinfo("Saved", f"Saved {os.path.basename(self.current_file)}")
            self.save_state()
            return True
        except OSError as e:
            if not silent:
                messagebox.showerror("Save failed", str(e))
            return False
    def _reload_current_from_disk(self):
        if not self.current_file:
            return
        try:
            with open(self.current_file, "r", encoding="utf-8") as f:
                s = f.read()
            self.open_files[self.current_file] = s
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", s)
            self.update_highlight_and_lines()
        except OSError:
            pass
    def _format_current_file(self, silent=True):
        py = self._python_for_subprocess()
        if not py or not self.current_file:
            return
        fmt = self.settings.get("formatter", "ruff")
        kw = {}
        if sys.platform.startswith("win"):
            cf = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if cf:
                kw["creationflags"] = cf
        try:
            if fmt == "black":
                r = subprocess.run(
                    [py, "-m", "black", self.current_file],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    **kw,
                )
            else:
                r = subprocess.run(
                    [py, "-m", "ruff", "format", self.current_file],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    **kw,
                )
            if r.returncode == 0:
                self._reload_current_from_disk()
            elif not silent:
                messagebox.showinfo("Format", (r.stderr or r.stdout or "Format failed.")[:800])
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            if not silent:
                messagebox.showwarning("Format", str(e))
    def _save_recovery_snapshot(self):
        if not self.current_file:
            return
        try:
            content = self.editor.get("1.0", "end-1c")
            rec = os.path.join(_DATA_BASE, "pyforge_recovery")
            os.makedirs(rec, exist_ok=True)
            h = hashlib.sha256(self.current_file.encode("utf-8")).hexdigest()[:10]
            fn = f"{int(time.time())}_{h}.txt"
            with open(os.path.join(rec, fn), "w", encoding="utf-8") as f:
                f.write(f"# path: {self.current_file}\n\n")
                f.write(content)
        except OSError:
            pass
    def _project_tool_dir(self):
        return os.path.join(self.project_path, ".pyforge")
    def _project_run_config_path(self):
        return os.path.join(self._project_tool_dir(), "run.json")
    def load_run_config(self):
        default = {"args": "", "env": "", "cwd": ""}
        if not self.project_path:
            return default
        path = self._project_run_config_path()
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    default.update(json.load(f))
            except (OSError, json.JSONDecodeError):
                pass
        return default
    def save_run_config(self, cfg):
        os.makedirs(self._project_tool_dir(), exist_ok=True)
        with open(self._project_run_config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    def run_current_file(self):
        if not self.current_file:
            messagebox.showwarning("No File", "No file is currently open.")
            return
        self.save_current_file(silent=True)
        file_path = os.path.abspath(self.current_file)
        py = sys.executable
        cfg = self.load_run_config() if self.project_path else {}
        cwd = (cfg.get("cwd") or "").strip() or (self.project_path or os.path.dirname(file_path))
        if not os.path.isdir(cwd):
            cwd = self.project_path or os.path.dirname(file_path)
        args = []
        if cfg.get("args"):
            try:
                args = shlex.split(cfg["args"], posix=not sys.platform.startswith("win"))
            except ValueError:
                args = []
        env = os.environ.copy()
        for line in (cfg.get("env") or "").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
        cmd = [py, file_path] + args
        if sys.platform.startswith("win"):
            subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            try:
                subprocess.Popen(cmd, cwd=cwd, env=env)
            except OSError as e:
                messagebox.showerror("Run failed", str(e))
                return
        self.console.write(f"Launched: {os.path.basename(self.current_file)}  (cwd={cwd})\n")
    def _python_for_subprocess(self):
        """Interpreter that can run ``-m PyInstaller`` (not the PyInstaller bootloader exe when frozen)."""
        if not getattr(sys, "frozen", False):
            return sys.executable
        for name in ("python", "python3"):
            path = shutil.which(name)
            if path:
                return path
        py_launcher = shutil.which("py")
        if py_launcher:
            return py_launcher
        return None
    def _python_module_cmd(self, python_exe, module, *args):
        if sys.platform.startswith("win") and os.path.basename(python_exe).lower() in ("py.exe", "py"):
            return [python_exe, "-3", "-m", module, *args]
        return [python_exe, "-m", module, *args]
    def _pip_module_cmd(self, python_exe, *pip_args):
        if sys.platform.startswith("win") and os.path.basename(python_exe).lower() in ("py.exe", "py"):
            return [python_exe, "-3", "-m", "pip", *pip_args]
        return [python_exe, "-m", "pip", *pip_args]
    def _install_pyinstaller_with_pip(self, python_exe):
        """Install PyInstaller via pip; try normal install then --user. Returns True if usable after."""
        kw = {}
        if sys.platform.startswith("win"):
            cf = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if cf:
                kw["creationflags"] = cf
        attempts = (
            ("install", "--disable-pip-version-check", "pyinstaller"),
            ("install", "--user", "--disable-pip-version-check", "pyinstaller"),
        )
        last_err = ""
        for pip_args in attempts:
            cmd = self._pip_module_cmd(python_exe, *pip_args)
            try:
                r = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=600,
                    **kw,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
                messagebox.showerror("Install failed", str(e))
                return False
            if r.returncode == 0 and self._pyinstaller_available(python_exe):
                return True
            last_err = (r.stderr or "") + (r.stdout or "")
        detail = (last_err or "").strip()
        if len(detail) > 1800:
            detail = "…" + detail[-1800:]
        messagebox.showerror(
            "Could not install PyInstaller",
            "pip could not install PyInstaller. Check your internet connection and try again.\n\n"
            + (detail if detail else "(no output from pip)"),
        )
        return False
    def _ensure_pyinstaller(self, python_exe):
        if self._pyinstaller_available(python_exe):
            return True
        if not messagebox.askyesno(
            "Install PyInstaller?",
            "Building an .exe needs PyInstaller, which is not installed for this Python yet.\n\n"
            "Install PyInstaller now? (requires internet; may take a minute.)",
        ):
            return False
        self.console.write("Installing PyInstaller via pip …\n")
        self.update_idletasks()
        ok = self._install_pyinstaller_with_pip(python_exe)
        if ok:
            self.console.write("PyInstaller is ready — starting build.\n")
        return ok
    def _pyinstaller_available(self, python_exe):
        try:
            kwargs = {}
            if sys.platform.startswith("win"):
                cf = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if cf:
                    kwargs["creationflags"] = cf
            cmd = self._python_module_cmd(python_exe, "PyInstaller", "--version")
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=20,
                **kwargs,
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False
    @staticmethod
    def _pyinstaller_safe_name(name):
        base = os.path.splitext(name)[0]
        safe = re.sub(r'[<>:"/\\|?*]', "_", base)
        safe = safe.strip(" .") or "app"
        return safe[:200]
    def _project_py_files(self):
        if not self.project_path:
            return []
        return list(self._walk_py_files(self.project_path))
    def _pyinstaller_build_cmd(self, python_exe, script_abs, project_dir, name, extra_args=None):
        dist_dir = os.path.join(project_dir, "dist")
        build_dir = os.path.join(project_dir, "build")
        proj = os.path.abspath(project_dir)
        core = [
            "--noconfirm",
            "--onefile",
            "--name",
            name,
            "--distpath",
            dist_dir,
            "--workpath",
            build_dir,
            "--specpath",
            proj,
            "--paths",
            proj,
        ]
        if extra_args:
            core.extend(extra_args)
        core.append(os.path.abspath(script_abs))
        return self._python_module_cmd(python_exe, "PyInstaller", *core)
    def _pyinstaller_popen_kwargs(self):
        """PyInstaller is run with merged streams + closed stdin so it cannot hang waiting for input."""
        kw = {}
        if sys.platform.startswith("win"):
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
            kw["startupinfo"] = si
            cf = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if cf:
                kw["creationflags"] = cf
        return kw

    def _run_pyinstaller_builds(self, python_exe, builds, extra_pyinstaller_args=None):
        dist_hint = os.path.join(builds[0][2], "dist")
        self.console.write(
            f"\n--- PyInstaller (one .exe) — dist folder: {dist_hint} ---\n"
            "(May take several minutes; output appears below as it runs.)\n"
        )
        out_q = queue.Queue()

        def worker():
            try:
                for script, name, project_dir in builds:
                    cmd = self._pyinstaller_build_cmd(
                        python_exe, script, project_dir, name, extra_args=extra_pyinstaller_args
                    )
                    title = f"=== {name}.exe  <-  {os.path.basename(script)} ==="
                    out_q.put(f"\n{title}\n")
                    try:
                        proc = subprocess.Popen(
                            cmd,
                            cwd=project_dir,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            **self._pyinstaller_popen_kwargs(),
                        )
                    except (FileNotFoundError, OSError) as e:
                        out_q.put(f"Error starting PyInstaller: {e}\n")
                        continue
                    try:
                        for chunk in iter(lambda: proc.stdout.read(4096), ""):
                            out_q.put(chunk)
                    finally:
                        if proc.stdout:
                            proc.stdout.close()
                    rc = proc.wait()
                    out_q.put(f"\n(exit code {rc})\n")
            except Exception as e:
                out_q.put(f"\nBuild thread error: {e}\n")
            finally:
                out_q.put(None)

        def pump():
            try:
                while True:
                    try:
                        item = out_q.get_nowait()
                    except queue.Empty:
                        self.after(40, pump)
                        return
                    if item is None:
                        self.console.write("\n--- PyInstaller finished ---\n")
                        return
                    self.console.write(item)
            except Exception as e:
                self.console.write(f"\nConsole update error: {e}\n")
                self.after(40, pump)

        threading.Thread(target=worker, daemon=True).start()
        self.after(0, pump)
    def _show_build_exe_dialog(self, py_paths):
        project_dir = os.path.abspath(self.project_path)
        basenames = [os.path.basename(p) for p in py_paths]
        default_basename = os.path.basename(self.current_file) if self.current_file else basenames[0]
        if default_basename not in basenames:
            default_basename = basenames[0]

        dlg = ctk.CTkToplevel(self)
        dlg.title("Build .exe")
        _configure_ctk_dialog(dlg, transient_parent=self, grab=True)

        name_var = tk.StringVar(value=self._pyinstaller_safe_name(default_basename))
        win_var = tk.BooleanVar(value=False)
        icon_var = tk.StringVar(value="")

        ctk.CTkLabel(
            dlg,
            text="Entry script (your main .py). All other modules in this project that it imports are packed into a single .exe.",
            wraplength=480,
            anchor="w",
            justify="left",
            text_color=Theme.TEXT,
            font=("Segoe UI", 11),
        ).pack(fill="x", padx=20, pady=(18, 6))
        entry_menu = ctk.CTkOptionMenu(dlg, values=basenames, width=400, **_dialog_option_kwargs())
        entry_menu.set(default_basename)
        entry_menu.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(
            dlg,
            text="Output name (without .exe):",
            anchor="w",
            text_color=Theme.TEXT_SECONDARY,
            font=("Segoe UI", 11),
        ).pack(fill="x", padx=20, pady=(0, 4))
        name_entry = ctk.CTkEntry(dlg, textvariable=name_var, width=400, **_dialog_entry_kwargs())
        name_entry.pack(fill="x", padx=20, pady=(0, 8))

        ctk.CTkCheckBox(
            dlg,
            text="Windowed app (no console) — PyInstaller --windowed",
            variable=win_var,
            text_color=Theme.TEXT_SECONDARY,
            fg_color=Theme.RAISED,
            hover_color=Theme.HOVER,
        ).pack(anchor="w", padx=20, pady=(4, 4))
        icon_row = ctk.CTkFrame(dlg, fg_color="transparent")
        icon_row.pack(fill="x", padx=20, pady=(0, 10))

        def browse_icon():
            p = filedialog.askopenfilename(filetypes=[("Icon", "*.ico"), ("All files", "*.*")])
            if p:
                icon_var.set(p)

        ctk.CTkEntry(
            icon_row,
            placeholder_text="Optional .ico for --icon",
            textvariable=icon_var,
            width=300,
            **_dialog_entry_kwargs(),
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            icon_row,
            text="Browse…",
            width=90,
            corner_radius=Theme.RADIUS,
            command=browse_icon,
            fg_color=Theme.BTN_SECONDARY,
            hover_color=Theme.BTN_SECONDARY_HOVER,
        ).pack(side="right")

        def on_entry_change(choice):
            name_var.set(self._pyinstaller_safe_name(choice))

        entry_menu.configure(command=on_entry_change)

        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 18))

        def start_build():
            self.save_current_file(silent=True)
            main_basename = entry_menu.get()
            raw_main_name = name_var.get().strip() or main_basename
            main_name = self._pyinstaller_safe_name(raw_main_name)
            if not main_name:
                messagebox.showwarning("Build", "Enter a valid main output name.")
                return
            extra_pi = []
            if win_var.get():
                extra_pi.append("--windowed")
            ip = icon_var.get().strip()
            if ip and os.path.isfile(ip):
                extra_pi.extend(["--icon", os.path.abspath(ip)])
            builds = [(os.path.join(project_dir, main_basename), main_name, project_dir)]
            python_exe = self._python_for_subprocess()
            if not python_exe:
                messagebox.showerror(
                    "Python not found",
                    "PyForge is running as a packaged .exe, so it cannot run PyInstaller itself.\n\n"
                    "Install Python 3 and add it to PATH, or run PyForge from source:\n"
                    "  python PyForge.py\n\n"
                    "Then install PyInstaller:\n"
                    "  pip install pyinstaller",
                )
                return
            if not self._ensure_pyinstaller(python_exe):
                return
            try:
                os.makedirs(os.path.join(project_dir, "build"), exist_ok=True)
                os.makedirs(os.path.join(project_dir, "dist"), exist_ok=True)
            except OSError as e:
                messagebox.showerror("Build", f"Could not create build folders:\n{e}")
                return
            dlg.destroy()
            self._run_pyinstaller_builds(python_exe, builds, extra_pyinstaller_args=extra_pi or None)

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            command=dlg.destroy,
            fg_color=Theme.BTN_SECONDARY,
            hover_color=Theme.BTN_SECONDARY_HOVER,
            corner_radius=Theme.RADIUS,
            width=110,
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            btn_frame,
            text="Build",
            command=start_build,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            corner_radius=Theme.RADIUS,
            width=110,
        ).pack(side="right")
        _fit_ctk_dialog_geometry(dlg, min_w=520, min_h=480, margin_w=24, margin_h=24)
        dlg.after(80, lambda: name_entry.focus_set())
    def build_exe(self):
        if not self.project_path:
            messagebox.showinfo("No Project", "Open a project first.")
            return
        py_paths = self._project_py_files()
        if not py_paths:
            messagebox.showwarning("No Python files", "Add at least one .py file to the project.")
            return
        self._show_build_exe_dialog(py_paths)
    def show_search(self):
        self.search_frame.grid()
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")
        self.search_entry.icursor("end")
    def hide_search(self):
        self.search_frame.grid_remove()
    def toggle_search(self):
        if self.search_frame.winfo_ismapped():
            self.hide_search()
        else:
            self.show_search()
    def find_next(self):
        term = self.search_entry.get()
        if not term:
            return
        start = self.editor.index("insert +1c")
        pos = self.editor.search(term, start, stopindex="end", forwards=True, regexp=False, nocase=not self.match_case_var.get())
        if not pos:
            pos = self.editor.search(term, "1.0", stopindex="insert", forwards=True, regexp=False, nocase=not self.match_case_var.get())
        if pos:
            end = f"{pos}+{len(term)}c"
            self.editor.tag_remove("sel", "1.0", "end")
            self.editor.tag_add("sel", pos, end)
            self.editor.mark_set("insert", end)
            self.editor.see(pos)
        else:
            messagebox.showinfo("Find", "No more matches found.")
    def find_previous(self):
        term = self.search_entry.get()
        if not term:
            return
        start = self.editor.index("insert")
        pos = self.editor.search(term, "1.0", stopindex=start, forwards=False, regexp=False, nocase=not self.match_case_var.get())
        if not pos:
            pos = self.editor.search(term, "end", stopindex="insert", forwards=False, regexp=False, nocase=not self.match_case_var.get())
        if pos:
            end = f"{pos}+{len(term)}c"
            self.editor.tag_remove("sel", "1.0", "end")
            self.editor.tag_add("sel", pos, end)
            self.editor.mark_set("insert", pos)
            self.editor.see(pos)
        else:
            messagebox.showinfo("Find", "No more matches found.")
    def toggle_breakpoint(self, event=None):
        if not self.current_file:
            return "break"
        try:
            line = int(self.editor.index("insert").split(".")[0])
        except (tk.TclError, ValueError):
            return "break"
        s = self.breakpoints.setdefault(self.current_file, set())
        if line in s:
            s.remove(line)
            self.console.write(f"Breakpoint removed line {line}\n")
        else:
            s.add(line)
            self.console.write(f"Breakpoint set line {line}\n")
        return "break"
    def start_embedded_terminal(self):
        if not self.project_path:
            messagebox.showinfo("Project", "Open a project first.")
            return
        self.stop_embedded_terminal()
        self._pty_q = queue.Queue()
        self._pty_session = PtySession(self.project_path, self._pty_q)
        if not self._pty_session.start():
            return
        self.term_out.delete("1.0", "end")
        self.term_in.configure(placeholder_text="Shell input (Enter)")
        self.after(100, self._pty_pump)
    def stop_embedded_terminal(self):
        if getattr(self, "_pty_session", None):
            self._pty_session.close()
            self._pty_session = None
    def _pty_pump(self):
        q = getattr(self, "_pty_q", None)
        if not q:
            return
        try:
            while True:
                try:
                    item = q.get_nowait()
                except queue.Empty:
                    self.after(80, self._pty_pump)
                    return
                if item is None:
                    self.term_out.insert("end", "\n[Terminal closed]\n")
                    return
                self.term_out.insert("end", item)
                self.term_out.see("end")
        except tk.TclError:
            self.after(80, self._pty_pump)
    def _terminal_send_line(self, event=None):
        if not getattr(self, "_pty_session", None):
            return
        line = self.term_in.get()
        self.term_in.delete(0, "end")
        self._pty_session.write(line + "\n")
    def start_visual_debugger(self):
        if not self.current_file:
            messagebox.showwarning("Debug", "No file open.")
            return
        self.save_current_file(silent=True)
        if self._pdb_session:
            self._pdb_session.close()
            self._pdb_session = None
        self._pdb_q = queue.Queue()
        self._pdb_session = PdbPipeSession(
            os.path.abspath(self.current_file), self.project_path, self._pdb_q
        )
        if not self._pdb_session.start():
            return
        self.dbg_out.delete("1.0", "end")
        self.bottom_tabs.set("Debug")
        self.after(100, self._pdb_pump)
    def _pdb_pump(self):
        q = getattr(self, "_pdb_q", None)
        if not q:
            return
        try:
            while True:
                try:
                    item = q.get_nowait()
                except queue.Empty:
                    self.after(80, self._pdb_pump)
                    return
                if item is None:
                    self.dbg_out.insert("end", "\n[pdb process ended]\n")
                    return
                self.dbg_out.insert("end", item)
                self.dbg_out.see("end")
        except tk.TclError:
            self.after(80, self._pdb_pump)
    def _pdb_send(self, cmd):
        if self._pdb_session:
            self._pdb_session.send(cmd)
    def _pdb_send_entry(self):
        if self._pdb_session:
            self._pdb_session.send(self.dbg_in.get())
            self.dbg_in.delete(0, "end")
    def run_pylint_ui(self):
        import json

        if not self.project_path:
            messagebox.showinfo("Project", "Open a project first.")
            return
        py = self._python_for_subprocess()
        if not py:
            return
        for i in self.pylint_tree.get_children():
            self.pylint_tree.delete(i)
        kw = {}
        if sys.platform.startswith("win"):
            cf = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if cf:
                kw["creationflags"] = cf
        try:
            r = subprocess.run(
                [py, "-m", "pylint", "--output-format=json", "."],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=600,
                **kw,
            )
        except Exception as e:
            messagebox.showerror("pylint", str(e))
            return
        try:
            data = json.loads(r.stdout or "[]")
        except json.JSONDecodeError:
            self.console.write("pylint: could not parse JSON (is pylint installed?)\n")
            return
        for i, item in enumerate(data):
            msg = item.get("message", "")
            path = item.get("path", "")
            line = item.get("line", "")
            try:
                rel = os.path.relpath(path, self.project_path)
            except ValueError:
                rel = path
            self.pylint_tree.insert("", "end", iid=f"pl{i}", values=(rel, line, msg))
        self.bottom_tabs.set("Pylint")
        self.console.write(f"\npylint: {len(data)} message(s)\n")
    def _pylint_goto(self, event):
        sel = self.pylint_tree.selection()
        if not sel:
            return
        vals = self.pylint_tree.item(sel[0], "values")
        if len(vals) < 2:
            return
        rel, line = vals[0], vals[1]
        path = os.path.normpath(os.path.join(self.project_path, rel))
        if not os.path.isfile(path):
            return
        try:
            ln = int(line)
        except (TypeError, ValueError):
            return
        self.open_file(path)
        self.editor.mark_set("insert", f"{ln}.0")
        self.editor.see(f"{ln}.0")
        self.update_highlight_and_lines()
    def pip_install_editable(self):
        if not self.project_path:
            messagebox.showinfo("Project", "Open a project first.")
            return
        py = self._python_for_subprocess()
        if not py:
            return
        self._async_console_cmd([py, "-m", "pip", "install", "-e", "."], title="pip install -e .")
    def rename_symbol_dialog(self):
        if not self.project_path:
            messagebox.showinfo("Project", "Open a project first.")
            return
        from pyforge_rename import rename_symbol_project

        old = _ctk_prompt_string(self, "Rename symbol", "Current name:")
        if not old or not old.strip():
            return
        new = _ctk_prompt_string(self, "Rename symbol", "New name:")
        if new is None or not new.strip():
            return
        old, new = old.strip(), new.strip()
        fc, nr, msg = rename_symbol_project(self.project_path, old, new)
        messagebox.showinfo("Rename symbol", msg)
        self.load_project_files()
        if self.current_file:
            self.open_file(self.current_file)
    def _widget_under(self, w, ancestor):
        while w is not None:
            if w == ancestor:
                return True
            w = getattr(w, "master", None)
        return False

    def _cancel_menu_hover_timer(self):
        aid = getattr(self, "_menu_hover_after_id", None)
        if aid is not None:
            try:
                self.after_cancel(aid)
            except (tk.TclError, ValueError):
                pass
            self._menu_hover_after_id = None
        self._menu_pending_geom_anchor = None

    def _cancel_menu_leave_debounce(self):
        lid = getattr(self, "_menu_leave_after_id", None)
        if lid is not None:
            try:
                self.after_cancel(lid)
            except (tk.TclError, ValueError):
                pass
            self._menu_leave_after_id = None

    def _cancel_menu_pointer_poll(self):
        aid = getattr(self, "_menu_poll_after_id", None)
        if aid is not None:
            try:
                self.after_cancel(aid)
            except (tk.TclError, ValueError):
                pass
            self._menu_poll_after_id = None

    def _menu_poll_pointer(self):
        """While a dropdown is open, poll global pointer — bar <Motion> does not run over the editor."""
        self._menu_poll_after_id = None
        if not getattr(self, "_menu_popup", None):
            return
        try:
            x, y = self.winfo_pointerxy()
        except tk.TclError:
            self._menu_poll_after_id = self.after(40, self._menu_poll_pointer)
            return
        if not self._menu_point_in_menu_regions(x, y):
            self._destroy_menu_popup()
            return
        self._menu_poll_after_id = self.after(40, self._menu_poll_pointer)

    def _menu_start_pointer_poll(self):
        if getattr(self, "_menu_popup", None):
            self._menu_poll_pointer()

    def _menu_pointer_in_menu_ui(self):
        try:
            x, y = self.winfo_pointerxy()
        except tk.TclError:
            return False
        return self._menu_point_in_menu_regions(x, y)

    def _destroy_menu_popup(self):
        mid = getattr(self, "_menu_motion_idle_id", None)
        if mid is not None:
            try:
                self.after_cancel(mid)
            except (tk.TclError, ValueError):
                pass
            self._menu_motion_idle_id = None
        self._cancel_menu_pointer_poll()
        self._cancel_menu_hover_timer()
        self._cancel_menu_leave_debounce()
        self._menu_pending_geom_anchor = None
        self._menu_motion_anchor = None
        self._menu_popup_anchor = None
        try:
            if getattr(self, "_menu_popup", None):
                self._menu_popup.destroy()
        except tk.TclError:
            pass
        self._menu_popup = None

    def _menu_hit_test_pointer(self, x, y):
        """Screen-space hit test for menu title buttons (fresh geometry each run; cheap vs per-pixel Motion)."""
        items = getattr(self, "_menu_items", None)
        if not items:
            return
        for btn, entries in items:
            try:
                bx = int(btn.winfo_rootx())
                by = int(btn.winfo_rooty())
                bw = max(int(btn.winfo_width()), 1)
                bh = max(int(btn.winfo_height()), 1)
            except (tk.TclError, ValueError):
                continue
            if bx <= x <= bx + bw and by <= y <= by + bh:
                if getattr(self, "_menu_motion_anchor", None) is btn:
                    return
                self._menu_hover_enter(btn, entries)
                return
        self._menu_motion_anchor = None
        if getattr(self, "_menu_popup", None) and not self._menu_point_in_menu_regions(x, y):
            self._destroy_menu_popup()

    def _menu_schedule_motion_hit_test(self, event=None):
        """Coalesce <Motion> storms: one idle callback reads pointer and hit-tests (cached rects)."""
        if getattr(self, "_menu_motion_idle_id", None) is not None:
            return

        def run():
            self._menu_motion_idle_id = None
            try:
                x, y = self.winfo_pointerxy()
            except tk.TclError:
                return
            self._menu_hit_test_pointer(x, y)

        self._menu_motion_idle_id = self.after_idle(run)

    def _menu_hover_enter(self, geom_anchor, entries):
        # Sync hit-test state so <Enter> then coalesced <Motion> does not reopen / toggle wrongly.
        self._menu_motion_anchor = geom_anchor
        self._cancel_menu_leave_debounce()
        self._cancel_menu_hover_timer()
        if getattr(self, "_menu_popup", None):
            self._menu_open(geom_anchor, entries, allow_toggle=False)
            return
        if Theme.MENU_HOVER_DELAY_MS <= 0:
            self._menu_open(geom_anchor, entries, allow_toggle=False)
            return

        def fire():
            self._menu_hover_after_id = None
            self._menu_pending_geom_anchor = None
            self._menu_open(geom_anchor, entries, allow_toggle=False)

        self._menu_pending_geom_anchor = geom_anchor
        self._menu_hover_after_id = self.after(Theme.MENU_HOVER_DELAY_MS, fire)

    def _menu_hover_leave(self):
        self._cancel_menu_leave_debounce()

        def deferred_leave():
            self._menu_leave_after_id = None
            if self._menu_pointer_in_menu_ui():
                return
            self._cancel_menu_hover_timer()
            self._destroy_menu_popup()

        self._menu_leave_after_id = self.after(Theme.MENU_LEAVE_DEBOUNCE_MS, deferred_leave)

    def _maybe_dismiss_menu_global(self, event):
        pop = getattr(self, "_menu_popup", None)
        if not pop:
            return
        try:
            x, y = event.x_root, event.y_root
        except tk.TclError:
            return
        try:
            w = event.widget
            if self._widget_under(w, pop):
                return
            mb = getattr(self, "_menu_bar", None)
            if mb and self._widget_under(w, mb):
                return
        except (tk.TclError, AttributeError):
            pass
        if self._menu_point_in_menu_regions(x, y):
            return
        self._destroy_menu_popup()

    def _menu_point_in_menu_regions(self, x, y):
        """Same geometry as _menu_pointer_in_menu_ui but for explicit x,y (e.g. click)."""
        pop = getattr(self, "_menu_popup", None)
        if pop:
            try:
                px, py = pop.winfo_rootx(), pop.winfo_rooty()
                pw, ph = pop.winfo_width(), pop.winfo_height()
                if px <= x <= px + max(pw, 1) and py <= y <= py + max(ph, 1):
                    return True
            except tk.TclError:
                pass
        mb = getattr(self, "_menu_bar", None)
        if mb:
            try:
                x0, y0 = mb.winfo_rootx(), mb.winfo_rooty()
                bw, bh = mb.winfo_width(), mb.winfo_height()
                bh = bh + Theme.MENU_BRIDGE_BELOW_PX
                if x0 <= x <= x0 + max(bw, 1) and y0 <= y <= y0 + max(bh, 1):
                    return True
            except tk.TclError:
                pass
        return False

    def _menu_run(self, cmd):
        self._destroy_menu_popup()
        cmd()

    def _menu_popup_dimensions(self, entries):
        """Size from label text and row count — avoids CTk winfo_req* inflation and a fixed min width."""
        labels = [item[0] for item in entries if item is not None]
        f = tkfont.Font(family="Segoe UI", size=11, root=self)
        text_w = max((f.measure(t) for t in labels), default=0)
        # Button padx 8, inner pack padx 4, frame border ~2, small margin
        req_w = text_w + 44
        req_w = max(72, min(req_w, 1200))

        h = 4  # inner pack pady 2 + 2
        for item in entries:
            if item is None:
                h += 9  # separator height 1 + pady 4 + 4
            else:
                h += 32  # button height 30 + pady 1 + 1
        req_h = max(48, min(h, 2000))
        return req_w, req_h

    def _menu_open(self, anchor, entries, *, allow_toggle=False):
        """Hover uses allow_toggle=False (re-hover same title does not close). Click uses allow_toggle=True."""
        pop = getattr(self, "_menu_popup", None)
        cur = getattr(self, "_menu_popup_anchor", None)
        if pop is not None and cur == anchor:
            if allow_toggle:
                self._destroy_menu_popup()
            return
        # Re-entrancy: update_idletasks / events can call _menu_open again; nested call destroys this popup.
        if getattr(self, "_menu_open_busy", False):
            return
        self._menu_open_busy = True
        try:
            self._destroy_menu_popup()
            self._menu_popup_anchor = anchor
            top = ctk.CTkToplevel(self)
            self._menu_popup = top
            top.overrideredirect(True)
            top.attributes("-topmost", True)
            top.configure(fg_color=Theme.RAISED)
            top.resizable(False, False)
            inner = ctk.CTkFrame(
                top,
                fg_color=Theme.RAISED,
                corner_radius=Theme.RADIUS,
                border_width=1,
                border_color=Theme.BORDER,
            )
            inner.pack(fill="both", expand=True, padx=2, pady=2)
            for item in entries:
                if item is None:
                    ctk.CTkFrame(inner, height=1, fg_color=Theme.BORDER_SUBTLE).pack(fill="x", padx=8, pady=4)
                    continue
                label, cmd = item
                ctk.CTkButton(
                    inner,
                    text=label,
                    anchor="w",
                    height=30,
                    font=("Segoe UI", 11),
                    fg_color="transparent",
                    hover_color=Theme.HOVER,
                    text_color=Theme.TEXT,
                    corner_radius=4,
                    command=lambda c=cmd: self._menu_run(c),
                ).pack(fill="x", padx=4, pady=1)
            top.bind("<Escape>", lambda e: self._destroy_menu_popup())
            # Do not call top.update_idletasks() here — it can process idle callbacks and re-enter _menu_open,
            # destroying `top` while we still use `inner` (TclError: bad window path name).
            x = anchor.winfo_rootx()
            y = anchor.winfo_rooty() + anchor.winfo_height() - Theme.MENU_POPUP_OVERLAP_PX
            if self._menu_popup is not top:
                return
            req_w, req_h = self._menu_popup_dimensions(entries)
            if self._menu_popup is not top:
                return
            try:
                top.geometry(f"{req_w}x{req_h}+{x}+{y}")
            except tk.TclError:
                return
            top.bind("<Enter>", lambda e: self._cancel_menu_leave_debounce())
            top.bind("<Leave>", lambda e: self._menu_hover_leave())
            self.after_idle(self._menu_start_pointer_poll)
            if not getattr(self, "_menu_dismiss_bound", False):
                self.bind_all("<Button-1>", self._maybe_dismiss_menu_global, add="+")
                self._menu_dismiss_bound = True
        finally:
            self._menu_open_busy = False

    def _build_ctk_menubar(self):
        self._menu_popup = None
        self._menu_popup_anchor = None
        self._menu_hover_after_id = None
        self._menu_leave_after_id = None
        self._menu_pending_geom_anchor = None
        self._menu_motion_anchor = None
        self._menu_motion_idle_id = None
        self._menu_poll_after_id = None
        self._menu_open_busy = False
        self._menu_items = []
        self._menu_bar = ctk.CTkFrame(
            self,
            height=36,
            corner_radius=0,
            fg_color=Theme.RAISED,
            border_width=0,
        )
        self._menu_bar.grid(row=0, column=0, columnspan=3, sticky="ew")
        self._menu_bar.grid_propagate(False)
        inner = ctk.CTkFrame(self._menu_bar, fg_color="transparent")
        inner.pack(side="left", padx=(6, 12), pady=4)
        btn_kw = {
            "height": 28,
            "corner_radius": 4,
            "fg_color": "transparent",
            "hover_color": Theme.HOVER,
            "text_color": Theme.TEXT,
            "font": ("Segoe UI", 11),
        }

        def add_btn(label, entries):
            wrap = ctk.CTkFrame(inner, fg_color="transparent")
            wrap.pack(side="left", padx=1)
            bw = max(52, 8 * len(label) + 20)
            b = ctk.CTkButton(wrap, text=label, width=bw, **btn_kw)
            b.pack(fill="both", expand=True)
            b.configure(command=lambda a=b, e=entries: self._menu_open(a, e, allow_toggle=True))
            self._menu_items.append((b, entries))
            # Bind on the button: the button fully covers the wrap, so <Enter> on the parent never fires.
            b.bind("<Enter>", lambda e, ga=b, ent=entries: self._menu_hover_enter(ga, ent))
            b.bind("<Leave>", lambda e: self._menu_hover_leave())

        add_btn(
            "File",
            [
                ("Settings…", self.show_settings_dialog),
                None,
                ("Exit", self.on_closing),
            ],
        )
        add_btn("Navigate", [("Go to Line…", self.go_to_line)])
        add_btn("View", [("Toggle breakpoint (line)", self.toggle_breakpoint)])
        add_btn(
            "Search",
            [
                ("Find in Project…", self.find_in_project),
                ("Replace in Project…", self.replace_in_project),
                ("Rename symbol (AST/rope)…", self.rename_symbol_dialog),
            ],
        )
        add_btn("Edit", [("Format Document", self.format_document)])
        add_btn(
            "Run",
            [
                ("Run configuration…", self.show_run_config_dialog),
                ("Debug in external console (pdb)", self.run_debug_pdb),
                ("Visual debugger (pdb pipes)", self.start_visual_debugger),
                None,
                ("Run tests (pytest)", self.run_pytest),
                ("Lint project (ruff)", self.run_lint),
                ("Install requirements.txt", self.install_requirements),
                ("pip install -e . (editable)", self.pip_install_editable),
            ],
        )
        add_btn(
            "Tools",
            [
                ("Shell command…", self.shell_command_dialog),
                ("Zip dist folder", self.zip_dist_folder),
                ("Refresh Git status", self.refresh_git_status),
            ],
        )
        # Gaps / padding only: motion on bar + inner (not each button — avoids per-pixel storms on titles).
        # Coalesced via after_idle in _menu_schedule_motion_hit_test.
        self._menu_bar.bind("<Motion>", self._menu_schedule_motion_hit_test)
        inner.bind("<Motion>", self._menu_schedule_motion_hit_test)
    def show_settings_dialog(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Settings")
        _configure_ctk_dialog(dlg, transient_parent=self, grab=True)
        app_mode = tk.StringVar(value=self.settings.get("appearance", "dark"))
        fos = tk.BooleanVar(value=self.settings.get("format_on_save", False))
        fmt = tk.StringVar(value=self.settings.get("formatter", "ruff"))
        ctk.CTkLabel(
            dlg, text="Editor font size (9–22)", text_color=Theme.TEXT, font=("Segoe UI", 11)
        ).pack(fill="x", anchor="w", padx=20, pady=(20, 4))
        fs_e = ctk.CTkEntry(dlg, width=120, **_dialog_entry_kwargs())
        fs_e.insert(0, str(int(self.settings.get("font_size", 13))))
        fs_e.pack(anchor="w", padx=20)
        ctk.CTkLabel(dlg, text="Appearance", text_color=Theme.TEXT_SECONDARY, font=("Segoe UI", 11)).pack(
            fill="x", anchor="w", padx=20, pady=(12, 4)
        )
        ctk.CTkOptionMenu(
            dlg, values=["dark", "light", "system"], variable=app_mode, width=200, **_dialog_option_kwargs()
        ).pack(padx=20, anchor="w")
        ctk.CTkCheckBox(
            dlg,
            text="Format on save",
            variable=fos,
            text_color=Theme.TEXT_SECONDARY,
            fg_color=Theme.RAISED,
            hover_color=Theme.HOVER,
        ).pack(anchor="w", padx=20, pady=(12, 4))
        ctk.CTkLabel(
            dlg, text="Formatter (pip install ruff or black)", text_color=Theme.TEXT_SECONDARY, font=("Segoe UI", 11)
        ).pack(fill="x", anchor="w", padx=20, pady=(8, 4))
        ctk.CTkOptionMenu(dlg, values=["ruff", "black"], variable=fmt, width=200, **_dialog_option_kwargs()).pack(
            padx=20, anchor="w"
        )
        ctk.CTkLabel(
            dlg,
            text=f"Portable mode: {'on' if _is_portable_mode() else 'off'} (portable.txt next to PyForge.py or PYFORGE_PORTABLE=1)",
            text_color=Theme.TEXT_MUTED,
            wraplength=400,
            font=("Segoe UI", 11),
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=20, pady=(12, 8))

        def apply_save():
            try:
                fz = int(fs_e.get().strip())
            except ValueError:
                fz = 13
            self.settings["font_size"] = max(9, min(22, fz))
            self.settings["appearance"] = app_mode.get()
            self.settings["format_on_save"] = fos.get()
            self.settings["formatter"] = fmt.get()
            self.save_settings()
            ctk.set_appearance_mode(self.settings["appearance"])
            self.editor.set_font_size(self.settings["font_size"])
            self.line_numbers.configure(font=("Consolas", self.settings["font_size"]))
            dlg.destroy()

        row = _ctk_dialog_button_row(dlg, pady=20)
        ctk.CTkButton(
            row,
            text="Cancel",
            command=dlg.destroy,
            fg_color=Theme.BTN_SECONDARY,
            hover_color=Theme.BTN_SECONDARY_HOVER,
            corner_radius=Theme.RADIUS,
            width=100,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row,
            text="OK",
            command=apply_save,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            corner_radius=Theme.RADIUS,
            width=100,
        ).pack(side="left")
        _fit_ctk_dialog_geometry(dlg, min_w=440, min_h=380, margin_w=24, margin_h=24)
    def go_to_line(self):
        n = _ctk_prompt_integer(self, "Go to line", "Line number:", minvalue=1)
        if n is None:
            return
        self.editor.mark_set("insert", f"{n}.0")
        self.editor.see(f"{n}.0")
        self.update_highlight_and_lines()
    def find_in_project(self):
        if not self.project_path:
            messagebox.showinfo("Project", "Open a project first.")
            return
        term = _ctk_prompt_string(self, "Find in project", "Search for:")
        if not term:
            return
        matches = []
        for p in self._walk_py_files(self.project_path):
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if term in line:
                            matches.append((p, i, line.rstrip()[:240]))
            except OSError:
                pass
        res = ctk.CTkToplevel(self)
        res.title(f"Matches ({len(matches)})")
        _configure_ctk_dialog(res, transient_parent=self, grab=False, resizable=(True, True))
        res.minsize(640, 320)
        ctk.CTkLabel(
            res,
            text="Double-click a row to open the file at that line.",
            text_color=Theme.TEXT_SECONDARY,
            font=("Segoe UI", 11),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 6))
        wrap = ctk.CTkFrame(res, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        lb = tk.Listbox(
            wrap,
            bg=Theme.PANEL,
            fg=Theme.TEXT,
            selectbackground=Theme.ACCENT,
            selectforeground=Theme.TEXT,
            font=("Consolas", 11),
            height=16,
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
        )
        sb = ctk.CTkScrollbar(wrap, command=lb.yview, orientation="vertical", **_ctk_scrollbar_kwargs())
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        show = matches[:500]
        for p, ln, snippet in show:
            rel = os.path.relpath(p, self.project_path)
            lb.insert("end", f"{rel}:{ln}: {snippet}")

        def on_go(event=None):
            sel = lb.curselection()
            if not sel:
                return
            path, line_no, _ = show[sel[0]]
            if path in self.open_files or os.path.isfile(path):
                self.open_file(path)
                self.editor.mark_set("insert", f"{line_no}.0")
                self.editor.see(f"{line_no}.0")
                self.update_highlight_and_lines()
                res.destroy()

        lb.bind("<Double-Button-1>", on_go)
        _fit_ctk_dialog_geometry(res, min_w=720, min_h=400, margin_w=28, margin_h=28)
    def replace_in_project(self):
        if not self.project_path:
            messagebox.showinfo("Project", "Open a project first.")
            return
        old = _ctk_prompt_string(self, "Replace in project", "Find:")
        if old is None or old == "":
            return
        new = _ctk_prompt_string(self, "Replace in project", "Replace with:")
        if new is None:
            return
        if not _ctk_ask_yes_no(self, "Confirm", "Replace all occurrences of the text in all .py files?"):
            return
        nfiles = 0
        nrep = 0
        for p in self._walk_py_files(self.project_path):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    s = f.read()
            except OSError:
                continue
            c = s.count(old)
            if c:
                ns = s.replace(old, new)
                try:
                    with open(p, "w", encoding="utf-8") as f:
                        f.write(ns)
                except OSError:
                    continue
                nfiles += 1
                nrep += c
                if p in self.open_files:
                    self.open_files[p] = ns
        if self.current_file:
            self.open_file(self.current_file)
        self.load_project_files()
        messagebox.showinfo("Replace", f"Updated {nfiles} file(s), {nrep} replacement(s).")
    def format_document(self):
        if not self.current_file:
            messagebox.showinfo("Format", "No file open.")
            return
        self.save_current_file(silent=True)
        self._format_current_file(silent=False)
    def show_run_config_dialog(self):
        if not self.project_path:
            messagebox.showinfo("Project", "Open a project first.")
            return
        cfg = self.load_run_config()
        dlg = ctk.CTkToplevel(self)
        dlg.title("Run configuration")
        _configure_ctk_dialog(dlg, transient_parent=self, grab=True)
        ctk.CTkLabel(
            dlg,
            text="Extra arguments (passed to Python after script path):",
            wraplength=480,
            text_color=Theme.TEXT,
            font=("Segoe UI", 11),
            anchor="w",
            justify="left",
        ).pack(fill="x", anchor="w", padx=20, pady=(16, 4))
        args_e = ctk.CTkEntry(dlg, width=460, **_dialog_entry_kwargs())
        args_e.insert(0, cfg.get("args", ""))
        args_e.pack(padx=20, fill="x")
        ctk.CTkLabel(
            dlg,
            text="Environment (KEY=value per line):",
            anchor="w",
            text_color=Theme.TEXT_SECONDARY,
            font=("Segoe UI", 11),
        ).pack(fill="x", padx=20, pady=(12, 4), anchor="w")
        env_t = ctk.CTkTextbox(
            dlg,
            height=120,
            width=460,
            fg_color=Theme.ENTRY_BG,
            border_color=Theme.BORDER,
            text_color=Theme.TEXT,
            border_width=1,
            corner_radius=Theme.RADIUS,
            scrollbar_button_color=Theme.BTN_SECONDARY,
            scrollbar_button_hover_color=Theme.BTN_SECONDARY_HOVER,
        )
        env_t.insert("1.0", cfg.get("env", ""))
        env_t.pack(padx=20, fill="x")
        ctk.CTkLabel(
            dlg,
            text="Working directory (blank = project root):",
            anchor="w",
            text_color=Theme.TEXT_SECONDARY,
            font=("Segoe UI", 11),
        ).pack(fill="x", padx=20, pady=(12, 4), anchor="w")
        cwd_e = ctk.CTkEntry(dlg, width=460, **_dialog_entry_kwargs())
        cwd_e.insert(0, cfg.get("cwd", ""))
        cwd_e.pack(padx=20, fill="x")

        def save_cfg():
            self.save_run_config(
                {"args": args_e.get(), "env": env_t.get("1.0", "end-1c"), "cwd": cwd_e.get().strip()}
            )
            dlg.destroy()

        row = _ctk_dialog_button_row(dlg, pady=16)
        ctk.CTkButton(
            row,
            text="Cancel",
            command=dlg.destroy,
            fg_color=Theme.BTN_SECONDARY,
            hover_color=Theme.BTN_SECONDARY_HOVER,
            corner_radius=Theme.RADIUS,
            width=100,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row,
            text="Save",
            command=save_cfg,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            corner_radius=Theme.RADIUS,
            width=100,
        ).pack(side="left")
        _fit_ctk_dialog_geometry(dlg, min_w=520, min_h=420, margin_w=24, margin_h=24)
    def run_debug_pdb(self):
        if not self.current_file:
            messagebox.showwarning("Debug", "No file open.")
            return
        self.save_current_file(silent=True)
        py = sys.executable
        fp = os.path.abspath(self.current_file)
        cwd = self.project_path or os.path.dirname(fp)
        if sys.platform.startswith("win"):
            subprocess.Popen(
                ["cmd", "/k", py, "-m", "pdb", fp],
                cwd=cwd,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            subprocess.Popen([py, "-m", "pdb", fp], cwd=cwd)
        self.console.write(f"pdb: {os.path.basename(fp)}\n")
    def _async_console_cmd(self, cmd, cwd=None, env=None, title=""):
        if cwd is None:
            cwd = self.project_path
        self.console.write(f"\n--- {title or ' '.join(cmd)} ---\n")
        out_q = queue.Queue()

        def worker():
            try:
                kw = {}
                if sys.platform.startswith("win"):
                    cf = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    if cf:
                        kw["creationflags"] = cf
                proc = subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    **kw,
                )
                for chunk in iter(lambda: proc.stdout.read(4096), ""):
                    out_q.put(chunk)
                if proc.stdout:
                    proc.stdout.close()
                rc = proc.wait()
                out_q.put(f"\n(exit {rc})\n")
            except Exception as e:
                out_q.put(str(e) + "\n")
            finally:
                out_q.put(None)

        def pump():
            try:
                while True:
                    try:
                        item = out_q.get_nowait()
                    except queue.Empty:
                        self.after(40, pump)
                        return
                    if item is None:
                        self.console.write("\n--- done ---\n")
                        return
                    self.console.write(item)
            except Exception as e:
                self.console.write(str(e) + "\n")
                self.after(40, pump)

        threading.Thread(target=worker, daemon=True).start()
        self.after(0, pump)
    def run_pytest(self):
        if not self.project_path:
            messagebox.showinfo("Project", "Open a project first.")
            return
        py = self._python_for_subprocess()
        if not py:
            messagebox.showerror("Python", "Python interpreter not found.")
            return
        self._async_console_cmd([py, "-m", "pytest", "-q"], title="pytest")
    def run_lint(self):
        if not self.project_path:
            messagebox.showinfo("Project", "Open a project first.")
            return
        py = self._python_for_subprocess()
        if not py:
            return
        self._async_console_cmd([py, "-m", "ruff", "check", "."], title="ruff check")
    def install_requirements(self):
        if not self.project_path:
            messagebox.showinfo("Project", "Open a project first.")
            return
        req = os.path.join(self.project_path, "requirements.txt")
        if not os.path.isfile(req):
            messagebox.showinfo("pip", "No requirements.txt in the project root.")
            return
        py = self._python_for_subprocess()
        if not py:
            return
        self._async_console_cmd([py, "-m", "pip", "install", "-r", "requirements.txt"], title="pip install")
    def shell_command_dialog(self):
        if not self.project_path:
            messagebox.showinfo("Project", "Open a project first.")
            return
        cmd = _ctk_prompt_string(
            self,
            "Shell command",
            "Runs in project folder. On Windows this uses cmd /c.",
            entry_width=520,
        )
        if not cmd:
            return
        if sys.platform.startswith("win"):
            subprocess.Popen(
                ["cmd", "/k", cmd],
                cwd=self.project_path,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            subprocess.Popen(["/bin/sh", "-c", cmd], cwd=self.project_path)
        self.console.write(f"Launched shell: {cmd}\n")
    def zip_dist_folder(self):
        if not self.project_path:
            messagebox.showinfo("Project", "Open a project first.")
            return
        dist = os.path.join(self.project_path, "dist")
        if not os.path.isdir(dist):
            messagebox.showinfo("Zip", "No dist folder found. Build an .exe first.")
            return
        base = os.path.join(self.project_path, "dist_bundle")
        try:
            shutil.make_archive(base, "zip", root_dir=dist)
        except OSError as e:
            messagebox.showerror("Zip", str(e))
            return
        messagebox.showinfo("Zip", f"Created:\n{base}.zip")
if __name__ == "__main__":
    app = PyForgePro()
    app.mainloop()