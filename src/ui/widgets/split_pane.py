"""Split Pane widget for side-by-side views."""
from textual.widgets import Static
from textual.containers import Horizontal, Container, VerticalScroll
from textual.reactive import reactive
from textual.message import Message
from typing import Optional, Any
from src.utils.logger import logger


class SplitPane(Horizontal):
    """
    Split Pane container for side-by-side views.

    Allows displaying two widgets horizontally (e.g., Editor + Terminal).
    """

    left_ratio = reactive(50)  # Left pane width percentage (0-100)
    divider_visible = reactive(True)

    DEFAULT_CSS = """
    SplitPane {
        height: 100%;
        width: 100%;
        background: rgba(0, 20, 0, 0.8);
        border: round #00FF00;
    }

    SplitPane:focus {
        border: heavy #00FF00;
        background: rgba(0, 30, 0, 0.9);
    }

    .split-left {
        width: 1fr;
        background: rgba(0, 15, 0, 0.7);
        border: round #00AA00;
        padding: 1;
        margin-right: 1;
    }

    .split-right {
        width: 1fr;
        background: rgba(0, 15, 0, 0.7);
        border: round #00AA00;
        padding: 1;
    }

    .split-divider {
        width: 1;
        background: #00FF00;
        color: #00FF00;
    }

    .split-header {
        background: rgba(0, 100, 0, 0.8);
        color: #FFFFFF;
        text-style: bold;
        padding: 1;
        margin-bottom: 1;
        height: 3;
    }
    """

    class PaneChanged(Message):
        """Message sent when pane content changes."""

        def __init__(self, side: str, widget: Any) -> None:
            super().__init__()
            self.side = side
            self.widget = widget

    def __init__(
        self,
        left_widget: Optional[Any] = None,
        right_widget: Optional[Any] = None,
        left_label: str = "Left Pane",
        right_label: str = "Right Pane",
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.left_widget = left_widget
        self.right_widget = right_widget
        self.left_label = left_label
        self.right_label = right_label

    def compose(self):
        """Create split pane layout."""
        # Left pane
        with VerticalScroll(classes="split-left", id="split-left-container"):
            yield Static(
                f"[bold bright_green]╭─ {self.left_label} ──────────────────────╮[/]",
                classes="split-header"
            )
            if self.left_widget:
                yield self.left_widget

        # Divider
        if self.divider_visible:
            yield Static("│\n" * 50, classes="split-divider")

        # Right pane
        with VerticalScroll(classes="split-right", id="split-right-container"):
            yield Static(
                f"[bold bright_green]╭─ {self.right_label} ──────────────────────╮[/]",
                classes="split-header"
            )
            if self.right_widget:
                yield self.right_widget

    def set_left(self, widget: Any, label: Optional[str] = None) -> None:
        """
        Set left pane widget.

        Args:
            widget: Widget to display in left pane
            label: Optional label for the pane
        """
        try:
            left_container = self.query_one("#split-left-container")

            # Remove existing widgets except header
            for child in list(left_container.children)[1:]:  # Skip header
                child.remove()

            # Update label if provided
            if label:
                self.left_label = label
                header = left_container.query_one(".split-header")
                header.update(f"[bold bright_green]╭─ {label} ──────────────────────╮[/]")

            # Mount new widget
            left_container.mount(widget)
            self.left_widget = widget
            self.post_message(self.PaneChanged("left", widget))
            logger.info(f"Split pane left updated: {label or 'unnamed'}")

        except Exception as e:
            logger.error(f"Error setting left pane: {e}")

    def set_right(self, widget: Any, label: Optional[str] = None) -> None:
        """
        Set right pane widget.

        Args:
            widget: Widget to display in right pane
            label: Optional label for the pane
        """
        try:
            right_container = self.query_one("#split-right-container")

            # Remove existing widgets except header
            for child in list(right_container.children)[1:]:  # Skip header
                child.remove()

            # Update label if provided
            if label:
                self.right_label = label
                header = right_container.query_one(".split-header")
                header.update(f"[bold bright_green]╭─ {label} ──────────────────────╮[/]")

            # Mount new widget
            right_container.mount(widget)
            self.right_widget = widget
            self.post_message(self.PaneChanged("right", widget))
            logger.info(f"Split pane right updated: {label or 'unnamed'}")

        except Exception as e:
            logger.error(f"Error setting right pane: {e}")

    def set_ratio(self, left_percent: int) -> None:
        """
        Set split ratio.

        Args:
            left_percent: Percentage width for left pane (0-100)
        """
        if 0 <= left_percent <= 100:
            self.left_ratio = left_percent
            logger.info(f"Split ratio set to {left_percent}:{100 - left_percent}")
        else:
            logger.warning(f"Invalid split ratio: {left_percent}")

    def toggle_divider(self) -> None:
        """Toggle divider visibility."""
        self.divider_visible = not self.divider_visible
        try:
            divider = self.query_one(".split-divider")
            divider.display = self.divider_visible
        except Exception:
            pass

    def swap_panes(self) -> None:
        """Swap left and right pane contents."""
        temp_widget = self.left_widget
        temp_label = self.left_label

        self.set_left(self.right_widget, self.right_label)
        self.set_right(temp_widget, temp_label)

        logger.info("Split panes swapped")


class EditorTerminalSplit(SplitPane):
    """
    Specialized split pane for Editor + Terminal side-by-side.

    Pre-configured for optimal code editing workflow.
    """

    DEFAULT_CSS = """
    EditorTerminalSplit {
        height: 100%;
        width: 100%;
        background: rgba(0, 20, 0, 0.8);
        border: round #00FF00;
    }

    EditorTerminalSplit .split-left {
        width: 60%;  /* Editor gets more space */
    }

    EditorTerminalSplit .split-right {
        width: 40%;  /* Terminal gets less space */
    }
    """

    def __init__(
        self,
        editor_widget: Optional[Any] = None,
        terminal_widget: Optional[Any] = None,
        **kwargs
    ) -> None:
        super().__init__(
            left_widget=editor_widget,
            right_widget=terminal_widget,
            left_label="✏️  Code Editor",
            right_label="💻 Terminal",
            **kwargs
        )


class TriplePane(Container):
    """
    Triple pane container for three-way splits.

    Layout: Left | Center | Right
    """

    DEFAULT_CSS = """
    TriplePane {
        height: 100%;
        width: 100%;
        layout: horizontal;
        background: rgba(0, 20, 0, 0.8);
        border: round #00FF00;
    }

    .triple-left {
        width: 1fr;
        background: rgba(0, 15, 0, 0.7);
        border: round #00AA00;
        padding: 1;
        margin-right: 1;
    }

    .triple-center {
        width: 2fr;  /* Center gets double width */
        background: rgba(0, 15, 0, 0.7);
        border: round #00AA00;
        padding: 1;
        margin-right: 1;
    }

    .triple-right {
        width: 1fr;
        background: rgba(0, 15, 0, 0.7);
        border: round #00AA00;
        padding: 1;
    }
    """

    def __init__(
        self,
        left_widget: Optional[Any] = None,
        center_widget: Optional[Any] = None,
        right_widget: Optional[Any] = None,
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.left_widget = left_widget
        self.center_widget = center_widget
        self.right_widget = right_widget

    def compose(self):
        """Create triple pane layout."""
        with VerticalScroll(classes="triple-left", id="triple-left-container"):
            if self.left_widget:
                yield self.left_widget

        with VerticalScroll(classes="triple-center", id="triple-center-container"):
            if self.center_widget:
                yield self.center_widget

        with VerticalScroll(classes="triple-right", id="triple-right-container"):
            if self.right_widget:
                yield self.right_widget


class QuadPane(Container):
    """
    Quad pane container for four-way splits.

    Layout:
    ┌─────┬─────┐
    │  TL │  TR │
    ├─────┼─────┤
    │  BL │  BR │
    └─────┴─────┘
    """

    DEFAULT_CSS = """
    QuadPane {
        height: 100%;
        width: 100%;
        layout: grid;
        grid-size: 2 2;
        grid-gutter: 1;
        background: rgba(0, 20, 0, 0.8);
        border: round #00FF00;
    }

    .quad-pane {
        background: rgba(0, 15, 0, 0.7);
        border: round #00AA00;
        padding: 1;
    }
    """

    def __init__(
        self,
        top_left: Optional[Any] = None,
        top_right: Optional[Any] = None,
        bottom_left: Optional[Any] = None,
        bottom_right: Optional[Any] = None,
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.top_left = top_left
        self.top_right = top_right
        self.bottom_left = bottom_left
        self.bottom_right = bottom_right

    def compose(self):
        """Create quad pane layout."""
        with VerticalScroll(classes="quad-pane", id="quad-top-left"):
            if self.top_left:
                yield self.top_left

        with VerticalScroll(classes="quad-pane", id="quad-top-right"):
            if self.top_right:
                yield self.top_right

        with VerticalScroll(classes="quad-pane", id="quad-bottom-left"):
            if self.bottom_left:
                yield self.bottom_left

        with VerticalScroll(classes="quad-pane", id="quad-bottom-right"):
            if self.bottom_right:
                yield self.bottom_right
