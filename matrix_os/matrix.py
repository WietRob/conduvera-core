from __future__ import annotations
import os
import random
import shutil
import string
import sys
import time
from typing import List
from rich.console import Console
from rich.text import Text
from rich.live import Live
from .colors import console

MATRIX_CHARS = (
    "ｦｧｨｩｪｫｬｭｮｯｰｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
)


def run_matrix_rain(duration: float = 10.0, speed: float = 0.05) -> None:
    width = shutil.get_terminal_size((80, 24)).columns
    height = shutil.get_terminal_size((80, 24)).lines - 2
    columns = width
    drops = [random.randint(0, height) for _ in range(columns)]

    def frame() -> Text:
        text = Text()
        for y in range(height):
            line_chars: List[str] = []
            for x in range(columns):
                if drops[x] == y:
                    ch = random.choice(MATRIX_CHARS)
                    style = "bold #00ff41"
                elif drops[x] > y:
                    ch = random.choice(MATRIX_CHARS)
                    style = "green3"
                else:
                    ch = " "
                    style = ""
                line_chars.append(ch)
            text.append("".join(line_chars), style)
            if y != height - 1:
                text.append("\n")
        return text

    start = time.time()
    console.clear()
    with Live(frame(), console=console, refresh_per_second=int(1/max(speed, 0.01))):
        while time.time() - start < duration:
            for i in range(columns):
                if random.random() > 0.975:
                    drops[i] = 0
                drops[i] = (drops[i] + 1) % (height if height > 0 else 1)
            time.sleep(speed)
    console.show_cursor(True)
