"""Code editor widget with syntax highlighting."""
from textual.widgets import TextArea
from textual.reactive import reactive
from textual.message import Message
from pathlib import Path
from typing import Optional
from pygments.lexers import get_lexer_for_filename
from pygments.util import ClassNotFound
from src.utils.logger import logger


class CodeEditor(TextArea):
    """
    Code editor widget with syntax highlighting.

    Provides text editing with syntax highlighting for various languages.
    """

    file_path = reactive(None)
    is_modified = reactive(False)
    display_language = reactive("python")

    DEFAULT_CSS = """
    CodeEditor {
        background: rgba(0, 15, 0, 0.9);
        color: #00FF00;
        border: round #00FF00;
        padding: 0 1;
    }

    CodeEditor:focus {
        border: heavy #00FF00;
        background: rgba(0, 20, 0, 0.95);
    }

    CodeEditor > .text-area--cursor {
        background: #00FF00;
        color: #000000;
    }
    """

    class FileSaved(Message):
        """Message sent when file is saved."""

        def __init__(self, path: Path) -> None:
            super().__init__()
            self.path = path

    class FileLoaded(Message):
        """Message sent when file is loaded."""

        def __init__(self, path: Path) -> None:
            super().__init__()
            self.path = path

    def __init__(
        self,
        file_path: Optional[Path] = None,
        language: str = "python",
        theme: str = "monokai",
        **kwargs,
    ) -> None:
        # Textual's TextArea only accepts languages for which tree-sitter grammars
        # are installed in the current environment. Keep the Matrix OS editor usable
        # even when optional grammar packages are absent.
        kwargs.setdefault("language", None)
        super().__init__(**kwargs)
        self.file_path = file_path
        self.display_language = language
        self.theme_name = theme
        self.show_line_numbers = True

        self._apply_text_area_language(language)

        if file_path:
            self.load_file(file_path)

    def detect_language(self, file_path: Path) -> str:
        """
        Detect programming language from file.

        Args:
            file_path: Path to file

        Returns:
            Language name
        """
        try:
            lexer = get_lexer_for_filename(str(file_path))
            return lexer.name.lower()
        except ClassNotFound:
            return "text"

    def load_file(self, file_path: Path) -> bool:
        """
        Load file into editor.

        Args:
            file_path: Path to file to load

        Returns:
            True if successful, False otherwise
        """
        try:
            if not file_path.exists():
                logger.warning(f"File does not exist: {file_path}")
                return False

            if not file_path.is_file():
                logger.warning(f"Not a file: {file_path}")
                return False

            # Read file
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Set content
            self.text = content

            # Detect language
            detected_language = self.detect_language(file_path)
            self.display_language = detected_language
            self._apply_text_area_language(detected_language)

            # Update state
            self.file_path = file_path
            self.is_modified = False

            # Post message
            self.post_message(self.FileLoaded(file_path))

            logger.info(f"Loaded file: {file_path} (language: {self.display_language})")
            return True

        except Exception as e:
            logger.error(f"Failed to load file {file_path}: {e}")
            return False

    def save_file(self, file_path: Optional[Path] = None) -> bool:
        """
        Save editor content to file.

        Args:
            file_path: Path to save to (uses current file_path if None)

        Returns:
            True if successful, False otherwise
        """
        save_path = file_path or self.file_path

        if not save_path:
            logger.warning("No file path specified for save")
            return False

        try:
            # Ensure parent directory exists
            save_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(self.text)

            # Update state
            self.file_path = save_path
            self.is_modified = False

            # Post message
            self.post_message(self.FileSaved(save_path))

            logger.info(f"Saved file: {save_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save file {save_path}: {e}")
            return False

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Handle text changes."""
        self.is_modified = True

    def _apply_text_area_language(self, language: str) -> None:
        """Apply TextArea syntax highlighting when the grammar is available."""

        try:
            self.language = language
        except Exception as e:
            logger.warning(
                "Syntax grammar unavailable for %s; using plain text editing: %s",
                language,
                e,
            )
            self.language = None

    def action_save(self) -> None:
        """Save current file."""
        if self.file_path:
            self.save_file()
        else:
            logger.warning("No file loaded to save")

    def action_save_as(self, file_path: Path) -> None:
        """
        Save file as new path.

        Args:
            file_path: New file path
        """
        self.save_file(file_path)

    def action_reload(self) -> None:
        """Reload file from disk."""
        if self.file_path:
            if self.is_modified:
                logger.warning("File modified, reload cancelled")
                # TODO: Show confirmation dialog
                return
            self.load_file(self.file_path)

    def get_stats(self) -> dict:
        """
        Get editor statistics.

        Returns:
            Dictionary with editor stats
        """
        text = self.text
        return {
            "lines": text.count("\n") + 1,
            "characters": len(text),
            "words": len(text.split()),
            "language": self.display_language,
            "modified": self.is_modified,
            "file": str(self.file_path) if self.file_path else "Untitled",
        }
