#!/usr/bin/env python3
"""
Curses-based Matrix OS Demo

Alternative implementation using Python's curses library for
low-level terminal control with minimal dependencies.
"""
import curses
import time
import random
from collections import deque
from typing import List, Tuple


class MatrixRainColumn:
    """Represents a single column of matrix rain."""

    def __init__(self, x: int, height: int, speed: float):
        self.x = x
        self.height = height
        self.speed = speed
        self.y = random.randint(-20, 0)
        self.chars = deque(maxlen=random.randint(5, 20))
        self.next_update = 0

    def update(self, dt: float) -> None:
        """Update column position."""
        self.next_update -= dt
        if self.next_update <= 0:
            self.y += 1
            if self.y > self.height + len(self.chars):
                self.y = random.randint(-20, -5)
                self.chars.clear()

            # Add new character
            if 0 <= self.y < self.height:
                char = random.choice("ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉ0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                self.chars.append(char)

            self.next_update = self.speed

    def get_chars_at_positions(self) -> List[Tuple[int, str, int]]:
        """Get characters and their positions with brightness."""
        result = []
        for i, char in enumerate(self.chars):
            y_pos = self.y - i
            if 0 <= y_pos < self.height:
                # Brightness: 0 (head) is brightest
                brightness = i
                result.append((y_pos, char, brightness))
        return result


class CursesMatrixOS:
    """Matrix OS implementation using curses."""

    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.running = True
        self.show_menu = True
        self.columns: List[MatrixRainColumn] = []

        # Setup curses
        curses.curs_set(0)  # Hide cursor
        curses.noecho()
        curses.cbreak()
        stdscr.keypad(True)
        stdscr.nodelay(True)  # Non-blocking input
        stdscr.timeout(50)  # 50ms timeout for getch()

        # Setup colors
        self._setup_colors()

    def _setup_colors(self) -> None:
        """Setup color pairs for matrix effect."""
        curses.start_color()
        curses.use_default_colors()

        # Define color pairs
        # Pair 1: Bright green (head)
        curses.init_pair(1, curses.COLOR_WHITE, -1)
        # Pair 2: Bright green
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        # Pair 3: Medium green
        curses.init_pair(3, curses.COLOR_GREEN, -1)
        # Pair 4: Dark green
        curses.init_pair(4, curses.COLOR_GREEN, -1)
        # Pair 5: Very dark green
        curses.init_pair(5, curses.COLOR_GREEN, -1)
        # Pair 6: UI elements
        curses.init_pair(6, curses.COLOR_GREEN, curses.COLOR_BLACK)

    def get_color_pair(self, brightness: int) -> int:
        """Get color pair based on brightness."""
        if brightness == 0:
            return curses.color_pair(1) | curses.A_BOLD
        elif brightness == 1:
            return curses.color_pair(2) | curses.A_BOLD
        elif brightness < 4:
            return curses.color_pair(3)
        elif brightness < 8:
            return curses.color_pair(4)
        else:
            return curses.color_pair(5) | curses.A_DIM

    def setup_columns(self) -> None:
        """Setup matrix rain columns."""
        height, width = self.stdscr.getmaxyx()
        self.columns = [
            MatrixRainColumn(x, height - 5, random.uniform(0.1, 0.3)) for x in range(width)
        ]

    def draw_header(self) -> None:
        """Draw header bar."""
        height, width = self.stdscr.getmaxyx()

        # Header background
        header_text = " MATRIX OS - Curses Demo "
        header_text = header_text.center(width)[:width]

        self.stdscr.addstr(0, 0, header_text, curses.color_pair(6) | curses.A_BOLD)

    def draw_footer(self) -> None:
        """Draw footer with controls."""
        height, width = self.stdscr.getmaxyx()

        controls = " Q:Quit | M:Menu | R:Restart "
        footer_text = controls.center(width)[:width]

        try:
            self.stdscr.addstr(
                height - 1, 0, footer_text, curses.color_pair(6) | curses.A_BOLD
            )
        except curses.error:
            pass  # Ignore errors on last line

    def draw_menu(self) -> None:
        """Draw menu panel."""
        height, width = self.stdscr.getmaxyx()

        menu_items = [
            "╔════════════════════════════╗",
            "║      MATRIX OS MENU        ║",
            "╠════════════════════════════╣",
            "║                            ║",
            "║  1. Terminal               ║",
            "║  2. File Browser           ║",
            "║  3. Process Monitor        ║",
            "║  4. Code Editor            ║",
            "║                            ║",
            "║  Q. Quit                   ║",
            "║  M. Toggle Menu            ║",
            "║                            ║",
            "╚════════════════════════════╝",
        ]

        start_y = (height - len(menu_items)) // 2
        start_x = (width - 32) // 2

        for i, line in enumerate(menu_items):
            try:
                self.stdscr.addstr(
                    start_y + i, start_x, line, curses.color_pair(2) | curses.A_BOLD
                )
            except curses.error:
                pass

    def draw_matrix_rain(self) -> None:
        """Draw matrix rain effect."""
        height, width = self.stdscr.getmaxyx()

        # Update and draw all columns
        for column in self.columns:
            column.update(0.05)  # Fixed delta time

            for y, char, brightness in column.get_chars_at_positions():
                if 1 < y < height - 2 and 0 <= column.x < width:  # Skip header/footer
                    try:
                        color = self.get_color_pair(brightness)
                        self.stdscr.addstr(y, column.x, char, color)
                    except curses.error:
                        pass  # Ignore errors at screen edges

    def draw_status_panel(self) -> None:
        """Draw status information panel."""
        height, width = self.stdscr.getmaxyx()

        panel_width = 40
        panel_height = 10
        start_x = width - panel_width - 2
        start_y = 2

        if start_x < 0 or width < 50:  # Don't show on small screens
            return

        # Draw panel border
        try:
            for y in range(panel_height):
                if y == 0:
                    self.stdscr.addstr(
                        start_y + y,
                        start_x,
                        "┌" + "─" * (panel_width - 2) + "┐",
                        curses.color_pair(2),
                    )
                elif y == panel_height - 1:
                    self.stdscr.addstr(
                        start_y + y,
                        start_x,
                        "└" + "─" * (panel_width - 2) + "┘",
                        curses.color_pair(2),
                    )
                else:
                    self.stdscr.addstr(start_y + y, start_x, "│", curses.color_pair(2))
                    self.stdscr.addstr(
                        start_y + y, start_x + panel_width - 1, "│", curses.color_pair(2)
                    )

            # Panel title
            title = " SYSTEM STATUS "
            self.stdscr.addstr(
                start_y, start_x + (panel_width - len(title)) // 2, title, curses.color_pair(2) | curses.A_BOLD
            )

            # Status info
            info_lines = [
                f"  Status: {'ONLINE' if self.running else 'OFFLINE'}",
                f"  Terminal: {width}x{height}",
                f"  Rain Columns: {len(self.columns)}",
                f"  Menu: {'Visible' if self.show_menu else 'Hidden'}",
            ]

            for i, line in enumerate(info_lines):
                self.stdscr.addstr(
                    start_y + 2 + i, start_x + 2, line[:panel_width - 4], curses.color_pair(3)
                )

        except curses.error:
            pass

    def handle_input(self) -> None:
        """Handle keyboard input."""
        try:
            key = self.stdscr.getch()

            if key == ord("q") or key == ord("Q"):
                self.running = False
            elif key == ord("m") or key == ord("M"):
                self.show_menu = not self.show_menu
            elif key == ord("r") or key == ord("R"):
                self.setup_columns()
            elif key == curses.KEY_RESIZE:
                self.setup_columns()

        except curses.error:
            pass

    def run(self) -> None:
        """Main loop."""
        self.setup_columns()

        while self.running:
            # Clear screen
            self.stdscr.erase()

            # Draw components
            self.draw_matrix_rain()
            self.draw_header()
            self.draw_footer()

            if not self.show_menu:
                self.draw_status_panel()
            else:
                self.draw_menu()

            # Refresh screen
            self.stdscr.refresh()

            # Handle input
            self.handle_input()

            # Small delay
            time.sleep(0.05)


def main(stdscr):
    """Main entry point for curses app."""
    app = CursesMatrixOS(stdscr)
    app.run()


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        print("\n\033[92mMatrix OS terminated\033[0m")
