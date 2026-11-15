"""A chess queen drawn from polygons and circles.

The first interface rendered the character U+265B, which needs a font with chess
symbols; the default fonts of macOS (the evaluation machine) may not provide one, and
the piece then shows as an empty box. Drawing the shape avoids any font.
"""
from __future__ import annotations

from typing import Dict, Tuple

import pygame

from .theme import Color


class QueenPainter:
    """Renders a queen of a given size and colour, drawn 4x larger then smoothly scaled
    down (which antialiases it), and caches every rendered piece."""

    SUPERSAMPLE = 4
    # Shape on a 100 x 100 grid: a crown of five points, a body and a base.
    CROWN = ((27, 66), (13, 31), (28, 48), (31, 23), (42, 45), (50, 18), (58, 45),
             (69, 23), (72, 48), (87, 31), (73, 66))
    TIPS = ((13, 31), (31, 23), (50, 18), (69, 23), (87, 31))
    BODY = ((27, 64), (73, 64), (79, 80), (21, 80))
    BASE = (17, 79, 66, 11)
    TIP_RADIUS = 6
    OUTLINE = 5

    def __init__(self) -> None:
        self._cache: Dict[Tuple[int, Color, Color, int], pygame.Surface] = {}

    def get(self, size: int, fill: Color, outline: Color, alpha: int = 255) -> pygame.Surface:
        key = (size, fill, outline, alpha)
        if key not in self._cache:
            piece = self._render(max(4, size), fill, outline)
            if alpha < 255:
                piece.set_alpha(alpha)
            self._cache[key] = piece
        return self._cache[key]

    def _render(self, size: int, fill: Color, outline: Color) -> pygame.Surface:
        big = size * self.SUPERSAMPLE
        k = big / 100.0
        surface = pygame.Surface((big, big), pygame.SRCALPHA)

        def scaled(points):
            return [(x * k, y * k) for x, y in points]

        polygons = (scaled(self.CROWN), scaled(self.BODY))
        x, y, w, h = (v * k for v in self.BASE)
        base = pygame.Rect(round(x), round(y), round(w), round(h))
        tips = scaled(self.TIPS)
        tip_radius = self.TIP_RADIUS * k
        stroke = max(1, round(self.OUTLINE * k))

        # Outline: every shape drawn in the outline colour, grown by `stroke` on all sides.
        for polygon in polygons:
            pygame.draw.polygon(surface, outline, polygon)
            for start, end in zip(polygon, polygon[1:] + polygon[:1]):
                pygame.draw.line(surface, outline, start, end, 2 * stroke)
            for point in polygon:
                pygame.draw.circle(surface, outline, point, stroke)
        pygame.draw.rect(surface, outline, base.inflate(2 * stroke, 2 * stroke), border_radius=round(5 * k) + stroke)
        for tip in tips:
            pygame.draw.circle(surface, outline, tip, tip_radius + stroke)

        # Body.
        for polygon in polygons:
            pygame.draw.polygon(surface, fill, polygon)
        pygame.draw.rect(surface, fill, base, border_radius=round(5 * k))
        for tip in tips:
            pygame.draw.circle(surface, fill, tip, tip_radius)
        # Thin light bands between crown, body and base give the piece some relief.
        band = max(1, round(2.2 * k))
        pygame.draw.line(surface, outline, (26 * k, 65 * k), (74 * k, 65 * k), band)
        pygame.draw.line(surface, outline, (21 * k, 79.5 * k), (79 * k, 79.5 * k), band)

        return pygame.transform.smoothscale(surface, (size, size))
