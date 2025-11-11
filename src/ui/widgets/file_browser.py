"""File browser widget with tree view."""
from textual.widgets import Tree
from textual.reactive import reactive
from textual.message import Message
from pathlib import Path
from typing import Optional
from src.utils.logger import logger


class FileBrowser(Tree):
    """
    File browser widget with tree view.

    Provides hierarchical file system navigation with expand/collapse.
    """

    current_path = reactive(Path.home())
    show_hidden = reactive(False)

    DEFAULT_CSS = """
    FileBrowser {
        background: $panel;
        color: $text;
        border: solid $success;
        scrollbar-background: $panel-darken-1;
        scrollbar-color: $success;
        padding: 1;
    }

    FileBrowser:focus {
        border: solid $success-lighten-1;
    }

    FileBrowser > .tree--guides {
        color: $success-darken-1;
    }

    FileBrowser > .tree--cursor {
        background: $success-darken-2;
        text-style: bold;
    }
    """

    class FileSelected(Message):
        """Message sent when a file is selected."""

        def __init__(self, path: Path) -> None:
            super().__init__()
            self.path = path

    class DirectoryChanged(Message):
        """Message sent when directory changes."""

        def __init__(self, path: Path) -> None:
            super().__init__()
            self.path = path

    def __init__(
        self,
        root_path: Optional[Path] = None,
        show_hidden: bool = False,
        label: str = "Files",
        **kwargs,
    ) -> None:
        super().__init__(label, **kwargs)
        self.root_path = root_path or Path.home()
        self.show_hidden = show_hidden
        self.path_to_node = {}  # Map paths to tree nodes

    def on_mount(self) -> None:
        """Initialize file browser when mounted."""
        self.load_directory(self.root_path)
        logger.info(f"File browser initialized at: {self.root_path}")

    def get_file_icon(self, path: Path) -> str:
        """
        Get icon for file/directory.

        Args:
            path: Path to get icon for

        Returns:
            Icon string
        """
        if path.is_dir():
            return "📁"
        elif path.is_symlink():
            return "🔗"
        else:
            # File type icons
            suffix = path.suffix.lower()
            icons = {
                ".py": "🐍",
                ".js": "📜",
                ".ts": "📘",
                ".html": "🌐",
                ".css": "🎨",
                ".json": "📋",
                ".yaml": "⚙️",
                ".yml": "⚙️",
                ".md": "📝",
                ".txt": "📄",
                ".sh": "🔧",
                ".jpg": "🖼️",
                ".png": "🖼️",
                ".gif": "🖼️",
                ".pdf": "📕",
                ".zip": "📦",
                ".tar": "📦",
                ".gz": "📦",
            }
            return icons.get(suffix, "📄")

    def load_directory(self, path: Path) -> None:
        """
        Load directory contents into tree.

        Args:
            path: Directory path to load
        """
        try:
            self.clear()
            self.path_to_node = {}

            # Set root node
            root = self.root
            root.label = f"📂 {path.name or str(path)}"
            root.data = {"path": path, "loaded": False}
            self.path_to_node[path] = root

            # Load initial directory
            self._load_directory_contents(root, path)
            root.data["loaded"] = True
            root.expand()

            self.current_path = path
            self.post_message(self.DirectoryChanged(path))

            logger.debug(f"Loaded directory: {path}")

        except Exception as e:
            logger.error(f"Failed to load directory {path}: {e}")
            self.root.label = f"⚠️  Error: {e}"

    def _load_directory_contents(self, node, path: Path) -> None:
        """
        Load contents of a directory into a tree node.

        Args:
            node: Tree node to add children to
            path: Directory path to load
        """
        try:
            # Get directory contents
            items = list(path.iterdir())

            # Filter hidden files if needed
            if not self.show_hidden:
                items = [item for item in items if not item.name.startswith(".")]

            # Sort: directories first, then files, alphabetically
            items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))

            # Add items to tree
            for item in items:
                try:
                    icon = self.get_file_icon(item)
                    label = f"{icon} {item.name}"

                    child_node = node.add(label, data={"path": item, "loaded": False})
                    self.path_to_node[item] = child_node

                    # Allow expansion for directories
                    if item.is_dir():
                        child_node.allow_expand = True

                except PermissionError:
                    node.add(f"🔒 {item.name} (No permission)")
                except Exception as e:
                    logger.warning(f"Error loading {item}: {e}")

        except PermissionError:
            node.add("⚠️  Permission Denied")
        except Exception as e:
            logger.error(f"Error loading directory contents: {e}")
            node.add(f"⚠️  Error: {e}")

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        """
        Handle tree node expansion.

        Lazy-load directory contents when expanded.
        """
        node = event.node
        if node.data and not node.data.get("loaded"):
            path = node.data["path"]
            if path.is_dir():
                # Remove placeholder children
                node.remove_children()
                # Load directory contents
                self._load_directory_contents(node, path)
                node.data["loaded"] = True
                logger.debug(f"Expanded directory: {path}")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """
        Handle tree node selection.

        Post message when file is selected.
        """
        node = event.node
        if node.data:
            path = node.data["path"]
            logger.debug(f"Selected: {path}")

            if path.is_file():
                self.post_message(self.FileSelected(path))
            elif path.is_dir():
                self.current_path = path
                self.post_message(self.DirectoryChanged(path))

    def refresh_current(self) -> None:
        """Refresh current directory view."""
        self.load_directory(self.current_path)

    def go_to_parent(self) -> None:
        """Navigate to parent directory."""
        parent = self.current_path.parent
        if parent != self.current_path:  # Not at root
            self.load_directory(parent)

    def go_to_path(self, path: Path) -> None:
        """
        Navigate to specific path.

        Args:
            path: Path to navigate to
        """
        if path.is_dir():
            self.load_directory(path)
        elif path.is_file():
            self.load_directory(path.parent)
            # TODO: Select the file in the tree

    def toggle_hidden_files(self) -> None:
        """Toggle display of hidden files."""
        self.show_hidden = not self.show_hidden
        self.refresh_current()
        logger.info(f"Hidden files: {'shown' if self.show_hidden else 'hidden'}")

    def get_selected_path(self) -> Optional[Path]:
        """
        Get currently selected path.

        Returns:
            Selected path or None
        """
        if self.cursor_node and self.cursor_node.data:
            return self.cursor_node.data["path"]
        return None
