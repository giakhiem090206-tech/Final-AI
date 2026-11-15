"""Colours, fonts and text helpers shared by every part of the Task 1 interface."""
from __future__ import annotations

from typing import Dict, List, Tuple

import pygame

Color = Tuple[int, ...]


class Palette:
    """Every colour of the interface, named by the role it plays."""

    BACKGROUND = (237, 241, 239)
    CARD = (255, 255, 255)
    SHADOW = (219, 226, 222)
    BORDER = (214, 223, 218)
    CONTROL = (243, 246, 244)
    CONTROL_HOVER = (229, 238, 233)
    SELECTED = (232, 243, 237)
    DISABLED = (150, 178, 166)
    TEXT = (27, 39, 47)
    MUTED = (92, 107, 116)
    FAINT = (156, 167, 172)
    ACCENT = (30, 105, 82)
    ACCENT_HOVER = (22, 86, 66)
    ON_ACCENT = (255, 255, 255)

    LIGHT_SQUARE = (241, 233, 213)
    DARK_SQUARE = (104, 143, 117)
    BOARD_EDGE = (52, 74, 63)
    QUEEN = (30, 33, 31)
    QUEEN_EDGE = (255, 250, 236)

    # Status colours: only ever used for a state, always beside an icon or a label.
    GOOD = (28, 128, 84)
    WARNING = (196, 120, 0)
    CRITICAL = (205, 50, 44)

    HOVER_LINE = (236, 150, 12)
    MOVE_ROW = (255, 214, 102)
    BEST_VALUE = (60, 175, 110)

    # Categorical series, in their fixed order (validated colour-blind-safe for three series).
    SERIES = ((42, 120, 214), (235, 104, 52), (27, 175, 122))


def blend(color: Color, background: Color, amount: float) -> Color:
    """`amount` of `color` over `background` (0 gives the background, 1 the colour)."""
    return tuple(round(c * amount + b * (1 - amount)) for c, b in zip(color[:3], background[:3]))


class Fonts:
    """System fonts that cover Vietnamese on Windows (Segoe UI) and macOS (Arial)."""

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
    while text and text_width(text + "…", size, bold) > width:
        text = text[:-1]
    return text.rstrip() + "…"


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


def draw_paragraph(surface: pygame.Surface, text: str, x: int, y: int, width: int, size: int = 14,
                   color: Color = Palette.MUTED, max_lines: int = 99, line_height: int = 0) -> int:
    """Draw wrapped text and return the y below it."""
    line_height = line_height or Fonts.get(size).get_linesize() + 1
    lines = wrap_text(text, width, size)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fit_text(lines[-1] + " …", width, size)
    for index, line in enumerate(lines):
        draw_text(surface, line, (x, y + index * line_height), size, color)
    return y + len(lines) * line_height


def dashed_line(surface: pygame.Surface, color: Color, start: Tuple[int, int], end: Tuple[int, int],
                dash: int = 3, gap: int = 3) -> None:
    """A horizontal or vertical dashed line from `start` to `end`."""
    (x0, y0), (x1, y1) = start, end
    horizontal = y0 == y1
    first, last = (x0, x1) if horizontal else (y0, y1)
    for a in range(first, last, dash + gap):
        b = min(last, a + dash - 1)
        pygame.draw.line(surface, color, (a, y0) if horizontal else (x0, a), (b, y0) if horizontal else (x0, b))
