# PyForge

**A modern, lightweight Python code editor / IDE** built with **Tkinter + CustomTkinter**, featuring VS Code-inspired syntax highlighting, project management, live console, and one-click .exe building.
<img width="1406" height="1184" alt="image" src="https://github.com/user-attachments/assets/ebd71c6f-e04a-4c23-af51-2a7b34b08b00" />


## ✨ Features

- VS Code-style syntax highlighting (keywords, strings, comments, numbers, decorators, exceptions, etc.)
- Line numbers + current-line highlight
- Project folder management with .py file browser
- Create new projects & files
- Recent projects list (last 8 remembered)
- Persistent state (remembers last opened project + file)
- Built-in search (Find Next / Previous, Match Case)
- Live read-only console output
- Run current Python file in external terminal
- One-click **Build .exe** with PyInstaller (--onefile)
- Autosave every 3 seconds
- Clean dark-themed UI with CustomTkinter
- Keyboard shortcuts (Ctrl+N, Ctrl+S, Ctrl+R, Ctrl+B, Ctrl+F, Esc)


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
