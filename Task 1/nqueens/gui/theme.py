"""Colours, fonts and text helpers shared by every part of the Task 1 interface."""
from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

Color = Tuple[int, ...]


class Palette:
    """Every colour of the interface, named by the role it plays."""

    BACKGROUND = (232, 232, 232)
    CARD = (255, 255, 255)
    BORDER = (196, 196, 196)
    STATUS_BAR = (222, 222, 222)
    CONTROL = (246, 246, 246)
    CONTROL_HOVER = (229, 234, 242)
    DISABLED = (150, 170, 200)
    TEXT = (30, 30, 30)
    MUTED = (96, 96, 96)
    FAINT = (160, 160, 160)
    ACCENT = (42, 92, 160)
    ACCENT_HOVER = (32, 74, 132)
    ON_ACCENT = (255, 255, 255)

    LIGHT_SQUARE = (240, 217, 181)
    DARK_SQUARE = (181, 136, 99)
    BOARD_EDGE = (96, 66, 44)
    QUEEN = (30, 30, 30)
    QUEEN_EDGE = (255, 250, 240)

    GOOD = (30, 125, 60)
    WARNING = (190, 110, 0)
    CRITICAL = (200, 40, 40)

    HOVER_LINE = (42, 92, 160)
    MOVE_ROW = (255, 214, 102)
    BEST_VALUE = (70, 160, 90)

    # Categorical series, in a fixed colour-blind-safe order.
    SERIES = ((42, 120, 214), (235, 104, 52), (27, 175, 122))


class Fonts:
    """System fonts that cover every character used, on Windows (Segoe UI) and macOS (Arial)."""

    FAMILIES = "segoeui,arial,helvetica,dejavusans,liberationsans"
    _cache: Dict[Tuple[int, bool], pygame.font.Font] = {}

    @classmethod
    def get(cls, size: int, bold: bool = False) -> pygame.font.Font:
        key = (size, bold)
        if key not in cls._cache:
            cls._cache[key] = pygame.font.SysFont(cls.FAMILIES, size, bold=bold)
        return cls._cache[key]


_rendered: Dict[Tuple[str, int, Color, bool], pygame.Surface] = {}


def draw_text(surface: pygame.Surface, text: str, position: Tuple[float, float], size: int = 14,
              color: Color = Palette.TEXT, bold: bool = False, anchor: str = "topleft") -> pygame.Rect:
    """Draw one line of text; `anchor` is a pygame.Rect attribute such as "midright".

    Most labels are the same every frame, so rendered lines are cached (the cache is
    emptied when it grows, since counters such as the step number keep changing)."""
    key = (text, size, color, bold)
    image = _rendered.get(key)
    if image is None:
        if len(_rendered) > 2000:
            _rendered.clear()
        image = _rendered[key] = Fonts.get(size, bold).render(text, True, color)
    rect = image.get_rect(**{anchor: (round(position[0]), round(position[1]))})
    surface.blit(image, rect)
    return rect


def text_width(text: str, size: int = 14, bold: bool = False) -> int:
    return Fonts.get(size, bold).size(text)[0]


def fit_text(text: str, width: int, size: int = 14, bold: bool = False) -> str:
    """The text, cut with an ellipsis if it is wider than `width`."""
    if text_width(text, size, bold) <= width:
        return text
    while text and text_width(text + "...", size, bold) > width:
        text = text[:-1]
    return text.rstrip() + "..."


def wrap_text(text: str, width: int, size: int = 14, bold: bool = False) -> List[str]:
    """Split text into lines no wider than `width`, breaking between words."""
    lines: List[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and text_width(candidate, size, bold) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def dashed_line(surface: pygame.Surface, color: Color, start: Tuple[int, int], end: Tuple[int, int],
                dash: int = 3, gap: int = 3) -> None:
    """A horizontal or vertical dashed line from `start` to `end`."""
    (x0, y0), (x1, y1) = start, end
    horizontal = y0 == y1
    first, last = (x0, x1) if horizontal else (y0, y1)
    for a in range(first, last, dash + gap):
        b = min(last, a + dash - 1)
        pygame.draw.line(surface, color, (a, y0) if horizontal else (x0, a), (b, y0) if horizontal else (x0, b))
