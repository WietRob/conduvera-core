# Matrix OS Quick Start Guide

> Deprecated: Historical reference only. This document does not describe the current merged Matrix OS architecture. Use `docs/MATRIX_OS_ARCHITECTURE.md`, `docs/MATRIX_OS_MODULE_BOUNDARIES.md`, `docs/COMPLIANCE_ACCOUNTABILITY_INDEX.md`, and `docs/RELEASE_TRAIN_STATUS.md` as authoritative current docs.


## Installation

### Prerequisites

- Python 3.10 or higher
- Terminal with true color support
- 4GB RAM minimum
- Linux or macOS (Windows via WSL)

### Quick Install

```bash
# Clone repository
git clone https://github.com/WietRob/matrix-os.git
cd matrix-os

# Run launcher (handles all setup automatically)
./run.sh
```

That's it! The launcher script will:
1. Check Python version
2. Create virtual environment
3. Install all dependencies
4. Launch Matrix OS

## First Launch

When you first launch Matrix OS, you'll see:

1. **Header** - Application title and status
2. **Sidebar** - Navigation menu with buttons
3. **Main Area** - Content display with Matrix rain effect
4. **Footer** - Keyboard shortcuts and help

## Basic Navigation

### Using the Sidebar

Click or use keyboard to navigate:
- `📁 File Browser` - Browse files and directories
- `💻 Terminal` - Open shell terminal
- `📊 Processes` - Monitor system processes
- `✏️ Editor` - Code editor
- `⚙️ Settings` - Configure Matrix OS
- `❓ Help` - Show help information
- `🚪 Exit` - Quit application

### Keyboard Shortcuts

Essential shortcuts:
- `Ctrl+Q` - Quit Matrix OS
- `F1` - Toggle Matrix rain effect
- `Tab` - Navigate between widgets
- `Enter` - Select/activate
- `Esc` - Cancel/go back

## Common Tasks

### Opening a File

1. Click `📁 File Browser` in sidebar
2. Navigate using arrow keys or mouse
3. Press `Enter` to open file
4. File opens in code editor

### Running Terminal Commands

1. Click `💻 Terminal` in sidebar
2. Terminal opens with your default shell
3. Type commands as normal
4. Use `Ctrl+C` to interrupt commands

### Monitoring Processes

1. Click `📊 Processes` in sidebar
2. View running processes with CPU/Memory usage
3. Processes auto-refresh every 2 seconds
4. Use arrow keys to select processes

### Editing Code

1. Open file via File Browser
2. Code editor opens with syntax highlighting
3. Edit as normal text editor
4. Changes auto-tracked (modified indicator)

## Customization

### Configuration File

Matrix OS reads configuration from:
```
~/.config/matrix-os/config.yaml
```

Create this file to customize:

```yaml
matrix_os:
  display:
    fps: 30  # Animation frame rate

  effects:
    rain:
      enabled: true
      char_set: "mixed"  # katakana, ascii, mixed

  terminal:
    shell: "/bin/bash"  # Your preferred shell
```

### Changing Matrix Rain

Toggle rain on/off: `F1`

Edit `config.yaml` to customize:
```yaml
effects:
  rain:
    density: 0.05      # Higher = more drops
    speed_min: 0.5     # Minimum fall speed
    speed_max: 2.0     # Maximum fall speed
    char_set: "katakana"  # Character set
```

## Troubleshooting

### Matrix OS won't start

**Problem**: Python version error
```
Solution: Ensure Python 3.10+ is installed
$ python3 --version
```

**Problem**: Module not found
```
Solution: Reinstall dependencies
$ source venv/bin/activate
$ pip install -r requirements.txt
```

**Problem**: Terminal display issues
```
Solution: Ensure terminal supports true color
Set: export TERM=xterm-256color
```

### Performance Issues

**Slow/choppy animation**:
- Lower FPS in config: `display.fps: 20`
- Disable rain effect: Press `F1`
- Close unused widgets

**High memory usage**:
- Reduce terminal scrollback: `terminal.scrollback: 1000`
- Limit process monitor refresh: `process_monitor.max_processes: 25`

### Display Issues

**Colors look wrong**:
1. Check terminal supports 24-bit color
2. Set `TERM=xterm-256color` in environment
3. Try different terminal (iTerm2, Alacritty recommended)

**Text garbled/overlapping**:
1. Resize terminal window
2. Restart Matrix OS
3. Check terminal font supports Unicode

## Alternative Modes

### Rich Demo (Lightweight)

For quick system monitoring without full TUI:
```bash
./run.sh rich
```

Features:
- Live updating dashboard
- System stats
- Process monitor
- Matrix rain effect
- Lower resource usage

### Curses Demo (Minimal)

For minimal dependencies or older systems:
```bash
./run.sh curses
```

Features:
- Classic curses interface
- Matrix rain only
- No external dependencies beyond Python stdlib
- Works on basic terminals

## Next Steps

- Read [User Guide](USER_GUIDE.md) for detailed features
- Check [ANALYSIS_MATRIX_OS_TUI.md](../ANALYSIS_MATRIX_OS_TUI.md) for architecture
- Explore [examples/](../examples/) for code samples
- Join discussions on GitHub Issues

## Getting Help

- Press `F2` or `❓ Help` button for in-app help
- Check documentation in `docs/` folder
- Report issues: https://github.com/WietRob/matrix-os/issues
- Read source code - it's well documented!

---

**Enjoy your journey into the Matrix! 🟢**
