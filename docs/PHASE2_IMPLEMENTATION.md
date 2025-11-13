# Phase 2: Functional Widgets - Matrix OS

**Date:** 2025-11-13
**Branch:** `claude/matrix-os-ui-design-comparison-011CV5dNAePdv7fjnr4ABzKW`
**Status:** ✅ Completed (Core Features)

## Overview

Phase 2 implements functional, interactive widgets for the Matrix OS TUI application. This phase transforms the static UI from Phase 1 into a fully working development environment with real file browsing, process monitoring, and system information displays.

---

## 🎯 Goals Achieved

✅ **File Browser** - Working tree-view file navigator
✅ **Process Monitor** - Live system process tracking with auto-refresh
✅ **System Info Panel** - Real-time system metrics dashboard
✅ **View Switching** - Dynamic content switching system
✅ **Rich Integration** - All widgets use Rich-style theming from Phase 1

---

## 📁 1. File Browser Widget

**File:** `src/ui/widgets/file_browser.py`

### Features

#### 🌳 Tree View Navigation
- Hierarchical directory structure
- Lazy loading of directories (expand on demand)
- Navigate with arrow keys and Enter
- Parent directory navigation

#### 🎨 File Type Icons
Extensive icon mapping for file types:
- **Directories**: 📁
- **Python**: 🐍
- **JavaScript/TypeScript**: 📜📘
- **Web**: 🌐 (HTML), 🎨 (CSS)
- **Config**: ⚙️ (YAML/JSON)
- **Documents**: 📝 (Markdown), 📄 (Text)
- **Images**: 🖼️ (PNG/JPG/GIF)
- **Archives**: 📦 (ZIP/TAR)
- **Symlinks**: 🔗
- **Generic**: 📄

#### 🔧 Functionality
```python
# Features
- show_hidden: Toggle hidden files (.files)
- current_path: Track current directory
- path_to_node: Fast path → node lookups

# Methods
- load_directory(path) - Load directory contents
- go_to_parent() - Navigate up one level
- go_to_path(path) - Jump to specific path
- toggle_hidden_files() - Show/hide dotfiles
- get_selected_path() - Get currently selected item

# Messages
- FileSelected(path) - Posted when file clicked
- DirectoryChanged(path) - Posted on directory change
```

### Rich-Style Theming
```css
FileBrowser {
    background: rgba(0, 20, 0, 0.8);  /* Semi-transparent green */
    border: round #00FF00;             /* Rounded border */
    color: #00FF00;
}

FileBrowser:focus {
    border: heavy #00FF00;             /* Heavy when focused */
    background: rgba(0, 30, 0, 0.9);   /* Brighter on focus */
}

FileBrowser > .tree--cursor {
    background: rgba(0, 150, 0, 0.8);  /* Highlight selection */
    color: #FFFFFF;
    text-style: bold;
}
```

### Usage Example
```python
from src.ui.widgets.file_browser import FileBrowser
from pathlib import Path

# Create file browser
browser = FileBrowser(
    root_path=Path.cwd(),
    show_hidden=False,
    label="📁 File Browser"
)

# Handle events
def on_file_selected(message: FileBrowser.FileSelected):
    print(f"Selected file: {message.path}")

def on_directory_changed(message: FileBrowser.DirectoryChanged):
    print(f"Changed to: {message.path}")
```

---

## 📊 2. Process Monitor Widget

**File:** `src/ui.widgets/process_monitor.py`

### Features

#### 📈 Real-Time Process Tracking
- Live process list with auto-refresh (default: 2 seconds)
- Top 50 processes by default (configurable)
- Sort by CPU, Memory, Name, PID
- Color-coded metrics

#### 🎨 Context-Aware Coloring

**CPU Usage:**
- `< 20%`: Green (normal)
- `20-50%`: Yellow (moderate)
- `50-80%`: Bold Yellow (high)
- `> 80%`: Bold Red (critical)

**Memory Usage:**
- `< 20%`: Green (normal)
- `20-50%`: Yellow (moderate)
- `50-80%`: Bold Yellow (high)
- `> 80%`: Bold Red (critical)

**Process Status:**
- `running`: Green
- `sleeping`: Blue
- `stopped`: Yellow
- `zombie`: Red
- `idle`: Dim

#### 📊 Columns Displayed
| Column | Width | Description |
|--------|-------|-------------|
| PID | 8 | Process ID |
| Name | 30 | Process name (truncated) |
| CPU% | 8 | CPU usage percentage |
| MEM% | 8 | Memory usage percentage |
| Status | 12 | Process state |
| User | 15 | Owner username |

#### 🔧 Functionality
```python
# Configuration
refresh_interval: float = 2.0  # Auto-refresh rate
max_processes: int = 50        # Max processes to show
sort_column: str = "cpu"       # Sort by CPU by default
auto_refresh: bool = True      # Enable auto-refresh

# Methods
- update_processes() - Manual refresh
- action_sort_by_cpu() - Sort by CPU
- action_sort_by_memory() - Sort by memory
- action_sort_by_name() - Sort alphabetically
- action_toggle_auto_refresh() - Toggle auto-refresh
- get_selected_process() - Get current selection

# Formatting
- format_cpu(percent) - Color-coded CPU display
- format_memory(percent) - Color-coded memory display
- format_status(status) - Color-coded status display
```

### Rich-Style Theming
```css
ProcessMonitor {
    background: rgba(0, 20, 0, 0.8);
    border: round #00FF00;
    color: #00FF00;
}

ProcessMonitor:focus {
    border: heavy #00FF00;
    background: rgba(0, 30, 0, 0.9);
}

ProcessMonitor > .datatable--header {
    background: rgba(0, 100, 0, 0.8);  /* Green header */
    color: #FFFFFF;
    text-style: bold;
}

ProcessMonitor > .datatable--cursor {
    background: rgba(0, 150, 0, 0.8);  /* Highlight row */
    color: #FFFFFF;
    text-style: bold;
}
```

### Usage Example
```python
from src.ui.widgets.process_monitor import ProcessMonitor

# Create process monitor
monitor = ProcessMonitor(
    refresh_interval=2.0,
    max_processes=50
)

# Sort processes
monitor.action_sort_by_cpu()      # By CPU usage
monitor.action_sort_by_memory()   # By memory usage
monitor.action_sort_by_name()     # Alphabetically

# Get selection
process_info = monitor.get_selected_process()
print(f"Selected PID: {process_info['pid']}")
```

---

## 📊 3. System Info Panel Widget

**File:** `src/ui/widgets/system_info.py`

### Features

#### 📈 Real-Time System Metrics
- **CPU Usage** - Percentage with progress bar
- **Memory Usage** - Percentage with progress bar
- **Disk Usage** - Percentage with progress bar
- **Process Count** - Total running processes
- **System Uptime** - Hours and minutes

#### 🎨 Rich-Style Design
- Box drawing border header
- Text-based progress bars
- Context-aware colors
- Status indicator at bottom

#### 📊 Progress Bars
```
💻 CPU Usage
   45.2% ████████████░░░░░░░░
```

Uses Unicode block characters:
- `█` - Filled (used portion)
- `░` - Empty (free portion)

#### 🎨 Color Coding
- **Green** (`< 50%`): Healthy
- **Bright Green** (`50-75%`): Moderate
- **Yellow** (`75-90%`): Warning
- **Red** (`> 90%`): Critical

### Visual Layout
```
╔═══════════════════════════════╗
║    📊 SYSTEM INFORMATION     ║
╚═══════════════════════════════╝

💻 CPU Usage
   45.2% ████████████░░░░░░░░

🧠 Memory Usage
   62.1% ███████████████░░░░░

💾 Disk Usage
   78.5% █████████████████░░░

⚙️  Processes
   142 running

⏱️  System Uptime
   12h 34m

╭───────────────────────────────╮
│  🟢 All Systems Operational  │
╰───────────────────────────────╯
```

### Implementation
```python
from src.ui.widgets.system_info import SystemInfoPanel

# Create panel
panel = SystemInfoPanel(refresh_rate=2.0)

# Auto-refreshes every 2 seconds
# Displays real-time metrics with color coding
```

---

## 🔄 4. View Switching System

### Architecture

The view switching system allows dynamic content replacement in the main application without full app restart.

#### Components

**1. View Container** (`#view-container`)
- Houses all switchable views
- Transparent background
- Full width/height

**2. Views** (`.view` class)
- Individual view widgets
- Can be any Textual widget
- Auto-sized to container

**3. View Factory** (`_create_view_widget()`)
- Creates view instances on demand
- Lazy loading for performance
- Centralized view configuration

### Supported Views

| View ID | Widget | Description |
|---------|--------|-------------|
| `welcome` | Container + Label | Welcome screen (default) |
| `files` | FileBrowser | File navigation |
| `processes` | ProcessMonitor | Process monitoring |
| `sysinfo` | SystemInfoPanel | System metrics |
| `terminal` | (Coming soon) | Terminal emulator |
| `editor` | (Coming soon) | Code editor |

### View Switching API

```python
class MatrixOS(App):
    def switch_view(self, view_name: str, widget=None) -> None:
        """
        Switch to a different view.

        Args:
            view_name: View identifier ("files", "processes", etc.)
            widget: Optional pre-created widget
        """
        # Get container
        view_container = self.query_one("#view-container")

        # Remove current views
        for child in view_container.children:
            child.remove()

        # Create and mount new view
        if widget is None:
            widget = self._create_view_widget(view_name)

        if widget:
            view_container.mount(widget)
            self.current_view = view_name
```

### Usage Example

```python
# From sidebar buttons
def on_button_pressed(self, event: Button.Pressed):
    if event.button.id == "btn_files":
        self.switch_view("files")
    elif event.button.id == "btn_processes":
        self.switch_view("processes")
    elif event.button.id == "btn_sysinfo":
        self.switch_view("sysinfo")
```

---

## 🎨 5. Integrated Theme Updates

All Phase 2 widgets use the Rich-inspired theme from Phase 1:

### Common Theme Elements

```css
/* Pure black backgrounds */
background: #000000;

/* Semi-transparent green overlays */
background: rgba(0, 20, 0, 0.8);

/* Rounded borders (Rich-style) */
border: round #00FF00;

/* Heavy borders on focus */
border: heavy #00FF00;

/* Matrix green color palette */
color: #00FF00;        /* Primary */
color: #00AA00;        /* Dim */
color: #FFFFFF;        /* Bright/focus */
```

### View-Specific Styles

```css
#file-browser-view {
    background: rgba(0, 20, 0, 0.8);
}

#process-monitor-view {
    background: rgba(0, 20, 0, 0.8);
}

#system-info-view {
    background: rgba(0, 20, 0, 0.8);
}

SystemInfoPanel {
    background: rgba(0, 20, 0, 0.8);
    border: round #00FF00;
    padding: 2;
}
```

---

## 🚀 How to Use

### Navigation

#### Keyboard Shortcuts
- **F1** - Toggle Matrix rain effect
- **Ctrl+Q** - Quit application
- **Ctrl+F** - Open file browser (future)
- **Ctrl+P** - Open process monitor (future)

#### Sidebar Buttons
Click any sidebar button to switch views:
- **📁 File Browser** - Navigate filesystem
- **📊 Process Monitor** - View running processes
- **📊 System Info** - System metrics dashboard
- **🎨 Matrix Effects** - Toggle rain effect

### File Browser Operations
- **Arrow Keys** - Navigate tree
- **Enter** - Expand/collapse directories
- **Click** - Select files/folders
- **H** - Toggle hidden files (future)

### Process Monitor Operations
- **Arrow Keys** - Select process
- **R** - Refresh manually (future)
- **S** - Change sort order (future)
- Auto-refreshes every 2 seconds

---

## 📊 Statistics

### Code Additions

| File | Lines Added | Description |
|------|-------------|-------------|
| `file_browser.py` | ~250 | Complete file browser |
| `process_monitor.py` | ~250 | Process monitoring |
| `system_info.py` | ~130 | System metrics panel |
| `app.py` | +~80 | View switching system |
| `matrix.tcss` | +~30 | View styling |
| **Total** | **~740** | **Phase 2 additions** |

### Features Implemented

✅ **3 Major Widgets** - Fully functional
✅ **View Switching** - Dynamic content loading
✅ **Rich Integration** - Consistent theming
✅ **Auto-Refresh** - Live data updates
✅ **Event System** - Message passing
✅ **Error Handling** - Graceful degradation

---

## 🎯 Success Metrics

### Functionality
- ✅ File browser loads and navigates directories
- ✅ Process monitor displays live data
- ✅ System info shows real-time metrics
- ✅ View switching works seamlessly
- ✅ All widgets auto-refresh correctly

### User Experience
- ✅ Smooth transitions between views
- ✅ Consistent Rich-style theming
- ✅ Informative status messages
- ✅ Responsive keyboard navigation
- ✅ Clear visual feedback

### Code Quality
- ✅ Clean widget separation
- ✅ Reusable components
- ✅ Comprehensive error handling
- ✅ Logging for debugging
- ✅ Type hints throughout

---

## 🔮 Future Enhancements (Phase 3)

### Planned Features

#### Terminal Emulator
- [ ] PTY-based terminal widget
- [ ] Full shell integration
- [ ] Command history
- [ ] Copy/paste support

#### Code Editor
- [ ] Syntax highlighting
- [ ] Multiple language support
- [ ] Line numbers
- [ ] Search/replace

#### Enhanced Features
- [ ] File browser: Create/delete files
- [ ] Process monitor: Kill processes
- [ ] System info: More detailed metrics
- [ ] View tabs: Multiple views open
- [ ] Split panes: Side-by-side views

---

## 🐛 Known Issues

### Current Limitations

1. **Terminal Widget** - Not yet implemented
2. **Code Editor** - Not yet implemented
3. **File Operations** - Read-only (no create/delete/edit)
4. **Process Control** - View-only (no kill/pause)
5. **Keyboard Shortcuts** - Limited (Ctrl+F, Ctrl+P not connected)

These will be addressed in Phase 3.

---

## 🧪 Testing

### Manual Testing Checklist

```bash
# Launch Matrix OS
python3 -m src.core.app

# Test file browser
1. Click "📁 File Browser"
2. Navigate with arrow keys
3. Expand directories with Enter
4. Verify file icons display correctly

# Test process monitor
1. Click "📊 Process Monitor"
2. Wait for auto-refresh
3. Verify sorting (by CPU)
4. Check color coding on high CPU/memory processes

# Test system info
1. Click "📊 System Info"
2. Verify all metrics display
3. Check progress bars
4. Verify auto-refresh every 2 seconds

# Test view switching
1. Switch between different views
2. Verify smooth transitions
3. Check status bar updates
4. Confirm no crashes/errors
```

---

## 📝 Integration Notes

### Dependencies

All widgets require:
- `textual` >= 0.50.0
- `rich` >= 13.7.0
- `psutil` >= 5.9.0 (for process/system monitoring)

### Import Structure

```python
from src.ui.widgets.file_browser import FileBrowser
from src.ui.widgets.process_monitor import ProcessMonitor
from src.ui.widgets.system_info import SystemInfoPanel
```

### Event Handling

Widgets post messages that can be handled:

```python
# File browser events
@on(FileBrowser.FileSelected)
def handle_file_selected(self, message):
    print(f"File: {message.path}")

@on(FileBrowser.DirectoryChanged)
def handle_dir_changed(self, message):
    print(f"Directory: {message.path}")
```

---

## 🎉 Summary

Phase 2 successfully transforms Matrix OS from a static UI demo into a functional development environment. The implementation maintains the Rich-inspired design from Phase 1 while adding real, usable features.

### Key Achievements

1. **Complete Widget Suite** - File browser, process monitor, system info
2. **View System** - Dynamic content switching without restart
3. **Rich Integration** - Consistent theming across all widgets
4. **Live Updates** - Auto-refreshing data displays
5. **User Feedback** - Context-aware status messages

### Next Steps

Phase 3 will focus on:
- Terminal emulator with PTY support
- Code editor with syntax highlighting
- Advanced features (file operations, process control)
- Plugin architecture
- Performance optimization

---

**Built with 💚 using Python, Textual, and Rich**

*"The Matrix has you... and now you can browse it"* 🟢
