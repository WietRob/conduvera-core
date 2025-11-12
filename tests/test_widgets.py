"""Tests for Matrix OS widgets."""
import pytest
from pathlib import Path
from textual.app import App


# Import widgets - we'll test basic initialization
try:
    from src.ui.widgets.matrix_rain import MatrixRain
    from src.ui.widgets.file_browser import FileBrowser
    from src.ui.widgets.process_monitor import ProcessMonitor
    from src.ui.widgets.code_editor import CodeEditor
    from src.ui.widgets.terminal import Terminal
except ImportError as e:
    pytest.skip(f"Could not import widgets: {e}", allow_module_level=True)


class TestMatrixRain:
    """Test Matrix Rain widget."""

    def test_initialization(self):
        """Test widget can be initialized."""
        widget = MatrixRain()
        assert widget is not None
        assert widget.rain_active == True

    def test_char_sets(self):
        """Test different character sets."""
        for char_set in ["katakana", "ascii", "mixed", "custom"]:
            widget = MatrixRain(char_set=char_set)
            assert widget.char_set is not None

    def test_random_char(self):
        """Test random character generation."""
        widget = MatrixRain()
        char = widget.random_char()
        assert isinstance(char, str)
        assert len(char) == 1


class TestFileBrowser:
    """Test File Browser widget."""

    def test_initialization(self):
        """Test widget can be initialized."""
        widget = FileBrowser()
        assert widget is not None

    def test_with_path(self):
        """Test initialization with specific path."""
        widget = FileBrowser(root_path=Path.home())
        assert widget.root_path == Path.home()

    def test_get_file_icon(self):
        """Test file icon detection."""
        widget = FileBrowser()

        # Test various file types
        assert widget.get_file_icon(Path("/test/file.py")) == "🐍"
        assert widget.get_file_icon(Path("/test/file.js")) == "📜"
        assert widget.get_file_icon(Path("/test/file.txt")) == "📄"


class TestProcessMonitor:
    """Test Process Monitor widget."""

    def test_initialization(self):
        """Test widget can be initialized."""
        widget = ProcessMonitor()
        assert widget is not None

    def test_get_processes(self):
        """Test process retrieval."""
        widget = ProcessMonitor()
        processes = widget.get_processes()
        assert isinstance(processes, list)
        assert len(processes) > 0  # Should have at least some processes


class TestCodeEditor:
    """Test Code Editor widget."""

    def test_initialization(self):
        """Test widget can be initialized."""
        widget = CodeEditor()
        assert widget is not None

    def test_detect_language(self):
        """Test language detection."""
        widget = CodeEditor()

        # Test various file extensions
        assert "python" in widget.detect_language(Path("test.py")).lower()
        # Note: detection may vary, just check it returns something
        lang = widget.detect_language(Path("test.txt"))
        assert isinstance(lang, str)

    def test_get_stats(self):
        """Test editor statistics."""
        widget = CodeEditor()
        stats = widget.get_stats()

        assert "lines" in stats
        assert "characters" in stats
        assert "words" in stats
        assert "language" in stats


class TestTerminal:
    """Test Terminal widget."""

    def test_initialization(self):
        """Test widget can be initialized."""
        widget = Terminal()
        assert widget is not None
        assert widget.command_running == False  # Not started yet


# Integration test with Textual app
@pytest.mark.asyncio
async def test_matrix_rain_in_app():
    """Test Matrix Rain widget in Textual app."""

    class TestApp(App):
        def compose(self):
            yield MatrixRain()

    app = TestApp()
    async with app.run_test() as pilot:
        # Widget should be mounted
        rain = app.query_one(MatrixRain)
        assert rain is not None
        assert rain.rain_active == True

        # Should have columns set up
        assert len(rain.columns) > 0
