"""Matrix Digital Rain effect widget."""
from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text
from rich.style import Style
import random
import time
from typing import List, Dict, Any


class MatrixRain(Widget):
    """
    Matrix Digital Rain effect widget.

    Simulates the iconic falling green characters from The Matrix.
    """

    rain_active = reactive(True)
    density = reactive(0.05)
    speed_multiplier = reactive(1.0)

    CHAR_SETS = {
        "katakana": "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜｦﾝ",
        "ascii": "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%^&*",
        "mixed": "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉ0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "custom": "01",
    }

    DEFAULT_CSS = """
    MatrixRain {
        background: $panel-darken-3;
        color: $success;
    }
    """

    def __init__(
        self,
        char_set: str = "mixed",
        fps: int = 30,
        speed_min: float = 0.5,
        speed_max: float = 2.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.char_set = self.CHAR_SETS.get(char_set, self.CHAR_SETS["mixed"])
        self.fps = fps
        self.speed_min = speed_min
        self.speed_max = speed_max
        self.columns: List[Dict[str, Any]] = []
        self.last_update = time.time()

    def on_mount(self) -> None:
        """Initialize rain when widget is mounted."""
        self.setup_columns()
        self.set_interval(1 / self.fps, self.update_rain)

    def setup_columns(self) -> None:
        """Setup column data structures."""
        width = max(1, self.size.width)
        self.columns = [
            {
                "drops": [],
                "speed": random.uniform(self.speed_min, self.speed_max),
                "next_drop": random.uniform(0, 2.0),
            }
            for _ in range(width)
        ]

    def random_char(self) -> str:
        """Get random character from character set."""
        return random.choice(self.char_set)

    def update_rain(self) -> None:
        """Update rain animation state."""
        if not self.rain_active:
            return

        current_time = time.time()
        dt = (current_time - self.last_update) * self.speed_multiplier
        self.last_update = current_time

        height = max(1, self.size.height)
        width = max(1, self.size.width)

        # Resize columns if terminal size changed
        if len(self.columns) != width:
            self.setup_columns()

        for col in self.columns:
            col["next_drop"] -= dt

            # Start new drop
            if col["next_drop"] <= 0:
                col["drops"].append(
                    {
                        "y": 0.0,
                        "chars": [self.random_char() for _ in range(random.randint(5, 20))],
                        "head_brightness": 1.0,
                    }
                )
                col["next_drop"] = random.uniform(0.5, 3.0) / self.density

            # Update existing drops
            for drop in col["drops"][:]:
                drop["y"] += col["speed"] * dt

                # Remove drops that are off-screen
                if drop["y"] > height + len(drop["chars"]):
                    col["drops"].remove(drop)

        self.refresh()

    def get_color_style(self, brightness: float) -> Style:
        """
        Get Rich Style based on brightness level.

        Args:
            brightness: Value from 0.0 (darkest) to 1.0 (brightest)

        Returns:
            Rich Style object
        """
        if brightness > 0.9:
            # Head - bright white/green
            return Style(color="#FFFFFF", bold=True)
        elif brightness > 0.7:
            # Near head - bright green
            return Style(color="#00FF00", bold=True)
        elif brightness > 0.5:
            # Middle - medium green
            return Style(color="#00DD00")
        elif brightness > 0.3:
            # Fading - darker green
            return Style(color="#00AA00")
        elif brightness > 0.1:
            # Tail - dark green
            return Style(color="#006600")
        else:
            # Very faint
            return Style(color="#003300", dim=True)

    def render(self) -> Text:
        """Render the matrix rain effect."""
        height = self.size.height
        width = self.size.width

        # Create 2D screen buffer
        screen: List[List[str]] = [[" " for _ in range(width)] for _ in range(height)]
        brightness: List[List[float]] = [[0.0 for _ in range(width)] for _ in range(height)]

        # Draw all drops
        for col_idx, col in enumerate(self.columns):
            if col_idx >= width:
                break

            for drop in col["drops"]:
                y_start = int(drop["y"])
                for char_idx, char in enumerate(drop["chars"]):
                    y = y_start - char_idx
                    if 0 <= y < height:
                        screen[y][col_idx] = char
                        # Calculate brightness based on position in drop
                        char_brightness = max(0.0, 1.0 - (char_idx / len(drop["chars"])))
                        # Head is brightest
                        if char_idx == 0:
                            char_brightness = 1.0
                        brightness[y][col_idx] = char_brightness

        # Convert to Rich Text with colors
        text = Text()
        for y in range(height):
            for x in range(width):
                char = screen[y][x]
                style = self.get_color_style(brightness[y][x])
                text.append(char, style=style)
            if y < height - 1:  # Don't add newline on last row
                text.append("\n")

        return text

    def action_toggle_rain(self) -> None:
        """Toggle rain on/off."""
        self.rain_active = not self.rain_active

    def action_increase_speed(self) -> None:
        """Increase rain speed."""
        self.speed_multiplier = min(5.0, self.speed_multiplier + 0.5)

    def action_decrease_speed(self) -> None:
        """Decrease rain speed."""
        self.speed_multiplier = max(0.1, self.speed_multiplier - 0.5)
