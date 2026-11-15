"""Colours and text helpers."""
from __future__ import annotations

from typing import Dict, Tuple

import pygame

Color = Tuple[int, int, int]


class Theme:
    # Light, minimal interface. The playfield itself stays black, as in the arcade original,
    # so that the sprites keep their contrast.
    BACKGROUND = (246, 247, 250)
    PANEL = (255, 255, 255)
    CARD = (236, 238, 244)
    CARD_HOVER = (221, 225, 236)
    BORDER = (208, 213, 224)
    TEXT = (32, 36, 46)
    MUTED = (96, 103, 118)
    FAINT = (140, 147, 162)
    BOARD_TEXT = (240, 242, 246)  # text drawn on top of the black playfield
    BOARD_MUTED = (172, 178, 192)
    BOARD_ACCENT = (240, 200, 90)
    BOARD_GOOD = (84, 190, 120)
    GROUND_A = (0, 0, 0)  # the black playfield
    WALL_FACE = ((200, 72, 24), (200, 72, 24), (240, 128, 64))  # brick colours, for chips flying off a hit
    # Identity colours of the two players: yellow, as in the arcade original, and blue. Checked
    # with the palette validator of the dataviz guidelines on a black surface: the pair stays
    # apart under colour blindness (worst case 24 on the OKLab scale) and clears 3:1 contrast.
    # Only the yellow is lighter than that tool's band for chart colours, which suits a sprite.
    PLAYERS = ((232, 192, 40), (74, 168, 232))
    PLAYERS_LIGHT = ((252, 232, 128), (172, 220, 252))
    PLAYERS_DARK = ((156, 112, 16), (24, 88, 148))
    PLAYER_TEXT = ((138, 96, 0), (24, 88, 148))  # the player colours, darkened to be readable on white
    GOOD = (26, 128, 70)
    BAD = (200, 40, 40)
    ACCENT = (168, 104, 0)


class Fonts:
    _cache: Dict[Tuple[int, bool], pygame.font.Font] = {}

    @classmethod
    def clear(cls) -> None:
        """Fonts die with pygame.quit(), so a restarted app must not reuse old ones."""
        cls._cache.clear()

    @classmethod
    def get(cls, size: int, bold: bool = False) -> pygame.font.Font:
        size = size + 1 if size <= 14 else size  # small text is bumped by one point for readability
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
