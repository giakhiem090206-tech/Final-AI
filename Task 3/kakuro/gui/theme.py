"""Colours and text helpers."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pygame

Color = Tuple[int, int, int]


# The look of kakuros.com: a white page, grey blocked cells and white entry cells, the pale blue
# of its selected size link for the run being looked at, green for digits that are in order and red
# for those that are not. Its green (#00cc00) is deepened a little so that it reads on white.
_CLASSIC = dict(
    BACKGROUND=(255, 255, 255), PANEL=(240, 240, 255), CARD=(222, 224, 244), CARD_HOVER=(204, 208, 236),
    BORDER=(190, 192, 222), TEXT=(51, 51, 51), MUTED=(100, 100, 120), FAINT=(150, 150, 170),
    BLACK_CELL=(226, 226, 226), WHITE_CELL=(255, 255, 255), GRID=(60, 60, 70),
    DIGIT=(120, 124, 150), DETERMINED=(28, 96, 196), ASSIGNED=(40, 40, 40),
    RUN_FILL=(223, 248, 255), RUN_CLUE=(52, 120, 208), SELECT=(232, 150, 20),
    GOOD=(0, 160, 0), BAD=(220, 0, 0), BAD_FILL=(255, 220, 220), PRUNED=(220, 30, 30), ACCENT=(51, 51, 102),
    HEAT=((255, 255, 255), (255, 248, 214), (255, 238, 180), (255, 224, 140)),
)
PALETTES = {"classic": _CLASSIC}


class Theme:
    """The colours in use; the screens read them when they draw."""

    name = "classic"
    BACKGROUND: Color
    PANEL: Color
    CARD: Color
    CARD_HOVER: Color
    BORDER: Color
    TEXT: Color
    MUTED: Color
    FAINT: Color
    BLACK_CELL: Color
    WHITE_CELL: Color
    GRID: Color
    DIGIT: Color
    DETERMINED: Color
    ASSIGNED: Color
    RUN_FILL: Color
    RUN_CLUE: Color
    SELECT: Color
    GOOD: Color
    BAD: Color
    BAD_FILL: Color
    PRUNED: Color
    ACCENT: Color
    HEAT: Tuple[Color, Color, Color, Color]

    @classmethod
    def use(cls, name: str) -> None:
        for key, value in PALETTES[name].items():
            setattr(cls, key, value)
        cls.name = name


Theme.use("classic")


class Fonts:
    _cache: Dict[Tuple[int, bool], pygame.font.Font] = {}

    @classmethod
    def clear(cls) -> None:
        cls._cache.clear()

    @classmethod
    def get(cls, size: int, bold: bool = False) -> pygame.font.Font:
        size = size + 1 if size <= 14 else size  # small text is bumped by one point for readability
        key = (size, bold)
        if key not in cls._cache:
            cls._cache[key] = pygame.font.SysFont("arial,helvetica,dejavusans,liberationsans", size, bold=bold)
        return cls._cache[key]


def draw_text(surface: pygame.Surface, text: str, position: Tuple[int, int], size: int = 14,
              color: Optional[Color] = None, bold: bool = False, center: bool = False, right: bool = False) -> pygame.Rect:
    image = Fonts.get(size, bold).render(text, True, Theme.TEXT if color is None else color)
    if center:
        rect = image.get_rect(center=position)
    elif right:
        rect = image.get_rect(topright=position)
    else:
        rect = image.get_rect(topleft=position)
    surface.blit(image, rect)
    return rect


def wrap_text(text: str, size: int, width: int) -> List[str]:
    font = Fonts.get(size)
    lines: List[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if font.size(candidate)[0] <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
