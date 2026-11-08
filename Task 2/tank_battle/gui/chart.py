"""A small line chart of who is ahead, cycle by cycle."""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import pygame

from .theme import Theme, draw_text


class AdvantageChart:
    """One series around zero: above the line player 1 is ahead, below it player 2.

    The two regions carry the players' colours and are also labelled in words, so that
    identity does not depend on colour alone. Hovering shows the value at any cycle.
    """

    MIN_CYCLES = 30
    MIN_RANGE = 10.0

    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def _plot_area(self) -> pygame.Rect:
        return pygame.Rect(self.rect.x + 12, self.rect.y + 30, self.rect.width - 24, self.rect.height - 40)

    def draw(self, surface: pygame.Surface, values: Sequence[float], highlighted: Optional[int] = None) -> None:
        pygame.draw.rect(surface, Theme.PANEL, self.rect, border_radius=10)
        draw_text(surface, "Who is ahead", (self.rect.x + 12, self.rect.y + 8), 14, Theme.TEXT, bold=True)
        if values:
            draw_text(surface, f"{values[-1]:+.1f}", (self.rect.right - 12, self.rect.y + 9), 13, Theme.TEXT, right=True)

        plot = self._plot_area()
        scale = max(self.MIN_RANGE, max((abs(v) for v in values), default=0.0)) * 1.1
        span = max(self.MIN_CYCLES, len(values) - 1)
        zero_y = plot.centery

        def point(index: int, value: float) -> Tuple[int, int]:
            return (int(plot.x + index / span * plot.width), int(zero_y - value / scale * plot.height / 2))

        # Region tints, so that the side of the line reads at a glance.
        layer = pygame.Surface(plot.size, pygame.SRCALPHA)
        layer.fill((*Theme.PLAYERS[0], 18), (0, 0, plot.width, plot.height // 2))
        layer.fill((*Theme.PLAYERS[1], 18), (0, plot.height // 2, plot.width, plot.height - plot.height // 2))
        surface.blit(layer, plot)
        pygame.draw.line(surface, Theme.BORDER, (plot.x, zero_y), (plot.right, zero_y))
        self._side_label(surface, "P1 ahead", Theme.PLAYERS[0], plot.x + 4, plot.y + 2)
        self._side_label(surface, "P2 ahead", Theme.PLAYERS[1], plot.x + 4, plot.bottom - 15)

        if len(values) >= 2:
            points: List[Tuple[int, int]] = [point(i, v) for i, v in enumerate(values)]
            pygame.draw.lines(surface, Theme.TEXT, False, points, 2)
        if values:
            pygame.draw.circle(surface, Theme.TEXT, point(len(values) - 1, values[-1]), 3)
        if highlighted is not None and 0 <= highlighted < len(values):
            x = point(highlighted, values[highlighted])[0]
            pygame.draw.line(surface, Theme.ACCENT, (x, plot.y), (x, plot.bottom), 1)
        self._draw_hover(surface, plot, values, span, point)

    @staticmethod
    def _side_label(surface: pygame.Surface, text: str, color: Tuple[int, int, int], x: int, y: int) -> None:
        pygame.draw.rect(surface, color, (x, y + 3, 8, 8), border_radius=2)
        draw_text(surface, text, (x + 12, y), 11, Theme.MUTED)

    @staticmethod
    def _draw_hover(surface, plot, values, span, point) -> None:
        mouse = pygame.mouse.get_pos()
        if not values or not plot.collidepoint(mouse):
            return
        index = min(len(values) - 1, max(0, round((mouse[0] - plot.x) / plot.width * span)))
        x, y = point(index, values[index])
        pygame.draw.line(surface, Theme.MUTED, (x, plot.y), (x, plot.bottom), 1)
        pygame.draw.circle(surface, Theme.ACCENT, (x, y), 4)
        text = f"cycle {index}: {values[index]:+.1f}"
        label = pygame.Rect(0, 0, 112, 20)
        label.midbottom = (min(max(x, plot.x + 56), plot.right - 56), max(plot.y + 22, y - 6))
        pygame.draw.rect(surface, Theme.CARD_HOVER, label, border_radius=4)
        draw_text(surface, text, label.center, 12, Theme.TEXT, center=True)
