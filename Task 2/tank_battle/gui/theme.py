"""Colours and text helpers."""
from __future__ import annotations

from typing import Dict, Tuple

import pygame

Color = Tuple[int, int, int]


class Theme:
    BACKGROUND = (18, 20, 26)
    PANEL = (28, 31, 39)
    CARD = (38, 42, 52)
    CARD_HOVER = (50, 55, 68)
    BORDER = (56, 61, 75)
    TEXT = (230, 233, 238)
    MUTED = (150, 157, 170)
    FAINT = (96, 103, 118)
    GROUND_A = (0, 0, 0)  # the black playfield
    WALL_FACE = ((200, 72, 24), (200, 72, 24), (240, 128, 64))  # brick colours, for chips flying off a hit
    # Identity colours of the two players: yellow, as in the arcade original, and blue. Checked
    # with the palette validator of the dataviz guidelines on a black surface: the pair stays
    # apart under colour blindness (worst case 24 on the OKLab scale) and clears 3:1 contrast.
    # Only the yellow is lighter than that tool's band for chart colours, which suits a sprite.
    PLAYERS = ((232, 192, 40), (74, 168, 232))
    PLAYERS_LIGHT = ((252, 232, 128), (172, 220, 252))
    PLAYERS_DARK = ((156, 112, 16), (24, 88, 148))
    GOOD = (84, 190, 120)
    BAD = (226, 84, 84)
    ACCENT = (240, 200, 90)


class Fonts:
    _cache: Dict[Tuple[int, bool], pygame.font.Font] = {}

    @classmethod
    def clear(cls) -> None:
        """Fonts die with pygame.quit(), so a restarted app must not reuse old ones."""
        cls._cache.clear()

    @classmethod
    def get(cls, size: int, bold: bool = False) -> pygame.font.Font:
        key = (size, bold)
        if key not in cls._cache:
            cls._cache[key] = pygame.font.SysFont("arial,helvetica,dejavusans,liberationsans", size, bold=bold)
        return cls._cache[key]


def draw_text(surface: pygame.Surface, text: str, position: Tuple[int, int], size: int = 15,
              color: Color = Theme.TEXT, bold: bool = False, center: bool = False,
              right: bool = False) -> pygame.Rect:
    image = Fonts.get(size, bold).render(text, True, color)
    if center:
        rect = image.get_rect(center=position)
    elif right:
        rect = image.get_rect(topright=position)
    else:
        rect = image.get_rect(topleft=position)
    surface.blit(image, rect)
    return rect


def fit_text(text: str, size: int, width: int, bold: bool = False) -> str:
    """Shorten text with an ellipsis so that it fits a width in pixels."""
    font = Fonts.get(size, bold)
    if font.size(text)[0] <= width:
        return text
    while text and font.size(text + "...")[0] > width:
        text = text[:-1]
    return text + "..."


def draw_pips(surface: pygame.Surface, rect: pygame.Rect, value: int, maximum: int, color: Color) -> None:
    """A segmented meter: one block per hit point, so that the count can be read directly."""
    gap = 2
    width = (rect.width - gap * (maximum - 1)) / maximum
    for index in range(maximum):
        block = pygame.Rect(int(rect.x + index * (width + gap)), rect.y, max(1, int(width)), rect.height)
        pygame.draw.rect(surface, color if index < value else Theme.BORDER, block, border_radius=2)
