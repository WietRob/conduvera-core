"""Accessibility smoke for the Activity workspace (QUALITY-GATE).

Checks the delivered activity.html exposes semantic, keyboard-accessible
structure: nav with filter buttons, section headings, buttons with labels,
and that no interactive element relies solely on hover.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_UI = Path(__file__).resolve().parent.parent / "conduvera" / "ui" / "activity.html"


class TestAccessibilitySmoke:
    """Semantic + keyboard-accessible workspace shell."""

    @pytest.fixture(scope="class")
    def html(self):
        assert _UI.is_file(), f"{_UI} fehlt"
        return _UI.read_text(encoding="utf-8")

    def test_semantic_nav_filter(self, html):
        assert '<nav' in html
        assert 'class="filter"' in html
        # filter buttons with data-state labels, keyboard-activatable (button)
        assert '<button' in html

    def test_buttons_have_visible_labels(self, html):
        # no empty buttons (all carry text)
        btns = re.findall(r"<button[^>]*>([^<]*)</button>", html)
        assert btns, "keine Buttons"
        assert all(b.strip() for b in btns), "leerer Button ohne Label"

    def test_keyboard_activation(self, html):
        # interactive controls are <button> (natively keyboard-focusable);
        # evidence links are created dynamically via createElement('a')
        assert "<button" in html
        assert 'createElement("a")' in html or 'createElement(\'a\')' in html
        # no hover-only gating: filters are buttons (tab-focusable)
        assert 'onmouseover' not in html

    def test_no_aria_misuse(self, html):
        # any aria attributes present must include a label/role basis
        if "aria-" in html:
            assert "aria-label" in html or "role=" in html

    def test_semantic_sections(self, html):
        # section titles are heading-ish (div.section-title) — present
        assert "section-title" in html
        # main landmark
        assert "<main" in html
