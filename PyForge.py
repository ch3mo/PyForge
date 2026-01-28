import os
import json
import subprocess
import sys
from tkinter import messagebox, simpledialog, filedialog
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
import customtkinter as ctk
import idlelib.colorizer as ic
import idlelib.percolator as ip
import re
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
TOOLS_ROOT = "pyforge_projects"
os.makedirs(TOOLS_ROOT, exist_ok=True)
RECENT_FILE = os.path.expanduser("~/.pyforge_recent.json")
STATE_FILE = os.path.expanduser("~/.pyforge_state.json")
class VSSyntaxText(tk.Text):
    def __init__(self, master, **kwargs):
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
        font = ("Consolas", 13)
        italic_font = ("Consolas", 13, "italic")
        for tag, config in self.tagdefs.items():
            config['font'] = italic_font if 'Comment' in tag else font
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
        self.tag_configure("current_line", background="#2A2D2E")
    def set_current_line(self, line):
        self.tag_remove("current_line", "1.0", "end")
        if line > 0:
            self.tag_add("current_line", f"{line}.0", f"{line}.0 lineend + 1 char")
class LiveConsole(ScrolledText):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs, bg="#1E1E1E", fg="#D4D4D4",
                         font=("Consolas", 11), insertbackground="white")
    def write(self, text, color=None):
        self.insert("end", text)
        self.see("end")
    def flush(self):
        pass
class PyForgePro(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PyForge Pro")
        self.geometry("1400x1150")
        self.minsize(1100, 600)
        self.project_path = None
        self.current_file = None
        self.open_files = {}
        self.recent_projects = self.load_recent_projects()
        self.last_project = None
        self.last_file = None
        self.load_last_state()
        self.setup_ui()
        self.setup_bindings()
        self.start_autosave()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        if self.last_project and os.path.isdir(self.last_project):
            self.open_project_folder(self.last_project, restore=True)
            if self.last_file and os.path.exists(self.last_file) and self.last_file.startswith(self.last_project + os.sep):
                self.open_file(self.last_file)
    def load_last_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.last_project = data.get("last_project")
                    self.last_file = data.get("last_file")
            except:
                pass
    def save_state(self):
        if not self.project_path or not os.path.isdir(self.project_path):
            if os.path.exists(STATE_FILE):
                try:
                    os.remove(STATE_FILE)
                except:
                    pass
            return
        data = {
            "last_project": self.project_path,
            "last_file": self.current_file if self.current_file else None
        }
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except:
            pass
    def on_closing(self):
        self.save_state()
        self.destroy()
    def load_recent_projects(self):
        if os.path.exists(RECENT_FILE):
            try:
                with open(RECENT_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("recent", [])
            except:
                pass
        return []
    def save_recent_projects(self):
        data = {"recent": self.recent_projects}
        try:
            with open(RECENT_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except:
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
        self.grid_rowconfigure(0, weight=1)
        main = ctk.CTkFrame(self)
        main.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        main.grid_rowconfigure(2, weight=1)
        main.grid_columnconfigure(1, weight=1)
        self.tabs_frame = ctk.CTkFrame(main, height=40, fg_color="#252526")
        self.tabs_frame.grid(row=0, column=0, sticky="ew", columnspan=3)
        self.search_frame = ctk.CTkFrame(main, height=40, fg_color="#252526")
        self.search_frame.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.search_frame.grid_remove()
        self.match_case_var = tk.BooleanVar(value=False)
        ctk.CTkLabel(self.search_frame, text="Find:").pack(side="left", padx=5)
        self.search_entry = ctk.CTkEntry(self.search_frame, placeholder_text="Search term", width=300)
        self.search_entry.pack(side="left", padx=5)
        self.find_next_btn = ctk.CTkButton(self.search_frame, text="Find Next", command=self.find_next, width=100)
        self.find_next_btn.pack(side="left", padx=5)
        self.find_prev_btn = ctk.CTkButton(self.search_frame, text="Find Previous", command=self.find_previous, width=100)
        self.find_prev_btn.pack(side="left", padx=5)
        self.match_case_chk = ctk.CTkCheckBox(self.search_frame, text="Match case", variable=self.match_case_var)
        self.match_case_chk.pack(side="left", padx=5)
        self.close_search_btn = ctk.CTkButton(
            self.search_frame,
            text="×",
            command=self.hide_search,
            width=40,
            height=40,
            corner_radius=20,
            fg_color="transparent",
            hover_color="#3C3C3C",
            text_color="#858585",
            font=("Segoe UI", 20, "bold")
        )
        self.close_search_btn.pack(side="right", padx=15)
        self.close_search_btn.bind("<Enter>", lambda e: self.close_search_btn.configure(text_color="#FF5555"))
        self.close_search_btn.bind("<Leave>", lambda e: self.close_search_btn.configure(text_color="#858585"))
        self.line_numbers = tk.Text(
            main, width=6, padx=12, pady=0, takefocus=0,
            bg="#252526", fg="#858585", font=("Consolas", 13),
            state="disabled", relief="flat", highlightthickness=0, borderwidth=0, cursor="arrow"
        )
        self.line_numbers.grid(row=2, column=0, sticky="ns")
        tk.Frame(main, width=1, bg="#343434").grid(row=2, column=0, sticky="ns", padx=(58, 0))
        self.editor = VSSyntaxText(
            main, undo=True, wrap="none",
            bg="#1E1E1E", fg="#D4D4D4", insertbackground="white",
            selectbackground="#264F78", font=("Consolas", 13),
            borderwidth=0, highlightthickness=0
        )
        self.editor.grid(row=2, column=1, sticky="nsew")
        self.vsb = tk.Scrollbar(main, orient="vertical", command=self.yview_both)
        self.vsb.grid(row=2, column=2, sticky="ns")
        self.editor.configure(yscrollcommand=self.vsb.set)
        self.line_numbers.configure(yscrollcommand=self.vsb.set)
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
            "<FocusIn>", "<FocusOut>", "<Motion>"
        ]
        for ev in update_events:
            self.editor.bind(ev, lambda e=None: self.after(50, self.update_highlight_and_lines))
        self.editor.bind("<Configure>", lambda e=None: self.after(100, self.update_highlight_and_lines))
        self.vsb.bind("<B1-Motion>", lambda e=None: self.after(50, self.update_highlight_and_lines))
        self.console = LiveConsole(main, height=10)
        self.console.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        sidebar = ctk.CTkFrame(self, width=300, fg_color="#252526")
        sidebar.grid(row=0, column=2, sticky="ns", pady=10, padx=(0, 10))
        sidebar.grid_propagate(False)
        ctk.CTkLabel(sidebar, text="PYFORGE PRO", font=("Segoe UI", 24, "bold"), text_color="#CCCCCC").pack(pady=(20, 5))
        ctk.CTkLabel(sidebar, text="Developer Edition", font=("Segoe UI", 10), text_color="#888888").pack()
        self.project_btn = ctk.CTkButton(sidebar, text="Open Project",
                                         width=260, height=50,
                                         fg_color="#007ACC", hover_color="#005A9E",
                                         font=("Segoe UI", 14, "bold"),
                                         command=self.toggle_project)
        self.project_btn.pack(pady=20, padx=20)
        ctk.CTkButton(sidebar, text="Create Project",
                      width=260, height=40,
                      fg_color="#3C3C3C", hover_color="#505050",
                      command=self.create_project).pack(pady=5, padx=20)
        self.project_label = ctk.CTkLabel(sidebar, text="No project open", text_color="#888888")
        self.project_label.pack(pady=(0, 20))
        btn_style = {"width": 260, "height": 40, "fg_color": "#3C3C3C", "hover_color": "#505050", "corner_radius": 8}
        for text, cmd in [
            ("New File", self.new_file),
            ("Save File", self.save_current_file),
            ("Run Current", self.run_current_file),
            ("Build .exe", self.build_exe),
        ]:
            ctk.CTkButton(sidebar, text=text, command=cmd, **btn_style).pack(pady=4, padx=20)
        ctk.CTkLabel(sidebar, text="Project Files", font=("Segoe UI", 14, "bold"), text_color="#CCCCCC")\
            .pack(pady=(30, 5), anchor="w", padx=20)
        self.file_listbox = tk.Listbox(sidebar, bg="#2D2D30", fg="#CCCCCC", font=("Consolas", 11),
                                       selectbackground="#007ACC", highlightthickness=0)
        self.file_listbox.pack(fill="both", expand=False, padx=20, pady=5, ipady=60)
        self.file_listbox.bind("<<ListboxSelect>>", self.on_file_select)
        ctk.CTkLabel(sidebar, text="Recent Projects", font=("Segoe UI", 14, "bold"), text_color="#CCCCCC")\
            .pack(pady=(20, 5), anchor="w", padx=20)
        self.recent_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        self.recent_frame.pack(fill="x", padx=20, pady=5)
        self.recent_labels = []
        self.refresh_recent_ui()
        ctk.CTkLabel(sidebar, text="© 2026 • PyForge", font=("Segoe UI", 9), text_color="#666666")\
            .pack(side="bottom", pady=15)
        self.search_entry.bind("<Return>", lambda e: self.find_next())
    def yview_both(self, *args):
        self.editor.yview(*args)
        self.line_numbers.yview(*args)
    def on_mousewheel(self, event):
        if sys.platform.startswith("win"):
            delta = -1 * (event.delta // 120)
        else:
            delta = -1 if event.delta > 0 else 1
        self.yview_both("scroll", delta, "units")
        self.after(80, self.update_highlight_and_lines)
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
        except:
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
        self.line_numbers.tag_configure("current", foreground="#CCCCCC", font=("Consolas", 13, "bold"))
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
            lbl = ctk.CTkLabel(self.recent_frame, text=name, text_color="#AAAAAA",
                               font=("Segoe UI", 12), anchor="w", cursor="hand2")
            lbl.pack(fill="x", pady=3)
            lbl.bind("<Button-1>", lambda e, p=path: self.open_project_folder(p))
            lbl.bind("<Enter>", lambda e, l=lbl: l.configure(text_color="#FFFFFF"))
            lbl.bind("<Leave>", lambda e, l=lbl: l.configure(text_color="#AAAAAA"))
            self.recent_labels.append(lbl)
    def open_project_folder(self, path, restore=False):
        if not os.path.isdir(path):
            messagebox.showwarning("Not Found", f"Project folder no longer exists:\n{path}")
            self.recent_projects = [p for p in self.recent_projects if p != path]
            self.save_recent_projects()
            self.refresh_recent_ui()
            return
        self.project_path = path
        self.project_btn.configure(text="Close Project")
        self.project_label.configure(text=os.path.basename(path))
        self.load_project_files()
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
        self.bind("<Escape>", lambda e: self.hide_search() if self.search_frame.winfo_ismapped() else None)
    def start_autosave(self):
        def save():
            if self.current_file:
                try:
                    content = self.editor.get("1.0", "end-1c")
                    with open(self.current_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    self.open_files[self.current_file] = content
                except:
                    pass
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
                self.project_path = None
                self.current_file = None
                self.open_files.clear()
                self.file_listbox.delete(0, "end")
                self.editor.delete("1.0", "end")
                self.project_btn.configure(text="Open Project")
                self.project_label.configure(text="No project open")
                self.save_state()
        else:
            path = filedialog.askdirectory(title="Open Project", initialdir=TOOLS_ROOT)
            if path and os.path.isdir(path):
                self.open_project_folder(path)
    def load_project_files(self):
        self.file_listbox.delete(0, "end")
        self.open_files.clear()
        for file in sorted(os.listdir(self.project_path)):
            if file.endswith(".py"):
                self.file_listbox.insert("end", file)
                fpath = os.path.join(self.project_path, file)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        self.open_files[fpath] = f.read()
                except:
                    self.open_files[fpath] = ""
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
    def on_file_select(self, event):
        sel = self.file_listbox.curselection()
        if sel:
            filename = self.file_listbox.get(sel[0])
            path = os.path.join(self.project_path, filename)
            self.open_file(path)
    def open_file(self, path):
        if path not in self.open_files:
            return
        self.current_file = path
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", self.open_files[path])
        self.editor.mark_set("insert", "1.0")
        self.update_highlight_and_lines()
        self.title(f"PyForge Pro — {os.path.basename(path)}")
        self.save_state()
    def save_current_file(self):
        if self.current_file:
            content = self.editor.get("1.0", "end-1c")
            with open(self.current_file, "w", encoding="utf-8") as f:
                f.write(content)
            self.open_files[self.current_file] = content
            messagebox.showinfo("Saved", f"Saved {os.path.basename(self.current_file)}")
            self.save_state()
    def run_current_file(self):
        if not self.current_file:
            messagebox.showwarning("No File", "No file is currently open.")
            return
        self.save_current_file()
        file_path = os.path.abspath(self.current_file)
        if sys.platform.startswith("win"):
            cmd = f'start cmd /K python "{file_path}"'
            subprocess.Popen(cmd, shell=True)
        else:
            cmd = f'x-terminal-emulator -e python3 "{file_path}" || gnome-terminal -- python3 "{file_path}" || xterm -e python3 "{file_path}"'
            subprocess.Popen(cmd, shell=True)
        self.console.write(f"Launched: {os.path.basename(self.current_file)}\n")
    def build_exe(self):
        if not self.current_file:
            messagebox.showwarning("No File", "No file is currently open.")
            return
        self.save_current_file()
        name = os.path.splitext(os.path.basename(self.current_file))[0]
        try:
            subprocess.Popen(["pyinstaller", "--onefile", "--name", name, self.current_file],
                             creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform.startswith("win") else 0)
            self.console.write(f"Started PyInstaller build for {name}.exe ...\n")
        except FileNotFoundError:
            messagebox.showerror("PyInstaller not found", "Please install pyinstaller:\npip install pyinstaller")
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
if __name__ == "__main__":
    app = PyForgePro()
    app.mainloop()