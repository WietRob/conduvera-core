# Matrix OS 🟢

A Matrix-themed Terminal User Interface (TUI) operating system for software development, built with Python and Textual.

```
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   ███╗   ███╗ █████╗ ████████╗██████╗ ██╗██╗  ██╗           ║
║   ████╗ ████║██╔══██╗╚══██╔══╝██╔══██╗██║╚██╗██╔╝           ║
║   ██╔████╔██║███████║   ██║   ██████╔╝██║ ╚███╔╝            ║
║   ██║╚██╔╝██║██╔══██║   ██║   ██╔══██╗██║ ██╔██╗            ║
║   ██║ ╚═╝ ██║██║  ██║   ██║   ██║  ██║██║██╔╝ ██╗           ║
║   ╚═╝     ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝           ║
║                                                               ║
║              Development Environment v0.1.0                   ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
```

## 🎯 Features

- **🎨 Matrix Digital Rain Effect** - Iconic falling green characters animation
- **💻 Terminal Emulator** - Full PTY-based terminal with shell integration
- **📁 File Browser** - Tree-view file navigation with icons
- **📊 Process Monitor** - Real-time system process monitoring
- **✏️ Code Editor** - Syntax highlighting for multiple languages
- **🎨 Theming System** - Customizable Matrix green theme
- **⚡ High Performance** - 30+ FPS smooth animations
- **🔌 Plugin Architecture** - Extensible plugin system (coming soon)

## 🚀 Quick Start

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/WietRob/matrix-os.git
cd matrix-os
```

2. **Run Matrix OS**
```bash
./run.sh
```

The launcher script will automatically:
- Check Python version (3.10+ required)
- Create virtual environment
- Install dependencies
- Launch Matrix OS

### Manual Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run Matrix OS
python3 -m src.core.app
```

## 🎮 Usage

### Launch Modes

```bash
# Main Textual application (default)
./run.sh textual

# Rich-based demo (status dashboard)
./run.sh rich

# Curses-based demo (minimal dependencies)
./run.sh curses

# Development mode with DevTools
./run.sh dev

# Run tests
./run.sh test
```

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Q` | Quit application |
| `F1` | Toggle Matrix rain effect |
| `Ctrl+T` | Open terminal |
| `Ctrl+F` | Open file browser |
| `Ctrl+P` | Open process monitor |
| `F2` | Show help |

## 📁 Project Structure

```
matrix-os/
├── src/
│   ├── core/
│   │   ├── app.py              # Main application
│   │   └── __init__.py
│   │
│   ├── ui/
│   │   ├── widgets/
│   │   │   ├── matrix_rain.py  # Matrix rain effect
│   │   │   ├── terminal.py     # Terminal emulator
│   │   │   ├── file_browser.py # File browser
│   │   │   ├── process_monitor.py
│   │   │   └── code_editor.py
│   │   │
│   │   ├── themes/
│   │   │   └── matrix.tcss     # Matrix theme CSS
│   │   │
│   │   └── layouts/
│   │
│   ├── system/                 # System integrations
│   ├── effects/                # Visual effects
│   │
│   └── utils/
│       ├── config.py           # Configuration
│       └── logger.py           # Logging
│
├── config/
│   └── default.yaml            # Default configuration
│
├── examples/
│   ├── rich_demo.py           # Rich library demo
│   └── curses_demo.py         # Curses demo
│
├── tests/                      # Test suite
├── docs/                       # Documentation
│
├── run.sh                      # Launcher script
├── requirements.txt
├── pyproject.toml
└── README.md
```

## 🔧 Configuration

Configuration is stored in YAML format at:
- `~/.config/matrix-os/config.yaml` (user config)
- `./config/default.yaml` (default config)

### Example Configuration

```yaml
matrix_os:
  display:
    fps: 30
    true_color: true

  effects:
    rain:
      enabled: true
      density: 0.05
      speed_min: 0.5
      speed_max: 2.0
      char_set: "mixed"  # katakana, ascii, mixed

  terminal:
    shell: "/bin/bash"
    scrollback: 10000

  editor:
    theme: "monokai"
    tab_size: 4
    syntax_highlighting: true
```

## 🎨 Widgets Overview

### Matrix Rain Widget

Iconic digital rain effect with customizable:
- Character sets (Katakana, ASCII, mixed)
- Falling speed
- Density
- Color gradients

```python
from src.ui.widgets.matrix_rain import MatrixRain

rain = MatrixRain(
    char_set="mixed",
    fps=30,
    speed_min=0.5,
    speed_max=2.0
)
```

### Terminal Emulator

Full-featured terminal with:
- PTY (pseudo-terminal) support
- Shell integration
- Command execution
- Output streaming

```python
from src.ui.widgets.terminal import Terminal

terminal = Terminal(shell="/bin/bash")
terminal.execute_command("ls -la")
```

### File Browser

Tree-view file navigation with:
- Lazy loading
- File type icons
- Hidden files toggle
- Directory expansion

```python
from src.ui.widgets.file_browser import FileBrowser

browser = FileBrowser(root_path=Path.home())
```

### Process Monitor

Real-time process monitoring:
- CPU and memory usage
- Process status
- Sortable columns
- Auto-refresh

```python
from src.ui.widgets.process_monitor import ProcessMonitor

monitor = ProcessMonitor(refresh_interval=2.0)
```

## 🛠️ Development

### Prerequisites

- Python 3.10+
- Terminal with true color support
- Linux/macOS (Windows via WSL)

### Development Setup

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run in development mode
./run.sh dev

# Run tests
pytest tests/ -v

# Code formatting
black src/ tests/

# Type checking
mypy src/
```

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=src tests/

# Specific test
pytest tests/test_widgets.py -v
```

## 🎯 Roadmap

### v0.2.0 (In Progress)
- [ ] Window management system
- [ ] Event bus implementation
- [ ] Plugin system
- [ ] Multi-tab support

### v0.3.0 (Planned)
- [ ] Git integration
- [ ] Debugger interface
- [ ] Search functionality
- [ ] Custom keybindings

### v1.0.0 (Future)
- [ ] Remote SSH support
- [ ] Collaborative editing
- [ ] Plugin marketplace
- [ ] Theme customization UI

## 📚 Documentation

- [Analysis Document](ANALYSIS_MATRIX_OS_TUI.md) - Comprehensive technical analysis
- [API Documentation](docs/API.md) - API reference (coming soon)
- [User Guide](docs/USER_GUIDE.md) - Detailed user guide (coming soon)
- [Plugin Development](docs/PLUGINS.md) - Plugin creation guide (coming soon)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Textual](https://textual.textualize.io/) - Modern TUI framework
- [Rich](https://rich.readthedocs.io/) - Beautiful terminal formatting
- [The Matrix](https://en.wikipedia.org/wiki/The_Matrix) - Inspiration for the aesthetic

## 🔗 Links

- **GitHub**: [WietRob/matrix-os](https://github.com/WietRob/matrix-os)
- **Issues**: [Report a bug](https://github.com/WietRob/matrix-os/issues)
- **Textual Documentation**: [textual.textualize.io](https://textual.textualize.io/)

## 📸 Screenshots

```
┌─────────────────────────────────────────────────────────────┐
│ Matrix OS - Development Environment                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📁 Files          │  ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉ     │
│  💻 Terminal       │  0123456789ABCDEFGHIJK                 │
│  📊 Processes      │  ﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜｦﾝ           │
│  ✏️ Editor         │                                         │
│                    │  [Matrix Rain Effect]                  │
│                    │                                         │
│  ⚙️ Settings       │  System Status: ONLINE                 │
│  ❓ Help           │  Terminal: 80x24                       │
│                    │  Processes: 142                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

**Built with 💚 using Python and Textual**

*"Welcome to the Matrix"*
