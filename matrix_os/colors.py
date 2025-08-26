from rich.theme import Theme
from rich.console import Console

MATRIX_GREEN = "#00ff41"
MATRIX_DARK = "#003b00"
MATRIX_BG = "#0d0208"

matrix_theme = Theme(
    {
        "matrix.primary": MATRIX_GREEN,
        "matrix.dim": "green3",
        "matrix.bg": MATRIX_BG,
        "matrix.warn": "yellow",
        "matrix.error": "bold red",
        "matrix.ok": "bold #00ff41",
        "matrix.title": "bold #00ff41",
    }
)

console = Console(theme=matrix_theme)
