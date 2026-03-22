# PyForge

**A modern, lightweight Python code editor / IDE** built with **Tkinter + CustomTkinter**, featuring VS Code-inspired syntax highlighting, project management, live console, and one-click .exe building.
<img width="1402" height="1186" alt="image" src="https://github.com/user-attachments/assets/4fed57eb-9314-4de8-93fc-d7ff7b70c82f" />



Here’s an updated and more accurate version of the features list based on the code you shared (as of the version you posted):

### ✨ Current Features (updated March 2025–2026 perspective)

- **VS Code–like syntax highlighting**  
  - Keywords, strings (single & triple-quoted), comments, docstrings, numbers (incl. hex/bin/oct), built-ins, exceptions, types, class names, decorators, `self`/`super`/`cls`, etc.  
  - Uses `idlelib.colorizer` + custom tag definitions and colors closely matching VS Code Dark+ theme

- **Line numbers pane** (fixed-width, right-aligned)  
  - Highlights current line number in bold  
  - Clicking a line number → jumps cursor to start of that line

- **Current line highlighting** (subtle background)

- **Project-based workflow**  
  - Projects live inside `~/pyforge_projects/` (or custom location via open folder)  
  - Only `.py` files are shown in the project file list  
  - Create new project → auto-creates `main.py` with hello-world template  
  - Open existing folder as project (via button or recent list)

- **Recent projects** (up to 8)  
  - Shown as clickable labels  
  - Right-click → remove from list  
  - Persisted in `~/.pyforge_recent.json`

- **Session persistence**  
  - Remembers last opened project + last opened file  
  - Stored in `~/.pyforge_state.json`  
  - Restores on startup if folders/files still exist

- **In-editor find** (Ctrl+F / Ctrl+Shift+F)  
  - Find Next / Find Previous  
  - Match case checkbox  
  - Minimal UI (appears at top when activated, Esc / × to close)

- **Simple integrated output console** (read-only ScrolledText)  
  - Currently only shows launch messages (“Launched: …”)  
  - Does **not** capture real subprocess output (yet)

- **Run current file** (Ctrl+R)  
  - Saves file first  
  - Launches in **external** terminal/console window  
  - Windows → new `cmd` window  
  - Linux → tries `x-terminal-emulator` / `gnome-terminal` / `xterm`  
  - macOS → uses `open` (should be updated)

- **One-click .exe build** (Ctrl+B) using **PyInstaller**  
  - `--onefile` mode  
  - `--noconfirm`  
  - Custom output name (sanitized from script filename)  
  - Builds into project folder / `dist/` and `build/`  
  - Automatically tries to install PyInstaller (normal or --user) if missing  
  - Launches build in new console window (Windows) or background (others)

- **Auto-save every 3 seconds** (only when file is open)  
  - Writes directly to disk → content also kept in memory dict

- **New file** creation inside project (prompts for name)

- **Rename file** (right-click in file listbox)  
  - Only `.py` files  
  - Updates internal open-files dict and current_file if needed

- **Clean dark modern UI** built with **CustomTkinter**  
  - Sidebar layout inspired by lightweight VS Code / PyCharm feel  
  - Button grouping: project controls, file actions, build/run

- **Keyboard shortcuts**  
  - Ctrl+N → New File  
  - Ctrl+S → Save  
  - Ctrl+R → Run  
  - Ctrl+B → Build .exe  
  - Ctrl+F / Ctrl+Shift+F → Toggle search  
  - Esc → Close search bar (when open)

### Missing / Not really implemented yet (common expectations)

- Multi-file tabbed editing (currently only one file visible at a time)
- Real-time console output capture from run process
- Syntax error / linting / diagnostics
- Code completion / IntelliSense
- Folder / file tree (only flat .py list)
- Git integration
- Virtual environment support / requirements.txt handling
- Debugging (breakpoints, step-through)
- Find in files / project-wide search & replace
- Dark/light theme switcher (hard-coded dark)
- macOS-specific run behavior improvement (current `open` call is wrong for scripts)

### Suggested next small-to-medium improvements (in rough priority order)

1. Tabbed editor (multiple open files visible)
2. Capture & show real stdout/stderr in the bottom console pane
3. Remember open files per project (re-open them on project load)
4. Add “Save As…” for current file
5. Improve run behavior on macOS (use `osascript` or terminal app)
6. Add simple status bar (file path, line:column, Python version…)
7. Remember window size & position
8. Add basic file icons or at least distinguish `__main__.py` / `main.py`

Would you like to focus on any of these next (especially #1 or #2 — they make the biggest practical difference), or do you have another feature in mind? 😄


## 🚀 Installating the Source

1. Clone the repository:
   ```bash
   git clone https://github.com/ch3mo/PyForge.git

2. Change directory:
   ```bash
   cd PyForge

3. Install dependencies:
   ```bash
   pip install customtkinter pyinstaller


## 🏃‍♂️ Quick Start

1. Launch the editor:
   ```bash
   python pyforge_pro.py
2. Click Open Project → choose or create a project folder inside pyforge_projects/
3. Start coding — syntax highlighting and line numbers appear automatically
4. Use Run Current to execute the file in a terminal
5. Use Build .exe to create a standalone Windows executable

## ⌨️ Keyboard Shortcuts

| Shortcut       | Action                      |
|----------------|-----------------------------|
| Ctrl + N       | New File                    |
| Ctrl + S       | Save File                   |
| Ctrl + R       | Run Current File            |
| Ctrl + B       | Build .exe                  |
| Ctrl + F       | Toggle Search Bar           |

> Tip: All shortcuts work when the editor window is focused.


## 📦 Building Executable
You can build PyForge itself as a standalone .exe directly from the app:

1. Open pyforge_pro.py inside PyForge
2. Click Build .exe

Or manually from command line:
1. Open command promt:
   ```bash
   Bashpyinstaller --onefile --name PyForge --windowed pyforge_pro.py

## 📁 Project Structure

| Path                              | Description                                             |
|-----------------------------------|---------------------------------------------------------|
| `pyforge_projects/`               | Root folder where all your projects are stored          |
| `pyforge_projects/MyProject/`     | Example project folder                                  |
| `pyforge_projects/MyProject/main.py` | Main Python file of the project                      |
| `pyforge_projects/MyProject/other.py` | Additional Python files                             |
| `~/.pyforge_recent.json`          | Stores the list of recently opened projects (last 8)    |
| `~/.pyforge_state.json`           | Remembers the last opened project and file              |
| `dist/`                           | Output folder created by PyInstaller when building .exe |


## ⚠️ Known Limitations

| Limitation                                      | Details                                                                 |
|-------------------------------------------------|-------------------------------------------------------------------------|
| Project browser                                 | Only shows .py files                                                    |
| Editing                                         | Single-file only (no tabs or multi-file support yet)                    |
| Syntax highlighting                             | Regex-based (good coverage, but not full LSP-level)                     |
| Console                                         | Output-only (no stdin/input support)                                    |
| Terminal launching                              | Optimized for Windows (falls back to basic options on Linux/macOS)      |


## 🛠️ TODO / Roadmap Ideas

- [ ] Multi-tab editor support  
- [ ] Recursive folder tree view   
- [ ] Settings / preferences panel  
- [ ] Basic Git integration  
- [ ] Code folding & minimap  
- [ ] Support for more file types

## 📄 License
MIT License

## 🤝 Contributing
Contributions, bug reports, feature requests, and pull requests are welcome!
Feel free to open an issue or submit a PR.
